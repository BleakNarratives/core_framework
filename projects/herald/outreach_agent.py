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

Usage:
    outreach_agent --list                       who qualifies, and who does not
    outreach_agent --about-file ABOUT.md             draft for everyone qualified
    outreach_agent --about-file ABOUT.md --dry-run   show prompts; call nothing
    outreach_agent --about-file ABOUT.md --limit 3   cap drafts this run
    outreach_agent --about-file ABOUT.md --redo      re-draft already-drafted leads

  --about is required for drafting on purpose. It is your one paragraph of what
  you actually offer; the model tailors it per lead but may not invent beyond it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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


def build_prompt(entry: dict, about: str) -> str:
    """The whole prompt, and the constraints are the interesting part.

    Three of these rules exist because a model writing sales copy will otherwise
    invent things: credentials, familiarity with the poster, or a claim that the
    post asked for something it did not. The last rule is the important one -- it
    gives the model permission to say the two of you do not match, which is the
    answer you actually want on most of these.
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


def render(entry: dict, subject: str, body: str, now: str) -> str:
    """One draft block. Records the send route, and says plainly if there is none.

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

    if args.dry_run:
        for entry in todo:
            print(f"\n--- prompt for {entry['title'][:60]} ---")
            print(build_prompt(entry, about))
        print(f"\ndry run: {len(todo)} prompt(s); nothing called, nothing written")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blocks, refusals, malformed, failures = [], [], [], 0
    verdicts_now: dict[str, dict] = {}
    for entry in todo:
        source = source_of(entry)
        try:
            reply = complete_with_retries(build_prompt(entry, about), args.model,
                                          args.retries)
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
        blocks.append(render(entry, subject, body, now))
        verdicts_now[source] = {"verdict": "drafted", "at": now, "why": subject}
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
