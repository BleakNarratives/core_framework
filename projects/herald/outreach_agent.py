#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: monetization
# DEPS: stdlib only; shells out to bin/ai for the model call
# ROLE: Draft a tailored outreach email per qualified lead in LEADS.md
# AUTHOR: Bleak
# SESSION: 2026-09-16
# TIER: 4
# [/DNA_TAG]

"""outreach_agent — turn qualified leads into drafts you can send in one click.

WHAT IT DOES
  Reads LEADS.md, keeps the entries that are actually contactable, and asks the
  model for a short honest pitch tailored to each one. Writes them to
  OUTREACH_DRAFTS.md with the recipient, the subject, a prefilled `mailto:` link,
  and the source thread. Go there, read them, send the ones that are true.

WHAT IT DELIBERATELY DOES NOT DO, AND WHY
  There is no --send and no --post, and that is a decision, not an omission.

  1. It would have nothing to send to. The contact detail Reddit publishes is a
     username and, occasionally, an email. For most posts the only route is a DM,
     which needs your authenticated session -- so "automated sending" would mean
     driving your Reddit account, not a mail server.
  2. It would burn the only asset you have. Bulk promotional DMs are what Reddit's
     terms call spam, and the penalty is the account -- which is also the lead
     source. Cold email without a physical address and an opt-out is a CAN-SPAM
     problem in the US. Neither risk buys you a single extra reply.
  3. It cannot write the pitch. Look at the qualification output: the tool can
     find *who is hiring*, but it has no idea what you are selling. A pitch with
     no offer, sent 50 times, is not a funnel.

  So the split is: the machine writes the copy, which is the labour you did not
  want to do. You press send, from your identity, having read it. That is the
  same rule this repo already applies to the shell -- consenting to a draft is
  not consent to contact a stranger.

WHY A REPLY IS NOW CHECKED BEFORE IT IS WRITTEN (measured 2026-09-17)
  The only test a reply had to pass was "does it start with NO FIT". Anything else
  was written out as copy. Then a run with `--about-file ABOUT.md` returned six
  replies that were the *prompt itself* -- the whole question, echoed back as the
  answer -- and all six were written to OUTREACH_DRAFTS.md as drafts, with an
  empty subject and a `mailto:` body of "Write one short outreach email...". The
  file went from 3.5 KB to 155 KB in one run.

  Two things follow. One, a run that counts those as drafts is not reporting a fit
  rate, it is reporting how often the model echoed the question -- which is how a
  broken pipe reads as 70% fit. Two, the echo is NOT deterministic: the same lead
  and prompt, called twice by hand, refused both times. `complete()` goes through
  `bin/ai`, whose model resolves to `auto`, so the gateway rotates pools and some
  calls land on a model that behaves this way. Pin `--model` before comparing any
  two offers, or the comparison measures pool selection.

WHY A DRAFT CAN NOW POINT AT SOMETHING (2026-09-21)
  ABOUT.md ends with "code you can read" and gives nowhere to read it, which
  ABOUT_EVIDENCE.md itself calls the weakest line in the pitch. So a draft may now
  carry a bounded list of public artifacts, read from a Foxwood research ledger:

      outreach_agent --about-file ABOUT.md --evidence-ledger ~/foxwood_data/ledger

  Two things about this are deliberate.

  One, the evidence does NOT become new material about the offer. ABOUT.md is still
  the only place a claim about me may come from; the ledger lines only say what the
  existing claims rest on. A draft that leaned on the artifacts to say something
  *new* about me would be the same lie as an invented client list, told with better
  citations.

  Two, this is where a rule stops being prose. The last line of ABOUT_EVIDENCE.md's
  may-not-claim list says no ScholarScout-derived or quarantined material may be used
  as Foxwood evidence. That was a wish until this path existed; now every source is
  admitted through the repository's PROVENANCE.md registry before it can reach a
  prompt, and a refusal is fatal to the run rather than a quiet downgrade to "no
  evidence available". A requested ledger that cannot be read is a broken pipe, and
  herald already has a measured scar about what a broken pipe looks like when it is
  reported as a good number.

Usage:
    outreach_agent --list                       who qualifies, and who does not
    outreach_agent --about-file ABOUT.md             draft for everyone qualified
    outreach_agent --about-file ABOUT.md --dry-run   show prompts; call nothing
    outreach_agent --about-file ABOUT.md --limit 3   cap drafts this run
    outreach_agent --about-file ABOUT.md --redo      re-draft already-drafted leads
    outreach_agent --about-file ABOUT.md \
        --evidence-ledger DIR                        cite real artifacts in the draft
    outreach_agent --about-file ABOUT.md \
        --evidence-ledger DIR --evidence-claim claim-abc123   cite exactly one thing

  --about is required for drafting on purpose. It is your one paragraph of what
  you actually offer; the model tailors it per lead but may not invent beyond it.

  Evidence is the same rule one level down: changing the ledger, or which claims are
  selected from it, changes what a lead is being asked under, so it needs --redo for
  the same reason a new --about paragraph does.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADS_FILE = HERE / "LEADS.md"
DRAFTS_FILE = HERE / "OUTREACH_DRAFTS.md"

# Machine memory, kept separate from the drafts file on purpose. OUTREACH_DRAFTS.md
# is copy for you to read and send, and a refusal is not copy -- but without a record
# of refusals a batch cannot resume, because the only thing `todo` could exclude is a
# lead already *drafted*. Measured 2026-09-17: three batches of 15/17/10 made 42 calls
# covering 19 distinct leads, because each batch restarted at the first unrefused
# lead. Safe to delete; deleting it re-opens every lead.
#
# The memory is per LEAD, not per offer. A verdict is the model's answer to one lead
# under one `--about` paragraph, so if you change the offer, run with --redo -- or the
# answers given to the old offer will stand in for the new one and nothing will be
# re-asked. Measured 2026-09-17: two offers that looked similar drafted 9 leads and 0.
STATE_FILE = HERE / ".herald_state.json"

# Evidence is bounded the same way the Scout payloads are: a draft may rest on a few
# artifacts or none, and never on an unbounded bundle. The cap is on lines, and each
# line is clipped, so the prompt cannot grow a second half nobody reads.
EVIDENCE_LIMIT_DEFAULT = 4
EVIDENCE_TEXT_CAP = 240

# The apply-form rule lives in monitor_leads and is imported rather than
# reimplemented. Two copies of "what counts as contact" is how the number drifted
# in the first place -- and this reader has to grade entries that were written
# before the rule existed, so it must be the *same* rule, not a similar one.
sys.path.insert(0, str(HERE))
from monitor_leads import employment_type, reaches_a_person, route_kind  # noqa: E402


def find_ai() -> Path:
    """Locate bin/ai by walking up from this file.

    Not a hard-coded number of parents. This project has already moved once — it
    lived at the repository root until 2026-09-17 — and a fixed depth breaks
    silently on the next reorganisation, turning into "the model returned
    nothing" instead of "I looked in the wrong place". Walking up until bin/ai
    appears is the version that survives being filed into a project folder,
    which is the entire reason it is being filed.
    """
    for parent in (HERE, *HERE.parents):
        candidate = parent / "bin" / "ai"
        if candidate.is_file():
            return candidate
    return HERE / "bin" / "ai"


# Reuse, not rebuild: bin/ai is this repo's single front-end for every model
# call ("the backend is done"), and it already goes through the rotating
# gateway. A second HTTP client here would be a second place for endpoint and
# key handling to drift. It is also a repo-level dependency rather than a
# project-local one, which is why the search above walks upward.
AI = find_ai()


def find_repo_root() -> Path | None:
    """Walk up to the repository root: PROVENANCE.md plus src/foxwood_research.

    Both are required, not either. PROVENANCE.md alone is the classification
    registry and lives at the root; src/foxwood_research alone could be a vendored
    copy. Needing both is what makes this the root rather than a directory that
    happens to look like one.
    """
    for parent in (HERE, *HERE.parents):
        if (parent / "PROVENANCE.md").is_file() \
                and (parent / "src" / "foxwood_research").is_dir():
            return parent
    return None


def _import_foxwood():
    """Import Foxwood lazily, only on the path that asked for evidence.

    Herald has to run on a checkout where Foxwood is absent -- it is a project in
    this repository, not a dependency of it -- so the import lives here rather than
    at module scope. No import, no cost, and no new way for herald to fail to start.
    """
    root = find_repo_root()
    if root is None:
        raise RuntimeError(
            "no repository root found above "
            f"{HERE} (looking for PROVENANCE.md and src/foxwood_research); "
            "--evidence-ledger needs both")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from src.foxwood_research import RegistryGate, ResearchLedger
    except Exception as exc:
        raise RuntimeError(f"Foxwood is not importable from {root}: {exc}") from exc
    return RegistryGate, ResearchLedger


def _evidence_row(claim, source, kind: str) -> dict:
    """One prompt-ready line. `kind` is what the framing keys on.

    `artifact` is something the operator made and the offer rests on; `thread` is
    something a stranger posted and the draft is answering. They must not be framed
    the same way -- a lead's post described as "my artifact" would have the model
    tell the prospect about their own job ad. `claim` is empty on the thread path
    for the reason `load_evidence` gives below.
    """
    return {
        "claim_id": claim.claim_id if claim else "",
        "claim": claim.text[:EVIDENCE_TEXT_CAP] if claim else "",
        "confidence": claim.confidence if claim else "",
        "kind": kind,
        "source_id": source.source_id,
        "title": source.title,
        "url": source.url,
        "publisher": source.publisher,
        "content_hash": source.content_hash,
        "license_note": source.license_note,
    }


def load_evidence(ledger_dir, claim_ids=(),
                  limit: int = EVIDENCE_LIMIT_DEFAULT,
                  source_ids=()) -> list[dict]:
    """Bounded, registry-admitted evidence from a Foxwood ledger.

    This is the enforcement point for a rule that until now was prose. The last
    bullet of ABOUT_EVIDENCE.md's may-not-claim list says no ScholarScout-derived or
    quarantined material may be used as Foxwood evidence; reading the registry gate
    here means that holds even when the operator forgets it.

    Raises rather than returning nothing. A ledger that was asked for and cannot be
    read is a broken pipe, and it must not present itself as "no evidence available,
    carrying on" -- that is the shape of failure this pipeline already recorded once,
    when six echoed prompts were written out as six drafts.

    Selection is explicit or bounded, never editorial: either the operator names the
    claims, or the most recent `limit` of them are taken. This tool does not know
    which of your artifacts answer a stranger's job post, and a guess dressed up as
    relevance is how a pitch starts inventing things.

    `source_ids` selects sources by name instead of by claim, and it is the lead
    path. A lead's post is evidence in its own right, so demanding a claim before it
    can be cited would mean inventing a claim about a stranger. Nothing on that path
    reads `ledger.claims`, which is what lets a ledger of seeded leads work at all --
    and why the no-claims check below sits *after* the branch rather than in front
    of it.
    """
    RegistryGate, ResearchLedger = _import_foxwood()
    path = Path(ledger_dir).expanduser()
    if not path.is_dir():
        raise RuntimeError(f"no ledger directory at {path}")
    ledger = ResearchLedger(path)

    # One gate for the whole run, built once: it parses the registry, and a refusal
    # must be visible here rather than surfacing later as an unexplained empty list.
    gate = RegistryGate()

    named = [sid.strip() for sid in (source_ids or ()) if sid and sid.strip()]
    if named:
        rows: list[dict] = []
        for source_id in named:
            try:
                source = ledger.get_source(source_id)
            except Exception as exc:
                raise RuntimeError(f"{exc}") from exc
            gate.admit(source.origin, source.url)
            rows.append(_evidence_row(None, source, "thread"))
        return rows

    if not ledger.claims:
        raise RuntimeError(f"{path} holds no claims, so there is nothing to support an offer with")

    wanted = [cid.strip() for cid in (claim_ids or ()) if cid and cid.strip()]
    if wanted:
        try:
            claims = [ledger.get_claim(cid) for cid in wanted]
        except Exception as exc:
            raise RuntimeError(f"{exc}") from exc
    else:
        claims = list(ledger.claims)[-max(1, int(limit)):]
    if not claims:
        raise RuntimeError("no claims selected from the ledger")

    rows = []
    for claim in claims:
        for source_id in claim.source_ids:
            source = ledger.get_source(source_id)
            # Re-admit stored evidence, not just new evidence. A ledger written
            # before the registry gate existed is still graded by the rule that
            # exists now -- the same stance this reader already takes on leads whose
            # file predates the contact rule.
            gate.admit(source.origin, source.url)
            rows.append(_evidence_row(claim, source, "artifact"))
    return rows


def evidence_block(evidence) -> str:
    """The prompt fragment, or "" when there is no evidence.

    Empty really means empty: the no-evidence prompt is byte-for-byte the prompt
    this tool sent before evidence existed, so nothing about the existing behaviour
    is being reinterpreted by this feature.

    Two kinds of row arrive here and they get opposite framings, which is why they
    are rendered as separate sections rather than one list. An `artifact` is the
    operator's and a draft may point at it; a `thread` is a stranger's and a draft is
    answering it. One shared sentence -- "these are MY artifacts" -- would have the
    model tell a prospect about their own job ad, and the two cases are one word
    apart in the prompt and nothing alike in the world.
    """
    rows = list(evidence or ())
    if not rows:
        return ""
    artifacts = [row for row in rows if row.get("kind") != "thread"]
    threads = [row for row in rows if row.get("kind") == "thread"]
    sections: list[str] = []
    if artifacts:
        lines = ["Public artifacts the offer above rests on, and the only things you may point at:"]
        for row in artifacts:
            lines.append(
                f"  [{row['source_id']}] {row['title']} \u2014 {row['url']} "
                f"(license: {row['license_note']}; sha256 {row['content_hash'][:12]})")
        lines += [
            "How to use that list, and it is not optional:",
            "- These are MY artifacts. Never say or imply they exist inside their system.",
            "- Do not claim anything about them beyond the title and the line above.",
            "- Name one only if it directly answers something in their post. If none fits,",
            "  name none and let the offer stand on its own.",
        ]
        sections.append("\n".join(lines))
    if threads:
        lines = ["The post I am replying to, linked so I can open it myself:"]
        for row in threads:
            lines.append(f"  [{row['source_id']}] {row['title']} \u2014 {row['url']} "
                         f"(sha256 {row['content_hash'][:12]})")
        lines += [
            "How to use that, and it is not optional:",
            "- That is THEIR post, not mine. Never call it mine, never imply I made it.",
            "- I can see the title and the link, not the thread. Do not claim to have read",
            "  anything past what is written above, and do not describe their setup.",
            "- Do not quote it back at length or explain their own problem to them.",
            "- If the title does not say enough to know what they want, ask the one thing",
            "  I would need to know rather than guessing at it.",
        ]
        sections.append("\n".join(lines))
    return "\n" + "\n\n".join(sections) + "\n"

# `* **[author]** title` starts an entry; an indented `- Key: value` adds a field.
# Both shapes appear in LEADS.md: the old scanner wrote `URL:`, monitor_leads
# writes `Link:` plus `Matched:` and `Contact:`.
ENTRY_RE = re.compile(r"^\* \*\*\[(?P<who>[^\]]+)\]\*\*\s*(?P<title>.+?)\s*$")
FIELD_RE = re.compile(r"^\s+-\s*(?P<key>[A-Za-z]+):\s*(?P<value>.*)$")
SOURCE_KEYS = ("Link", "URL")

HEADER = """# OUTREACH DRAFTS — written, not sent

Generated by `outreach_agent.py` from `LEADS.md`. Newest at the bottom.

**Nothing here has been sent.** There is no send mode in that script and there is
not going to be one: bulk unsolicited DM or mail gets the account that is your
lead source banned, and a pitch with no offer behind it does not improve with
volume. Read each draft, then use the mail link or the thread.

Every draft is only as true as the `--about` paragraph it was given. If a draft
overstates what you do, fix the paragraph and re-run with `--redo`.
"""


# ── pure helpers (no network, no subprocess) ─────────────────────────────────

def parse_leads(text: str) -> list[dict]:
    """LEADS.md -> entries, in file order.

    Tolerates both the old and new entry shapes rather than assuming one: the
    file is append-only and holds output from both versions of the scanner.
    """
    entries: list[dict] = []
    for line in (text or "").splitlines():
        match = ENTRY_RE.match(line)
        if match:
            entries.append({"who": match.group("who").strip(),
                            "title": match.group("title").strip(),
                            "fields": {}})
            continue
        field = FIELD_RE.match(line)
        if field and entries:
            entries[-1]["fields"][field.group("key")] = field.group("value").strip()
    return entries


def source_of(entry: dict) -> str:
    for key in SOURCE_KEYS:
        if entry["fields"].get(key):
            return entry["fields"][key]
    return ""


def contacts_of(entry: dict) -> list[str]:
    raw = entry["fields"].get("Contact", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def emails_of(entry: dict) -> list[str]:
    return [c.split(":", 1)[1] for c in contacts_of(entry)
            if c.startswith("email:") and "@" in c]


def reachable_of(entry: dict) -> list[str]:
    """The contact hints that reach a person, in file order.

    An application form is a route and not a person: whatever is sent to one goes
    into an ATS that no human reads as a message. This is what `qualify` gates on,
    and it is deliberately stricter than "has something in the Contact field".
    """
    return [hint for hint in contacts_of(entry) if reaches_a_person(hint)]


def qualify(entry: dict) -> tuple[bool, str]:
    """(qualified, reason if not). The reason is shown, never swallowed.

    A lead needs two independent things: someone with work, and a way to reach
    them. Both are required, and they fail for different reasons, so the reasons
    are reported separately rather than as one unhelpful zero.
    """
    if not entry["fields"].get("Matched"):
        return False, "not a hiring post (a discussion thread, or a pre-filter entry)"
    if not contacts_of(entry):
        return False, "hiring, but published no way to make contact"
    if not reachable_of(entry):
        # Distinguished from the case above on purpose: "nothing published" and
        # "published only a place" are different facts about a lead, and the second
        # is what made the headline count wrong before it had its own reason. The
        # kinds are named, because "a form" and "a homepage" call for different
        # next actions from you.
        kinds = sorted({route_kind(h) for h in contacts_of(entry)})
        if kinds == ["apply"]:
            return False, ("published only an application form, which reaches a form "
                           "and not a person")
        return False, ("published no address and no direct route (only "
                       + "/".join(kinds) + "), so the thread is the only way in")
    if not source_of(entry):
        return False, "no source link, so no thread to reply in"
    return True, ""


def split_subject(reply: str) -> tuple[str, str]:
    """Model reply -> (subject, body). A missing subject is not an error."""
    lines = (reply or "").strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "", (reply or "").strip()


# The prompt's own sentences. A reply containing one of these is the question,
# not an answer -- there is no way a legitimately written email quotes the
# instruction "Write one short outreach email from me to someone who posted
# about work", and matching two independent phrases rather than one keeps a
# stray coincidence from discarding a real draft.
PROMPT_ECHO_MARKERS = (
    "write one short outreach email from me to someone who posted about work",
    "what i actually offer, and the only thing you may claim about me",
)

# The prompt asks for under 120 words. This is the sanity bound rather than the
# style rule: a body at 4x the cap is a different kind of output, not a verbose one.
BODY_WORD_CAP = 200


def not_an_email(subject: str, body: str) -> str:
    """Why this reply cannot be written as a draft, or "" if it can.

    Deliberately separate from the NO FIT path. A refusal is a decision the model
    is allowed to make; this is a malformed completion. They are counted apart
    because conflating them is exactly the failure that made a run of six echoed
    prompts look like six fits.
    """
    text = (body or "").strip()
    lowered = text.lower()
    if not text:
        return "empty reply"
    for marker in PROMPT_ECHO_MARKERS:
        if marker in lowered:
            return "the prompt was echoed back instead of answered"
    if not (subject or "").strip():
        return "no 'Subject:' first line, which the prompt requires"
    words = len(text.split())
    if words > BODY_WORD_CAP:
        return f"{words} words; the prompt caps the body at 120"
    return ""


def build_prompt(entry: dict, about: str, evidence=()) -> str:
    """The whole prompt, and the constraints are the interesting part.

    Three of these rules exist because a model writing sales copy will otherwise
    invent things: credentials, familiarity with the poster, or a claim that the
    post asked for something it did not. The last rule is the important one -- it
    gives the model permission to say the two of you do not match, which is the
    answer you actually want on most of these.

    `evidence` is optional and defaults to empty, which reproduces the previous
    prompt exactly. See `evidence_block` for why the artifacts are framed as
    citations for the offer rather than as more to say about it.
    """
    return f"""Write one short outreach email from me to someone who posted about work.

Their post:
  title: {entry['title']}
  posted by: {entry['who']}
  source: {source_of(entry)}

What I actually offer, and the only thing you may claim about me:
\"\"\"
{about.strip()}
\"\"\"
{evidence_block(evidence)}
Write the email in my voice. Rules, and they are not negotiable:
- First line exactly "Subject: <subject>". Then a blank line, then the body.
- Body under 120 words. Plain text. No markdown, no bullets, no emoji, no signature block.
- Open with their specific problem in one sentence. Do not quote their post back at length.
- Do not flatter, do not say "I came across your post", do not invent credentials,
  employers, results, or knowledge of them.
- Do not claim I have done anything that is not stated above.
- End with one small, concrete ask. Do not ask for a call as the first step.
- If what I offer plainly does not fit the work in the post, reply with exactly
  "NO FIT" and one sentence saying why, and nothing else.
"""


def render(entry: dict, subject: str, body: str, now: str, *, evidence=()) -> str:
    """One draft block. Records the send route, and says plainly if there is none.

    `evidence` is keyword-only and optional, so every existing call site keeps
    working unchanged, and a draft with no evidence renders exactly as it did
    before. When evidence is present it is written onto the draft, because the one
    thing a reader of OUTREACH_DRAFTS.md needs before pressing send is what the
    pitch is resting on -- and whether its license permits saying so.

    `Contact:` carries only the routes that reach a person. Places -- a homepage, a
    job document, an application form -- go on their own `Published:` line, because
    `Contact: link:https://acme.test` is the same overclaim as the count it came
    from: it puts a venue where a person belongs, in the one place you actually read.
    """
    who = entry["who"]
    reachable = reachable_of(entry)
    places = [hint for hint in contacts_of(entry) if hint not in reachable]
    addresses = emails_of(entry)
    lines = [f"\n## {entry['title']}\n",
             f"- To: {who}",
             "- Contact: " + (", ".join(reachable) if reachable
                              else "nothing published reaches a person"),
             f"- Source: {source_of(entry)}",
             # What the post says it is offering, so a draft to a salaried ad is
             # visible as such without herald deciding what to do about it.
             f"- Employment as stated in the post: {employment_type(entry['title'])}",
             f"- Status: **draft only — nothing sent** ({now})"]
    rows = list(evidence or ())
    if rows:
        lines.append("- Evidence: " + "; ".join(
            f"[{row['source_id']}] {row['title'][:60]} "
            f"(sha256 {row['content_hash'][:12]}; {row['license_note']})"
            for row in rows))
    if places:
        lines.append(f"- Published (places, not routes): {', '.join(places)}")
    if addresses:
        link = mailto(addresses[0], subject, body)
        lines.append(f"- Send: [open in your mail client]({link})")
    else:
        lines.append("- Send: no email published — the only route is a reply or DM "
                     "on the thread above, which you do yourself")
    if not addresses and not reachable_of(entry):
        # A draft can be rendered directly, so say it here too rather than letting
        # the links above read as a way in.
        lines.append("- Reach: nothing published reaches a person — "
                     "reply on the thread instead")
    lines.append("")
    if subject:
        lines.append(f"**Subject:** {subject}\n")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def mailto(address: str, subject: str, body: str) -> str:
    """A mailto: URL with subject and body prefilled.

    This is the entire 'automation' of sending, on purpose: one click, from your
    own client, to your own identity, after you have read the text. It cannot
    fire by accident and it cannot fire fifty times.
    """
    return (f"mailto:{address}"
            f"?subject={urllib.parse.quote(subject)}"
            f"&body={urllib.parse.quote(body)}")


def drafted_sources(text: str) -> set[str]:
    """Source URLs already drafted, so a re-run adds nothing.

    Keyed on the source link rather than the title: a title can be edited in
    LEADS.md and must not produce a second email to the same person.
    """
    return {m.group(1).strip() for m in
            re.finditer(r"^- Source:\s*(\S+)\s*$", text or "", re.M)}


# A verdict that is final, and a verdict that is worth trying again. A refusal and a
# malformed reply are decisions about a lead that has not changed, so repeating them
# wastes a call. A transport failure is the opposite: the same lead may answer fine
# on the next run, so it is recorded for the report and deliberately not skipped.
RESOLVED_VERDICTS = ("no_fit", "malformed")


def load_state(path: Path) -> dict:
    """Verdicts from earlier runs, keyed by lead source.

    A missing or unreadable file is not an error -- it is a first run, or a file
    somebody truncated. Failing to read it must never stop a run that would otherwise
    work: the cost of forgetting is a repeated call, not a broken tool.
    """
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"    ignoring unreadable {path.name} ({type(exc).__name__}); "
              "every lead will be treated as new", file=sys.stderr)
        return {}
    leads = data.get("leads") if isinstance(data, dict) else None
    return leads if isinstance(leads, dict) else {}


def save_state(path: Path, leads: dict) -> None:
    """Write it atomically, so a run killed mid-write cannot truncate the memory."""
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "verdict per lead source; delete this file to start over",
        "leads": leads,
    }
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)
    except OSError as exc:
        print(f"    could not write {path.name} ({exc}); this run will not resume",
              file=sys.stderr)


# ── model call ───────────────────────────────────────────────────────────────

# A 429 means two different things through this gateway and only one of them is
# worth waiting for. Measured 2026-09-17 on the raw envelope: `bin/ai --json`
# returns exactly {"ok", "error"} -- no headers, no retry_after field -- so the
# provider's own hint has to be read out of the error *string*. Two shapes seen:
#
#   "Rate limit reached for model ... Please try again in 7.199999999s"   <- wait
#   "You have no credits remaining ... credit_balance_exhausted"          <- 429 too
#
# The second cannot be fixed by waiting: the pool is out of credit, and retrying
# turns a fast failure into a slow one. So a wait is only returned when the message
# actually asks us to wait.
WAIT_PATTERNS = (
    re.compile(r"retry[_-]?after\"?\s*[:=]\s*\"?([0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(r"try again in ([0-9]+(?:\.[0-9]+)?)s", re.I),
    re.compile(r"retry after ([0-9]+(?:\.[0-9]+)?)", re.I),
)
# Specific codes only. An earlier version of this matched the bare word "billing"
# and was therefore dead code: Groq's *rate-limit* message ends with a link to
# https://console.groq.com/settings/billing, so every retryable 429 was classified
# as a dead account and never retried. Found by running it, not by reading it -- the
# only visible symptom was that the retry had never fired once.
QUOTA_EXHAUSTED_RE = re.compile(
    r"insufficient_quota|credit_balance_exhausted|no credits remaining|"
    r"exceeded your current quota", re.I)
MIN_WAIT = 2.0     # a 429 with no hint at all still deserves one short pause
MAX_WAIT = 60.0    # never hold a run on one lead for longer than this
DEFAULT_RETRIES = 3


def retry_after_seconds(message: str) -> float | None:
    """How long to wait before trying again, or None if trying again cannot help.

    None covers both "this is not a rate limit" and "this is a rate limit caused by
    an empty account" -- two different reasons not to sleep.
    """
    text = message or ""
    # In order: is this a rate limit at all, is it one that waiting cannot fix, and
    # only then how long to wait.
    if "429" not in text and "rate limit" not in text.lower():
        return None
    if QUOTA_EXHAUSTED_RE.search(text):
        return None
    for pattern in WAIT_PATTERNS:
        found = pattern.search(text)
        if found:
            try:
                return min(MAX_WAIT, max(0.0, float(found.group(1))))
            except ValueError:
                break
    return MIN_WAIT


def complete_with_retries(prompt: str, model: str | None = None,
                          retries: int = DEFAULT_RETRIES,
                          sleep=time.sleep) -> str:
    """complete(), but a rate limit is a wait rather than a lost lead.

    `sleep` is injected so this path can be tested without a suite that takes four
    minutes to run -- the same reason `complete` is patched in the tests.

    Measured 2026-09-17: without this, 8 of 10 calls in one run were lost to a
    per-minute token ceiling, each one carrying the provider's own statement of how
    long to wait. The run wrote nothing and reported nothing usable.
    """
    attempt = 0
    while True:
        try:
            return complete(prompt, model)
        except RuntimeError as exc:
            wait = retry_after_seconds(str(exc))
            if wait is None or attempt >= retries:
                raise
            attempt += 1
            print(f"    rate limited, waiting {wait:.1f}s "
                  f"(attempt {attempt}/{retries})", file=sys.stderr)
            sleep(wait)


def complete(prompt: str, model: str | None = None) -> str:
    """One call through bin/ai. Raises RuntimeError with what actually failed."""
    if not AI.is_file():
        raise RuntimeError(
            f"no bin/ai found (searched up from {HERE} to {HERE.parents[-1]}); "
            "this script deliberately has no model client of its own")
    cmd = [sys.executable, str(AI), "--json"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise RuntimeError("bin/ai timed out after 300s")
    if not proc.stdout.strip():
        raise RuntimeError(f"bin/ai printed nothing (exit {proc.returncode}): "
                           f"{(proc.stderr or '').strip()[:200]}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"bin/ai did not return JSON: {proc.stdout.strip()[:200]}")
    if not envelope.get("ok"):
        raise RuntimeError(f"model call failed: {envelope.get('error', 'unknown error')}")
    return str(envelope.get("reply") or "")


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="outreach_agent",
        description="Draft (never send) tailored outreach for leads in LEADS.md.")
    parser.add_argument("--about", default=None,
                        help="one paragraph on what you actually offer (required to draft)")
    parser.add_argument("--about-file", default=None, help="read that paragraph from a file")
    parser.add_argument("--model", "-m", default=None, help="preset name or provider::model")
    parser.add_argument("--limit", type=int, default=10, help="max drafts this run (default 10)")
    parser.add_argument("--match", action="append", default=[], metavar="TEXT",
                        help="only consider titles containing TEXT (repeatable)")
    parser.add_argument("--evidence-ledger", default=None, metavar="DIR",
                        help="read bounded, registry-admitted evidence from a Foxwood "
                             "ledger directory and give it to the model as citations "
                             "for the offer; omitted means no change to the prompt")
    parser.add_argument("--evidence-claim", action="append", dest="evidence_claims",
                        default=[], metavar="CLAIM_ID",
                        help="claim IDs to use from that ledger (repeatable; omitted means "
                             f"the most recent {EVIDENCE_LIMIT_DEFAULT})")
    parser.add_argument("--evidence-limit", type=int, default=EVIDENCE_LIMIT_DEFAULT,
                        help=f"how many of the most recent claims to use when no "
                             f"--evidence-claim is given (default {EVIDENCE_LIMIT_DEFAULT})")
    parser.add_argument("--seed-ledger", default=None, metavar="DIR",
                        help="write each lead this run will draft into a Foxwood ledger "
                             "as a citable source, and hand that draft its own post; "
                             "does nothing for leads already drafted or refused")
    parser.add_argument("--list", action="store_true",
                        help="report who qualifies and who does not, then stop")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the prompts and write nothing; makes no model calls")
    parser.add_argument("--redo", action="store_true",
                        help="ignore what earlier runs answered — both the drafts "
                             "file and .herald_state.json — and go round again")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES,
                        help="retries for a rate-limited call (default 3; a retry "
                             "only happens when the provider says how long to "
                             "wait, never for an account that is out of credit)")
    args = parser.parse_args(argv)

    if not LEADS_FILE.is_file():
        print(f"{LEADS_FILE} not found", file=sys.stderr)
        return 1

    entries = parse_leads(LEADS_FILE.read_text(errors="replace"))
    qualified, rejected = [], []
    for entry in entries:
        ok, reason = qualify(entry)
        (qualified if ok else rejected).append((entry, reason))

    if args.match:
        needles = [needle.lower() for needle in args.match if needle.strip()]
        qualified = [(entry, reason) for entry, reason in qualified
                     if any(needle in entry["title"].lower() for needle in needles)]
        print(f"  title filter: {', '.join(args.match)}")

    print(f"  {len(entries)} entries in LEADS.md, {len(qualified)} qualified to contact")
    for entry, reason in rejected:
        print(f"    skip  {entry['title'][:58]:<58} — {reason}")
    for entry, _ in qualified:
        # Shows the routes that reach a person, plus the employment type the post
        # states. The apply-form links are still in the file and still printed with
        # the draft; they are just not why this entry qualified. The employment label
        # informs and never excludes -- see `employment_type` for why there is no
        # filter here.
        print(f"    lead  [{employment_type(entry['title'])}] "
              f"{entry['title'][:52]:<52} — {', '.join(reachable_of(entry))}")

    # A ledger that was asked for and cannot be read is a broken pipe, and it must
    # not present itself as "no evidence available, carrying on".
    evidence: list[dict] = []
    if args.evidence_ledger:
        if not args.evidence_ledger.strip():
            print("  --evidence-ledger was empty; give a ledger directory or omit it",
                  file=sys.stderr)
            return 2
        try:
            evidence = load_evidence(args.evidence_ledger, args.evidence_claims,
                                     args.evidence_limit)
            print(f"  evidence: {len(evidence)} source line(s) from {len({row['claim_id'] for row in evidence})} claim(s) "
                  f"in {Path(args.evidence_ledger).expanduser()} "
                  f"({' '.join(sorted({row['source_id'] for row in evidence}))})",
                  file=sys.stderr)
        except Exception as exc:
            print(f"  evidence cannot be loaded: {exc}", file=sys.stderr)
            return 2

    if args.list:
        return 0

    about = args.about
    if args.about_file:
        about = Path(args.about_file).expanduser().read_text(errors="replace").strip()
    if not about or not about.strip():
        print("\n  --about is required to draft, and it is the whole point.",
              file=sys.stderr)
        print("  The tool can find who is hiring; it cannot know what you sell.",
              file=sys.stderr)
        print("  Write one honest paragraph, e.g.", file=sys.stderr)
        print("    outreach_agent --about \"I do X for Y, and I charge Z.\"",
              file=sys.stderr)
        return 2

    if not qualified:
        print("\n  nothing to draft: no entry in LEADS.md is both hiring and "
              "contactable.")
        print("  Run monitor_leads.py once Reddit stops answering 429.")
        return 0

    state = load_state(STATE_FILE)
    known = set() if args.redo else drafted_sources(
        DRAFTS_FILE.read_text(errors="replace") if DRAFTS_FILE.is_file() else "")
    resolved = set() if args.redo else {
        src for src, record in state.items()
        if isinstance(record, dict) and record.get("verdict") in RESOLVED_VERDICTS}
    sources = {source_of(e) for e, _ in qualified}
    done_drafted = sources & known
    done_resolved = sources & resolved
    # This is the whole of "resumable". Without it the batch restarts at the first
    # unrefused lead and spends its limit on leads it has already refused twice.
    todo = [e for e, _ in qualified
            if source_of(e) not in done_drafted and source_of(e) not in done_resolved]
    if done_drafted or done_resolved:
        print(f"  already answered: {len(done_drafted)} drafted, "
              f"{len(done_resolved)} refused on an earlier run — skipped "
              f"(--redo to redo)")
    todo = todo[: max(0, args.limit)]

    # Seeded evidence is per lead, not per run. The post being answered differs for
    # every draft, so it is kept keyed by source URL and attached per entry below --
    # handing every draft the same list of posts would have each pitch mention three
    # strangers' threads, which is worse than citing nothing.
    seeded: dict[str, str] = {}
    thread_rows: dict[str, dict] = {}
    if args.seed_ledger:
        if not args.seed_ledger.strip():
            print("  --seed-ledger was empty; give a ledger directory or omit it",
                  file=sys.stderr)
            return 2
        try:
            import lead_evidence
        except Exception as exc:
            print(f"  lead_evidence is not importable: {exc}", file=sys.stderr)
            return 2

        # --dry-run writes nothing, and that includes the ledger. Seeding into the
        # operator's directory during a dry run would make the one command whose
        # whole contract is "nothing is written" the command that writes the most.
        # A scratch directory still answers the question the dry run is asking --
        # what the prompt will actually say -- and the rows are read into memory
        # before it goes away.
        scratch = tempfile.TemporaryDirectory() if args.dry_run else None
        target = Path(scratch.name) if scratch is not None else args.seed_ledger
        try:
            seeded, skipped = lead_evidence.seed_ledger(todo, target)
            # Only read back when something was written. Calling load_evidence with an
            # empty source_ids falls through to the claims path and asks a question
            # about a ledger of leads -- which has no claims by construction -- and it
            # refuses, correctly. An unseeded run is not a broken pipe, so it must not
            # be made to look like one.
            if seeded:
                thread_rows = {row["source_id"]: row for row in load_evidence(
                    target, source_ids=list(seeded.values()))}
        except Exception as exc:
            print(f"  leads cannot be seeded into the ledger: {exc}", file=sys.stderr)
            return 2
        finally:
            if scratch is not None:
                scratch.cleanup()

        where = ("a scratch directory (dry run writes nothing)" if scratch is not None
                 else str(Path(args.seed_ledger).expanduser()))
        print(f"  seeded {len(seeded)} of {len(todo)} lead(s) into {where} "
              f"as citable evidence"
              + (f"; {skipped} skipped (no citable text or no link)" if skipped else ""),
              file=sys.stderr)

    def evidence_for(entry: dict) -> list[dict]:
        """Run-wide artifacts, plus this lead's own post when it was seeded.

        A lead that was skipped by the seeder gets no thread row and is not a
        failure: it falls back to exactly the prompt it would have had without
        --seed-ledger. The alternative -- a draft that cites a post it was not
        answering -- is the one outcome this must not produce.
        """
        rows = list(evidence)
        row = thread_rows.get(seeded.get(source_of(entry), ""))
        return rows + [row] if row else rows

    if args.dry_run:
        for entry in todo:
            print(f"\n--- prompt for {entry['title'][:60]} ---")
            print(build_prompt(entry, about, evidence_for(entry)))
        print(f"\ndry run: {len(todo)} prompt(s); nothing called, nothing written")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks, refusals, malformed, failures = [], [], [], 0
    verdicts_now: dict[str, dict] = {}
    for entry in todo:
        source = source_of(entry)
        try:
            reply = complete_with_retries(build_prompt(entry, about, evidence_for(entry)),
                                          args.model, args.retries)
        except RuntimeError as exc:
            failures += 1
            # Recorded for the report, and deliberately *not* treated as resolved: a
            # transport failure says nothing about the lead, so the next batch may
            # still try it again.
            verdicts_now[source] = {"verdict": "failed", "at": now,
                                    "why": str(exc)[:200]}
            print(f"    failed  {entry['title'][:52]:<52} — {exc}", file=sys.stderr)
            continue
        subject, body = split_subject(reply)
        if body.strip().upper().startswith("NO FIT"):
            # The model exercised its one escape hatch. Kept in the report rather
            # than written as a draft: a refused pitch is a finding, not copy.
            refusals.append(f"{entry['title'][:70]} — {body.strip()}")
            verdicts_now[source] = {"verdict": "no_fit", "at": now,
                                    "why": body.strip()[:200]}
            print(f"    no fit  {entry['title'][:52]}")
            continue
        # A reply that is not an email must not become a draft, and must not be
        # counted as one. Its own category, for the reason in the module docstring.
        why = not_an_email(subject, body)
        if why:
            malformed.append(f"{entry['title'][:70]} — {why}")
            verdicts_now[source] = {"verdict": "malformed", "at": now, "why": why}
            print(f"    bad     {entry['title'][:52]} — {why}")
            continue
        blocks.append(render(entry, subject, body, now, evidence=evidence_for(entry)))
        # What the pitch rested on is recoverable from OUTREACH_DRAFTS.md and is not
        # an opinion about the lead, so it is kept in the memory that makes this
        # batched tool resumable: changing the evidence needs --redo, same as changing
        # the offer, or the new question would be answered with the old evidence.
        #
        # Read from `evidence_for`, not from the run-wide list: with --seed-ledger each
        # draft carries its own post, so recording the run-wide list would say a draft
        # rested on evidence this one was never shown. The blank claim on a thread row
        # is filtered rather than recorded as "".
        rows_used = evidence_for(entry)
        evidence_ids = sorted({row["source_id"] for row in rows_used})
        evidence_claims = sorted({row["claim_id"] for row in rows_used if row["claim_id"]})
        verdicts_now[source] = {"verdict": "drafted", "at": now, "why": subject,
                                "evidence": evidence_ids, "claims": evidence_claims}
        print(f"    drafted {entry['title'][:52]}")

    # Saved before the drafts are written, so that a batch stopping at its limit -- or
    # a run killed from outside -- still remembers what it answered. That memory is
    # the only thing that lets the *next* batch advance.
    if verdicts_now:
        save_state(STATE_FILE, {**state, **verdicts_now})

    for line in refusals:
        print(f"    (no fit: {line})")
    for line in malformed:
        print(f"    (not written: {line})")

    if todo:
        # Printed before the early returns below, because a run in which everything
        # was refused is the common case and is exactly when you need to know the
        # next batch will move on rather than repeat.
        print(f"  {len(todo)} lead(s) attempted this run; answers remembered in "
              f"{STATE_FILE.name}, so the next batch continues from here.")

    if not blocks:
        if failures:
            print(f"all {failures} model calls failed; nothing written", file=sys.stderr)
            return 1
        if malformed and not refusals:
            # Every reply was the wrong kind of output. Exiting 0 here would
            # report a broken pipeline as a successful run that found nothing.
            print(f"no usable replies: {len(malformed)} were not emails; "
                  "nothing written", file=sys.stderr)
            return 1
        print("no drafts produced")
        return 0

    existed = DRAFTS_FILE.is_file()
    with DRAFTS_FILE.open("a", encoding="utf-8") as handle:
        if not existed:
            handle.write(HEADER)
        for block in blocks:
            handle.write(block)
    print(f"\nappended {len(blocks)} draft(s) to {DRAFTS_FILE}")
    print("  read them, then send the ones that are true. Nothing was sent.")
    if refusals:
        print(f"  {len(refusals)} lead(s) reported no fit and were not written.")
    if malformed:
        print(f"  {len(malformed)} reply(ies) were not emails and were not written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
