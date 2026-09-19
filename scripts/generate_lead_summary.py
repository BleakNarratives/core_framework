#!/usr/bin/env python3
"""generate_lead_summary.py — parse LEADS.md and emit a Markdown summary table.

Usage:
    python scripts/generate_lead_summary.py
    python scripts/generate_lead_summary.py --input projects/herald/LEADS.md
    python scripts/generate_lead_summary.py --output lead_summary.md

Logic is fully isolated in this file. No external dependencies.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_INPUT = os.path.join("projects", "herald", "LEADS.md")
DEFAULT_OUTPUT = "lead_summary.md"

ATS_DOMAINS = {
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "join.com",
    "bamboohr.com",
    "workable.com",
    "icims.com",
    "smartrecruiters.com",
    "myworkdayjobs.com",
    "applytojob.com",
    "breezy.hr",
    "grnh.se",
    "app.deel.com",
    "jobs.ashbyhq.com",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
DM_RE = re.compile(r"\bdm\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_leads(text: str) -> List[Dict[str, Any]]:
    """Return a list of lead dicts from raw LEADS.md text."""
    leads: List[Dict[str, Any]] = []
    current_section = "unknown"
    current_lead: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")

        # Track sections
        m_section = re.match(r"^##\s+(.+)$", line)
        if m_section:
            current_section = m_section.group(1).strip()
            continue

        # New lead entry
        m_lead = re.match(r"^\*\s+\*\*\[(.+?)\]\*\*\s+(.+)$", line)
        if m_lead:
            if current_lead:
                leads.append(current_lead)
            current_lead = {
                "section": current_section,
                "author_or_source": m_lead.group(1).strip(),
                "title": m_lead.group(2).strip(),
                "url": "",
                "matched": "",
                "contact": "",
                "contact_raw": "",
                "posted": "",
                "has_email": False,
                "has_dm": False,
                "has_ats": False,
                "has_link": False,
            }
            continue

        if current_lead is None:
            continue

        # Sub-fields
        if line.strip().startswith("- URL:"):
            current_lead["url"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- Link:"):
            current_lead["url"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- Matched:"):
            current_lead["matched"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- Contact:"):
            current_lead["contact_raw"] = line.split(":", 1)[1].strip()
            current_lead["contact"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("- Posted:"):
            current_lead["posted"] = line.split(":", 1)[1].strip()

    if current_lead:
        leads.append(current_lead)

    # Enrich contact classification
    for lead in leads:
        raw = lead.get("contact_raw", "")
        lead["has_email"] = bool(EMAIL_RE.search(raw))
        lead["has_dm"] = bool(DM_RE.search(raw))

        ats_found = False
        link_found = False
        for token in re.split(r",\s*", raw):
            token = token.strip()
            if not token:
                continue
            if token.startswith("email:"):
                continue
            if token == "dm":
                continue
            url_like = token.replace("link:", "").strip()
            domain = _extract_domain(url_like)
            if domain and domain in ATS_DOMAINS:
                ats_found = True
            elif url_like:
                link_found = True

        lead["has_ats"] = ats_found
        lead["has_link"] = link_found

    return leads


def _extract_domain(url: str) -> Optional[str]:
    if not url.startswith("http"):
        url = "https://" + url
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_contact_route(lead: Dict[str, Any]) -> str:
    if lead["has_email"] and lead["has_ats"]:
        return "email + ATS"
    if lead["has_email"] and lead["has_dm"]:
        return "email + DM"
    if lead["has_email"]:
        return "direct (email)"
    if lead["has_ats"] and lead["has_dm"]:
        return "ATS + DM"
    if lead["has_ats"]:
        return "ATS form"
    if lead["has_dm"]:
        return "DM only"
    if lead["has_link"]:
        return "link only"
    if lead.get("url"):
        return "source only"
    return "none"


def _is_qualified(lead: Dict[str, Any]) -> bool:
    """A lead is qualified if it has at least one actionable contact method."""
    return any([
        lead["has_email"],
        lead["has_dm"],
        lead["has_ats"],
        lead["has_link"],
    ])


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _compute_stats(leads: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(leads)
    qualified = sum(1 for lead in leads if _is_qualified(lead))
    unqualified = total - qualified

    routes: Dict[str, int] = {}
    for lead in leads:
        if not _is_qualified(lead):
            continue
        route = _classify_contact_route(lead)
        routes[route] = routes.get(route, 0) + 1

    fit_ratio = (qualified / total * 100) if total else 0.0

    # Per-section breakdown
    sections: Dict[str, Dict[str, Any]] = {}
    for lead in leads:
        sec = lead["section"]
        if sec not in sections:
            sections[sec] = {"total": 0, "qualified": 0, "routes": {}}
        sections[sec]["total"] += 1
        if _is_qualified(lead):
            sections[sec]["qualified"] += 1
            route = _classify_contact_route(lead)
            sections[sec]["routes"][route] = sections[sec]["routes"].get(route, 0) + 1

    return {
        "total": total,
        "qualified": qualified,
        "unqualified": unqualified,
        "fit_ratio_pct": round(fit_ratio, 1),
        "routes": dict(sorted(routes.items(), key=lambda x: (-x[1], x[0]))),
        "sections": sections,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "LEADS.md",
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_md(stats: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Lead Summary")
    lines.append("")
    lines.append(f"*Generated: {stats['generated_at']}*")
    lines.append(f"*Source: {stats['source']}*")
    lines.append("")

    # Overview table
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    lines.append(f"| Total leads | {stats['total']} |")
    lines.append(f"| Qualified | {stats['qualified']} |")
    lines.append(f"| Unqualified | {stats['unqualified']} |")
    lines.append(f"| Fit ratio | {stats['fit_ratio_pct']}% |")
    lines.append("")

    # Contact route breakdown
    lines.append("## Contact Route Breakdown")
    lines.append("")
    lines.append("| Route | Count | Share of qualified |")
    lines.append("|---|---:|--:|")
    qualified = stats["qualified"] or 1
    for route, count in stats["routes"].items():
        share = round(count / qualified * 100, 1)
        lines.append(f"| {route} | {count} | {share}% |")
    lines.append("")

    # Per-section breakdown
    lines.append("## Section Breakdown")
    lines.append("")
    lines.append("| Section | Total | Qualified | Fit % | Top routes |")
    lines.append("|---|---:|---:|---:|:---|")
    for sec, data in stats["sections"].items():
        fit = round(data["qualified"] / data["total"] * 100, 1) if data["total"] else 0.0
        top_routes = sorted(data["routes"].items(), key=lambda x: (-x[1], x[0]))[:3]
        top_str = ", ".join(f"{r} ({c})" for r, c in top_routes) if top_routes else "—"
        lines.append(f"| {sec} | {data['total']} | {data['qualified']} | {fit}% | {top_str} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Parse LEADS.md and emit a Markdown lead summary.",
    )
    p.add_argument(
        "--input", "-i",
        default=DEFAULT_INPUT,
        help=f"Path to LEADS.md (default: {DEFAULT_INPUT})",
    )
    p.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output Markdown path (default: {DEFAULT_OUTPUT})",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 2

    text = input_path.read_text(encoding="utf-8")
    leads = _parse_leads(text)

    if not leads:
        print("No leads parsed from input.", file=sys.stderr)
        return 1

    stats = _compute_stats(leads)
    md = _render_md(stats)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")

    print(f"Parsed {stats['total']} leads ({stats['qualified']} qualified).")
    print(f"Fit ratio: {stats['fit_ratio_pct']}%")
    print(f"Written: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
