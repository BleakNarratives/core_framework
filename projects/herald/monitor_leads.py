#!/usr/bin/env python3

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: monetization
# DEPS: stdlib only
# ROLE: Pull new RSS/Atom feed entries into LEADS.md
# AUTHOR: Bleak
# SESSION: 2026-09-16
# TIER: 4
# [/DNA_TAG]

"""monitor_leads — append genuinely new feed entries to LEADS.md.

WHY THIS WAS REWRITTEN
  The previous version never parsed the feed. It issued a GET, then wrote the
  *search URL* into LEADS.md as though it were a lead, under a comment that said
  so out loud ("Simple simulation of processing (in a real env, use feedparser)").
  The output was a bookmark with a timestamp. It also imported `requests`, which
  is not stdlib, for a job urllib does.

  Now: stdlib only, real Atom parsing, and the only thing written is an entry
  that actually exists in the feed -- title, author, permalink, date -- deduped
  against every URL already in the file. Re-running it adds nothing.

WHY THE SOURCE CHANGED (same day)
  The feeds were Reddit's `search.rss`. Once parsing worked it was obvious what
  they actually return: a site-wide OR of the query terms, plus subreddit hits
  from 2008. One run produced r/wallstreetbets, r/probation and r/residentevil.
  The scoping simply is not there, so the tool recorded noise faithfully -- which
  is better than recording bookmarks, but it is not a filter.

  Each feed is now a subreddit's `/new.rss`: the real, current, complete post
  list, and the relevance decision is made locally, deterministically, offline.

WHY THE TARGETS ARE HIRING SUBS
  r/ChatGPTCoding and r/cursor produce conversations about coding agents. Nobody
there is posting paid work. r/forhire and r/freelance_forhire are where the work
actually gets posted, and the tag does the filtering: r/forhire requires a
`[HIRING]` or `[FOR HIRE]` tag in the title, enforced by the subreddit.

  That distinction is the whole feature. `[HIRING]` is someone with work and a
  budget. `[FOR HIRE]` is a freelancer advertising themselves, which is the
  opposite of a lead, so it is excluded by name rather than left to a keyword.

  Contact details are extracted where the poster published them -- an email, an
  external link, or an explicit "DM me" -- and recorded on the entry.
  `--require-contact` keeps only posts that have one. Expect it to discard a lot:
  most posters say "DM me", which is a route to a pseudonym, not an address.

WHAT THIS IS STILL NOT
  A pipeline. A `[HIRING]` post is a real person with real work and a real
  budget, which is closer to a lead than anything else in this repo's lead
  tooling has come. But Reddit is pseudonymous: what you get is a username and
  whatever the poster chose to publish. Plenty of posts carry nothing but "DM
  me", which is a route to a pseudonym rather than an address. The file now says
  which is which instead of implying every entry is contactable.

Usage:
    monitor_leads                    fetch and append anything new
    monitor_leads --dry-run          report what would be added; write nothing
    monitor_leads --limit 5          cap new entries per feed
    monitor_leads --require-contact  only posts that publish a way to reach them
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

# Next to this script rather than next to the current directory: a cron job
# running from / should not leave a LEADS.md in /.
LEADS_FILE = Path(__file__).resolve().parent / "LEADS.md"

# Reddit answers 403 to a default or absent User-Agent. Naming the tool and
# offering a contact is both what their docs ask for and what gets a 200.
USER_AGENT = "monitor_leads/2.0 (personal feed reader; stdlib urllib)"

# Reddit rate-limits this host hard, and the limit is NOT per-run. Measured
# 2026-09-16: both subreddit feeds returned 429 in both orders, and a fresh
# request after a 30s wait was refused too. So this gap is politeness, and it
# does not reset the limit. A skipped feed is reported, never silently dropped.
FEED_DELAY_SECONDS = 2.0

ATOM = "{http://www.w3.org/2005/Atom}"
URL_RE = re.compile(r"https?://[^\s)\]<>\"']+")

# Subreddit /new.rss, not /search.rss. A search feed is scoped by the server, and
# the server does not scope it the way the query reads; /new.rss is the honest,
# complete, current list. Filtering it is our job, not the API's.
#
# These are the subs where paid work is posted, not the ones where coding agents
# are discussed. That difference is the point of the whole tool.
FEEDS = [
    {
        "name": "Reddit r/forhire — new",
        "url": "https://www.reddit.com/r/forhire/new.rss",
    },
    {
        "name": "Reddit r/freelance_forhire — new",
        "url": "https://www.reddit.com/r/freelance_forhire/new.rss",
    },
]

# `[HIRING]` is someone with work and a budget. `[FOR HIRE]` is a freelancer
# advertising themselves -- the opposite of a lead -- so the offering tag is
# excluded by name rather than left to a keyword. A loose `hiring` substring
# would happily admit "[FOR HIRE] dev, open to hiring managers".
HIRING_RE = re.compile(r"\[\s*hiring\s*\]|\bhiring\b", re.I)
OFFERING_RE = re.compile(r"\[\s*(?:for\s*hire|offering)\s*\]", re.I)

# Contact detail lives in the post body, which arrives as HTML.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
DM_RE = re.compile(r"\b(?:dm|d\.m\.|pm)\b|\bmessage me\b|\breach out\b|\bcontact me\b", re.I)
HREF_RE = re.compile(r'href="([^"]+)"')
# The permalink is already on every entry, so a Reddit URL in the body is not
# contact information -- it is the same thread again.
REDDIT_URL_RE = re.compile(r"https?://(?:[a-z0-9-]+\.)*reddit\.com|https?://redd\.it",
                           re.I)

HEADER = """# LEADS — posts with paid work, and what they published to reach them

Appended by `monitor_leads.py` (r/forhire, r/freelance_forhire) and `hn_leads.py`.
Newest at the bottom.

**Read the Contact line before treating an entry as a lead.** `[HIRING]` means
someone with work and a budget, which is real. But Reddit is pseudonymous: most
posts publish no address at all, and `dm` means the only route is the permalink
above. `email:` can be written to today; `link:` is a venue; nothing is a thread.
The absence of contact details is itself the finding, and it says so rather than
leaving you to assume every entry is contactable.
"""


# ── pure helpers (no network) ────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Compare URLs the way a person reads them: ignore the fragment, the query
    and a trailing slash.

    Reddit permalinks are stable across re-crawls; the tracking query string on
    them is not. Stripping it is what makes a second run a no-op instead of a
    duplicate.
    """
    text = (url or "").strip().rstrip(".,;")
    parts = urlsplit(text)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/"), "", ""))


def urls_in(text: str) -> set[str]:
    """Every URL already recorded in a LEADS.md, normalized."""
    return {normalize_url(u) for u in URL_RE.findall(text or "")}


def parse_atom(xml_bytes: bytes, source: str) -> list[dict]:
    """Parse an Atom feed into entries. Raises ET.ParseError on junk.

    Reddit serves Atom for .rss. Handles the link element properly: it is an
    attribute (`href`), not text like RSS, and a feed can carry several links,
    so `rel="alternate"` is the one a reader wants.
    """
    root = ET.fromstring(xml_bytes)
    entries: list[dict] = []
    for node in root.iter(f"{ATOM}entry"):
        link = ""
        for candidate in node.findall(f"{ATOM}link"):
            if candidate.get("rel") in (None, "alternate"):
                link = candidate.get("href") or ""
                break
        author = (node.findtext(f"{ATOM}author/{ATOM}name") or "").strip().lstrip("/")
        # Reddit puts the post body in <content>. Its href targets are the only
        # structured contact detail a feed offers, so they are taken before the
        # tags are stripped and the URLs are lost.
        content = (node.findtext(f"{ATOM}content")
                   or node.findtext(f"{ATOM}summary") or "")
        entries.append({
            "source": source,
            "title": (node.findtext(f"{ATOM}title") or "(untitled)").strip(),
            "url": link,
            "author": author or "unknown",
            "published": (node.findtext(f"{ATOM}published")
                          or node.findtext(f"{ATOM}updated") or "").strip(),
            "uid": normalize_url(link) or (node.findtext(f"{ATOM}id") or "").strip(),
            "body": plain_text(content),
            "links": hrefs(content),
        })
    return entries


def plain_text(html: str) -> str:
    """Feed HTML reduced to text, so a contact detail can be found with a regex."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html or "")).split())


def hrefs(html: str) -> list[str]:
    """The href targets in feed HTML, captured before tag-stripping loses them."""
    return [unescape(h) for h in HREF_RE.findall(html or "")]


def is_hiring(entry: dict) -> tuple[bool, str]:
    """Someone with paid work, or a freelancer advertising themselves?

    Returns (kept, the tag that admitted it). Returning the tag is the point: a
    filter that silently discards most of a feed has to be auditable, or you
    cannot tell a working filter from a broken one. It is written into LEADS.md.

    The offering check runs first and wins outright, so `[FOR HIRE]` cannot slip
    in on a `hiring` substring.
    """
    title = entry.get("title", "")
    if OFFERING_RE.search(title):
        return False, ""
    found = HIRING_RE.search(title)
    return (True, found.group(0).strip().lower()) if found else (False, "")


def contact_hints(entry: dict) -> list[str]:
    """Every way the poster published to reach them, best route first.

    An email can be written to directly; an external link is a venue; an explicit
    "DM me" reaches a pseudonym with no address at all. Reddit's own URLs are
    dropped, because the permalink is already on the entry and a link back to the
    same thread is not contact information.
    """
    body = entry.get("body", "")
    hints = [f"email:{address}" for address in sorted(set(EMAIL_RE.findall(body)))]
    links = {*(entry.get("links") or []), *URL_RE.findall(body)}
    hints += [f"link:{link.rstrip('.,;')}" for link in sorted(links)
              if link and not REDDIT_URL_RE.match(link)]
    if DM_RE.search(body):
        hints.append("dm")
    return hints


def new_entries(entries: list[dict], known: set[str]) -> list[dict]:
    """Entries whose URL is not already recorded, deduped within the batch too.

    `known` is mutated so that two feeds carrying the same thread do not both
    get appended.
    """
    fresh: list[dict] = []
    for entry in entries:
        key = entry["uid"]
        if not key or key in known:
            continue
        known.add(key)
        fresh.append(entry)
    return fresh


def render(source: str, entries: list[dict], now: str) -> str:
    """One dated section, in the same shape the existing file already uses."""
    lines = [f"\n## {source} ({now})\n"]
    for entry in entries:
        lines.append(f"* **[{entry['author']}]** {entry['title']}")
        lines.append(f"  - Link: {entry['url']}")
        if entry.get("matched"):
            lines.append(f"  - Matched: `{entry['matched']}`")
        if entry.get("contact"):
            lines.append(f"  - Contact: {', '.join(entry['contact'])}")
        if entry["published"]:
            lines.append(f"  - Posted: {entry['published']}")
        lines.append("")
    return "\n".join(lines)


# ── io ───────────────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/xml;q=0.9, */*;q=0.1",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="monitor_leads",
        description="Append new RSS/Atom entries to LEADS.md, deduped by URL.")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be added and write nothing")
    parser.add_argument("--limit", type=int, default=25,
                        help="max new entries to add per feed (default 25)")
    parser.add_argument("--require-contact", action="store_true",
                        help="keep only posts that publish a way to reach them")
    args = parser.parse_args(argv)

    known = urls_in(LEADS_FILE.read_text(errors="replace") if LEADS_FILE.is_file() else "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    fresh_total = 0
    failures = 0
    sections: list[str] = []

    for index, feed in enumerate(FEEDS):
        if index:
            time.sleep(FEED_DELAY_SECONDS)
        try:
            entries = parse_atom(fetch(feed["url"]), feed["name"])
        except urllib.error.HTTPError as exc:
            failures += 1
            # Reddit's 429 is the state this tool is most often in, so say what
            # they told us to wait rather than just the number.
            wait = exc.headers.get("Retry-After") if exc.headers else None
            hint = f", Retry-After {wait}s" if wait else ""
            print(f"  {feed['name']}: HTTP {exc.code}{hint} — skipped",
                  file=sys.stderr)
            continue
        except ET.ParseError as exc:
            failures += 1
            print(f"  {feed['name']}: not parseable as Atom ({exc}) — skipped",
                  file=sys.stderr)
            continue
        except Exception as exc:
            failures += 1
            print(f"  {feed['name']}: {type(exc).__name__}: {exc} — skipped",
                  file=sys.stderr)
            continue

        kept: list[dict] = []
        for entry in entries:
            hit, signal = is_hiring(entry)
            if not hit:
                continue
            entry["matched"] = signal
            entry["contact"] = contact_hints(entry)
            kept.append(entry)
        reachable = sum(1 for entry in kept if entry["contact"])
        if args.require_contact:
            kept = [entry for entry in kept if entry["contact"]]
        fresh = new_entries(kept, known)[: max(0, args.limit)]
        fresh_total += len(fresh)
        # Every count is reported separately: "0 new" and "0 hiring" mean very
        # different things, and "hiring but unreachable" is the number that
        # decides whether this source is worth keeping at all.
        print(f"  {feed['name']}: {len(entries)} in feed, {len(kept)} hiring, "
              f"{reachable} with contact, {len(fresh)} new")
        if fresh:
            sections.append(render(feed["name"], fresh, now))

    if failures == len(FEEDS):
        print("every feed failed; nothing written", file=sys.stderr)
        return 1

    if not fresh_total:
        print("nothing new; LEADS.md untouched")
        return 0

    if args.dry_run:
        print(f"dry run: would append {fresh_total} entries to {LEADS_FILE}")
        for section in sections:
            print(section.rstrip())
        return 0

    existed = LEADS_FILE.is_file()
    with LEADS_FILE.open("a", encoding="utf-8") as handle:
        if not existed:
            handle.write(HEADER)
        for section in sections:
            handle.write(section)
    print(f"appended {fresh_total} entries to {LEADS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
