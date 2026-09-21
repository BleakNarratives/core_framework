"""lead_evidence — a lead's own post, as evidence you can cite back at them.

WHY THIS EXISTS
  Herald could find who was hiring and it could draft a pitch, but the pitch could
  only ever talk about the operator. The strongest honest sentence in an outreach
  email is the one that answers the thing the poster actually wrote, and until now
  the draft had no way to point at it. This writes the post into a Foxwood ledger as
  a source, so the same citation-gated path that serves research serves outreach.

WHY THE POST IS NOT A CLAIM
  Foxwood's contract is that a claim needs a source. A lead post is the inverse: the
  post *is* the evidence, and requiring a claim first would mean manufacturing one
  about a stranger. So these are admitted as sources and cited as sources, which is
  why `load_evidence` grew a source-keyed path rather than this module inventing a
  second row shape.

WHAT A LEAD ACTUALLY GIVES YOU AS EVIDENCE, WHICH IS LESS THAN IT SOUNDS
  `monitor_leads.render` writes title, Link, Matched, Contact and Posted -- it does
  not write the post body. So for an entry read back out of LEADS.md the only text
  the poster wrote that survives in the file is the *title*. That is thin, and this
  module does not paper over it: the title is the excerpt, and the thread link is
  what a draft points at. An entry with neither is skipped rather than stored as a
  stub, and the skip count is returned so a run that stored nothing cannot look like
  a run that stored everything. When a caller has the real body in hand -- the
  scanners build one before they render the file -- it is used and clipped instead.

TWO THINGS IT REFUSES TO DO
  One, it does not store contact details. The repository's own .gitignore already
  says it is not the right place to keep a list of strangers' addresses; a ledger
  seeded from leads would walk that decision back one layer down, and the ledger
  travels further than the leads file does. The `Contact:` hints are the leads
  file's business and are not copied, because the excerpt is built from the post
  text and never from the field bookkeeping around it.

  Two, it does not store anything the registry blocks. Sources are written through
  the same PROVENANCE.md gate the reader uses, so seeding cannot become the way to
  get quarantined material into a prompt by a side door.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# A post is a few hundred words. This is the same bounded-payload stance as Scout's
# fetch cap and the pipe's excerpt cap: a lead is evidence, and evidence has a size.
MAX_EXCERPT_CHARS = 2000

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HINT_RE = re.compile(r"\b(?:email|dm|apply|profile|venue|link):\S+", re.IGNORECASE)

PII_PLACEHOLDER = "[contact detail removed]"


def herald():
    """The loaded outreach_agent, whether this was imported or run as a script.

    `python outreach_agent.py` puts that file in sys.modules as __main__, not under
    its own name, so a plain `import outreach_agent` from a module it calls would
    load a *second* copy of it: same source, two module objects, two `AI` paths, two
    sets of constants. It would work, and it would be the kind of difference nobody
    finds by reading either file. So the already-loaded module is preferred, and the
    file is only re-imported when nothing has loaded it yet.
    """
    module = sys.modules.get("outreach_agent")
    if module is not None:
        return module
    running = sys.modules.get("__main__")
    if running is not None and getattr(running, "__file__", None):
        if Path(running.__file__).resolve() == (HERE / "outreach_agent.py").resolve():
            return running
    sys.path.insert(0, str(HERE))
    import outreach_agent as module  # noqa: E402
    return module


def strip_pii(text: str) -> str:
    """Remove anything that identifies a person by address, before storage.

    Deliberately narrow: addresses and stored contact hints go, the username and
    thread link stay. Stripping identity wholesale would break the only two things
    a draft needs, and a redaction so aggressive it removes the post's meaning is a
    redaction an operator turns off.

    One pass over merged spans, not two sequential substitutions. `email:x@y.test`
    matches both patterns -- the hint rule covers the address rule's own match -- and
    running them one after the other re-matched the placeholder the first pass had
    just written, turning one address into `[contact detail removed] detail removed]`.
    Overlapping matches are merged first so each redaction site is replaced once.
    """
    text = text or ""
    spans = [match.span() for pattern in (EMAIL_RE, HINT_RE)
             for match in pattern.finditer(text)]
    if not spans:
        return text
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pieces: list[str] = []
    cursor = 0
    for start, end in merged:
        pieces.append(text[cursor:start])
        pieces.append(PII_PLACEHOLDER)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def normalize(entry: dict) -> dict:
    """Either entry shape -> the fields a ledger source needs.

    Two shapes reach this function and they are not the same shape: LEADS.md rounds
    an entry to `{"who", "title", "fields"}`, while the scanners hold
    `{"title", "url", "body", ...}` in memory before rendering. Reading only the
    first is what makes "the post body" look like a field that was always there.
    """
    fields = entry.get("fields") or {}
    url = ""
    if isinstance(fields, dict):
        for key in ("Link", "URL"):
            if fields.get(key):
                url = str(fields[key]).strip()
                break
    if not url:
        url = str(entry.get("url") or "").strip()
    title = str(entry.get("title") or "").strip()
    body = str(entry.get("body") or "").strip()
    return {
        "title": title,
        "url": url,
        "text": body or title,
        "publisher": str(entry.get("source") or "lead").strip() or "lead",
    }


def excerpt_for(entry: dict) -> str:
    """The citable text: the post if the caller has it, else the title, de-identified.

    Empty means this entry is not evidence. That happens for real -- an entry whose
    title is blank and whose body was never captured -- and the caller skips it
    loudly rather than writing a source with nothing in it.
    """
    return strip_pii(normalize(entry)["text"]).strip()[:MAX_EXCERPT_CHARS]


def seed_ledger(entries, ledger_dir, *, registry=None, repo_root=None):
    """Write leads into a Foxwood ledger. Returns ({url: source_id}, skipped count).

    Keyed by URL rather than returned as a bare list, because the caller's next move
    is to give one specific draft the one specific post it is answering -- and a list
    that has silently skipped an entry cannot be zipped against the entries it came
    from.

    Skips are counted, never swallowed: an entry with no citable text or no thread
    link is not evidence, and a run that stored nothing must not read like a run that
    stored everything.
    """
    oa = herald()
    root = Path(repo_root).expanduser() if repo_root else oa.find_repo_root()
    if root is None:
        raise RuntimeError(
            "no repository root found (looking for PROVENANCE.md and "
            "src/foxwood_research); a Foxwood ledger cannot be created without both")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from src.foxwood_research import RegistryGate, ResearchLedger
    except Exception as exc:
        raise RuntimeError(f"Foxwood is not importable from {root}: {exc}") from exc

    # Writes go through the same gate the reader uses. A read-only gate would leave
    # seeding as the way around it.
    gate = registry if registry is not None else RegistryGate()
    ledger = ResearchLedger(Path(ledger_dir).expanduser(), admit=gate.admit)

    written: dict[str, str] = {}
    skipped = 0
    for entry in entries or ():
        fields = normalize(entry)
        excerpt = excerpt_for(entry)
        if not excerpt or not fields["url"]:
            skipped += 1
            continue
        record = ledger.add_source(
            title=fields["title"][:200] or "(untitled)",
            url=fields["url"],
            publisher=fields["publisher"],
            excerpt=excerpt,
            license_note="public forum post; quoted for a private draft, not redistributed",
            origin=f"herald:lead:{fields['url']}",
        )
        written[fields["url"]] = record.source_id
    return written, skipped
