# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/swarm_digest.py
# ROLE: swarm_digest.py — see canonical at ~/projects/agents/scouts/swarm_digest.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
"""
swarm_digest.py

The actual token-saving tool: instead of pasting full terminal dumps or
screenshots into a chat, run this and paste its output — a compact,
few-line summary of what's happened in the substrate since last check.

Usage:
    python3 swarm_digest.py [--since HOURS] [--store pheromones.jsonl]
"""

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def load_events(store_path: str, since_hours: float):
    if not Path(store_path).exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    events = []
    with open(store_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                ts = datetime.fromisoformat(e["timestamp"])
                if ts >= cutoff:
                    events.append(e)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return events


def git_status_summary() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().splitlines()
        if not lines:
            return "clean"
        changed = sum(1 for l in lines if l.startswith(" M") or l.startswith("M"))
        added = sum(1 for l in lines if l.startswith("??") or l.startswith("A"))
        return f"{changed} modified, {added} untracked"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "not a git repo / git unavailable"


def digest(store_path: str, since_hours: float) -> str:
    events = load_events(store_path, since_hours)
    by_type = Counter(e["type"] for e in events)

    lines = [f"--- Swarm digest, last {since_hours:.0f}h ---"]
    lines.append(f"git: {git_status_summary()}")

    if not events:
        lines.append("No pheromone activity in this window.")
        return "\n".join(lines)

    lines.append(f"Events: {len(events)} total")
    for type_, count in by_type.most_common():
        lines.append(f"  {type_}: {count}")

    live_claims = [
        e for e in events if e["type"] == "TASK_CLAIM"
        and not any(
            r["type"] == "TASK_RELEASE" and r["path"] == e["path"] and r["timestamp"] > e["timestamp"]
            for r in events
        )
    ]
    if live_claims:
        lines.append(f"\nLikely-active claims ({len(live_claims)}):")
        for c in live_claims[-5:]:
            lines.append(f"  {c['source']} -> {c['path']}")

    fails = [e for e in events if e["type"] == "VALIDATION_FAIL"]
    if fails:
        lines.append(f"\nNew dead limbs ({len(fails)}):")
        for fail in fails[-5:]:
            reason = fail.get("payload", {}).get("reason", "unspecified")
            lines.append(f"  {fail['path']}: {reason}")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=float, default=6.0, help="Hours to look back (default 6)")
    parser.add_argument("--store", default="pheromones.jsonl")
    args = parser.parse_args()
    print(digest(args.store, args.since))
