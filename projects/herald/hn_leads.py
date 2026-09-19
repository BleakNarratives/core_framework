#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: monetization
# DEPS: stdlib only; imports monitor_leads for the shared filter + renderer
# ROLE: Pull the monthly HN "Who is hiring?" thread into LEADS.md
# AUTHOR: Bleak
# SESSION: 2026-09-17
# TIER: 4
# [/DNA_TAG]

"""hn_leads — Hacker News' monthly "Who is hiring?" thread, as contactable leads.

WHY THIS REPLACED THE SHOW HN SCAN
  The previous version queried for stories mentioning agents, codebases and
  technical debt, then wrote the top ten into LEADS.md. What that returns is
  Show HN *launch* posts — other people's products. The two it actually produced
  were "Resolv – AI Agentic IDE" and "TheAuditor v2.0": competitors, not buyers.
  outreach_agent refused both, correctly, as "not a hiring post".

  An HN post is only a lead if HN is where the work is offered. That is exactly
  one place: the monthly "Who is hiring?" thread, posted by the `whoishiring`
  account, where every top-level comment is a company advertising an open role.

WHY IT BEATS THE REDDIT SOURCE
  The HN source is paginated and exposes structured comments, author names, and
  contact hints; the parser reports email, person-reachable, and application-form
  counts separately. The for-hire subreddits publish an address roughly never —
  the only route there is a DM. Algolia is exercised through offline fixtures in
  the test suite; live Reddit access is currently rate-limited on this host.

WHAT THIS INHERITS
  The contact extraction, dedupe and renderer are imported from monitor_leads
  rather than reimplemented, so both sources write one entry shape and
  outreach_agent does not need to know which produced it. The source-level
  hiring signal is the thread itself, so `matched` is set here rather than
  detected from a `[HIRING]` tag.

Usage:
    hn_leads --dry-run            report what would be added; write nothing
    hn_leads                      fetch the current thread and append
    hn_leads --require-contact    only posts that publish a way to reach them
    hn_leads --limit 10           cap entries this run (default 25)
    hn_leads --thread 49522897    pin a specific thread, for backfilling a month
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET  # noqa: F401  (kept for parity with monitor_leads errors)
from datetime import datetime, timezone
from pathlib import Path

# Run from a checkout, from cron, or imported by a test: the shared helpers live
# beside this file, so put that directory on the path explicitly rather than
# relying on the caller's working directory.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from monitor_leads import (  # noqa: E402
    LEADS_FILE,
    contact_hints,
    hrefs,
    new_entries,
    normalize_url,
    plain_text,
    reaches_a_person,
    render,
    urls_in,
)

API = "https://hn.algolia.com/api/v1"
USER_AGENT = "hn_leads/2.0 (personal feed reader; stdlib urllib)"
PAGE_SIZE = 200       # Algolia's practical page size for this index
MAX_PAGES = 6         # a month's thread is ~400 comments; this covers it
MATCH = "who-is-hiring"

# The `whoishiring` account's own first comment on each thread is the rules
# boilerplate ("Please state the location..."), not a job. Excluded by author.
OP_AUTHOR = "whoishiring"

# HN identities live in the query string, which is a problem: normalize_url()
# deliberately drops queries, so every news.ycombinator.com/item?id=N collapses
# to one identical key. Measured 2026-09-17 -- that made 263 real job posts
# deduplicate down to a single recorded entry, silently, because a collapse looks
# exactly like "already seen". So HN keys on the item id itself.
HN_ITEM_RE = re.compile(r"[?&]id=(\d+)")


# ── transport ────────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 30) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def find_thread() -> dict:
    """The most recent "Who is hiring?" story.

    Sorted by date, not relevance. `search` ranks by relevance and returns
    threads from 2015 — which is how the first version of this query silently
    produced five-year-old job posts as though they were current.
    """
    body = _get(f"{API}/search_by_date"
                f"?tags=story,author_{OP_AUTHOR}&hitsPerPage=20")
    for hit in body.get("hits") or []:
        title = (hit.get("title") or "")
        if "who is hiring" in title.lower():
            return hit
    raise RuntimeError("no 'Who is hiring?' story in the last 20 posts by "
                       f"{OP_AUTHOR} — the format may have changed")


def fetch_comments(story_id: str) -> list[dict]:
    """Every comment on the thread, paginated.

    Algolia caps a single response, so a one-page fetch can return a silent
    subset — the failure mode where a list looks complete and is not. Pagination
    stops at the API-reported page count, bounded by `MAX_PAGES`.
    """
    out: list[dict] = []
    page = 0
    while page < MAX_PAGES:
        body = _get(f"{API}/search?tags=comment,story_{story_id}"
                    f"&hitsPerPage={PAGE_SIZE}&page={page}")
        out.extend(body.get("hits") or [])
        if page + 1 >= (body.get("nbPages") or 1):
            break
        page += 1
    return out


# ── pure helpers (no network) ────────────────────────────────────────────────

def first_line(text: str, limit: int = 120) -> str:
    """The post's opening line, which is where the role and company go.

    The thread's convention is `Company | Role | Location | Salary`, but it is a
    convention and not enforced, so this takes whatever the first line is rather
    than pretending to parse fields that are not reliably there.
    """
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:limit]
    return "(no text)"


def hn_ids_in(text: str) -> set[str]:
    """HN item ids already recorded in a LEADS.md, in this file's uid form.

    Needed because `urls_in()` returns normalize_url() output, which has no query
    string left, so it can never match a `hn:<id>` key. Both sets are unioned at
    the call site.
    """
    return {f"hn:{match}" for match in HN_ITEM_RE.findall(text or "")}


def has_email(entry: dict) -> bool:
    return any(c.startswith("email:") for c in entry.get("contact") or [])


def is_job_post(hit: dict, story_id: str) -> bool:
    """Top-level only, and not the thread's own rules comment.

    Nested replies are discussion *about* a job, sometimes hostile, sometimes
    another company replying. Sending outreach to those would be both wrong and
    embarrassing.
    """
    if str(hit.get("parent_id")) != str(story_id):
        return False
    if hit.get("author") == OP_AUTHOR:
        return False
    return bool(hit.get("comment_text"))


def to_entry(hit: dict, source: str) -> dict:
    """An Algolia comment -> the same entry shape monitor_leads writes."""
    body = plain_text(hit.get("comment_text") or "")
    item = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
    entry = {
        "source": source,
        "title": first_line(body),
        "url": item,
        "author": hit.get("author") or "unknown",
        "published": hit.get("created_at") or "",
        # The item id IS the identity. An HN comment can be edited, and the id
        # cannot; and the id must not be routed through normalize_url(), which
        # would strip it and collapse every post onto one key.
        "uid": f"hn:{hit.get('objectID')}",
        "body": body,
        "links": hrefs(hit.get("comment_text") or ""),
        "matched": MATCH,
    }
    entry["contact"] = contact_hints(entry)
    return entry


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hn_leads",
        description="Append the current HN 'Who is hiring?' posts to LEADS.md.")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be added and write nothing")
    parser.add_argument("--limit", type=int, default=25,
                        help="max new entries to add (default 25)")
    parser.add_argument("--require-contact", action="store_true",
                        help="keep only posts that publish a way to reach them")
    parser.add_argument("--require-email", action="store_true",
                        help="keep only posts with a real address; a careers link "
                             "is an application form, not a contact")
    parser.add_argument("--thread", default=None,
                        help="pin a specific thread id instead of the current one")
    args = parser.parse_args(argv)

    try:
        thread = ({"objectID": args.thread, "title": f"HN thread {args.thread}"}
                  if args.thread else find_thread())
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"  could not find the thread: {exc}", file=sys.stderr)
        return 1
    story_id = str(thread["objectID"])
    source = f"HN — {thread.get('title', story_id)}"

    try:
        hits = fetch_comments(story_id)
    except urllib.error.URLError as exc:
        print(f"  could not fetch comments: {exc}", file=sys.stderr)
        return 1

    posts = [h for h in hits if is_job_post(h, story_id)]
    entries = [to_entry(h, source) for h in posts]
    # Three numbers, reported separately and always. Conflating them reads as "250
    # people you can email", when a large share of those published nothing but an
    # application form on a company ATS. The gap between "reachable" and "any
    # route" is the honest measure of this source, and it was 55-vs-a-lot wrong
    # before the apply-form rule existed.
    with_email = sum(1 for e in entries if has_email(e))
    with_any = sum(1 for e in entries if e["contact"])
    with_person = sum(1 for e in entries
                      if any(reaches_a_person(c) for c in e["contact"]))
    reachable = (lambda e: any(reaches_a_person(c) for c in e["contact"]))
    if args.require_email:
        entries = [e for e in entries if has_email(e)]
    elif args.require_contact:
        # A form is not a way to reach somebody, so this keeps only the routes a
        # person can actually be written to.
        entries = [e for e in entries if reachable(e)]

    already = LEADS_FILE.read_text(errors="replace") if LEADS_FILE.is_file() else ""
    known = urls_in(already) | hn_ids_in(already)
    fresh = new_entries(entries, known)[: max(0, args.limit)]

    print(f"  {source}")
    print(f"  {len(hits)} comments, {len(posts)} top-level job posts")
    print(f"  {with_email} publish an email, {with_person} reach a person, "
          f"{with_any} published some route ({with_any - with_person} apply-form "
          f"only), {len(fresh)} new")
    if not fresh:
        print("nothing new; LEADS.md untouched")
        return 0

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    section = render(source, fresh, now)

    if args.dry_run:
        print(f"dry run: would append {len(fresh)} entries to {LEADS_FILE}")
        print(section.rstrip())
        return 0

    existed = LEADS_FILE.is_file()
    with LEADS_FILE.open("a", encoding="utf-8") as handle:
        if not existed:
            from monitor_leads import HEADER
            handle.write(HEADER)
        handle.write(section)
    print(f"appended {len(fresh)} entries to {LEADS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
