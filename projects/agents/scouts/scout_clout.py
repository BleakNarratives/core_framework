# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/scout_clout.py
# ROLE: scout_clout.py — see canonical at ~/projects/agents/scouts/scout_clout.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
"""
scout.py

A working scout, not a skeleton. Walks a directory, finds three concrete
signals worth surfacing, and emits real pheromones via pheromone_store.py
— does not invent its own message format.

Usage:
    python3 scout.py /path/to/scan
"""

import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from pheromone_store import PheromoneStore

TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|XXX)[:\s](.*)", re.IGNORECASE)
STALE_DAYS = 180


def scan(root_dir: str, store: PheromoneStore, source: str = "scout"):
    root = Path(root_dir)
    basenames = defaultdict(list)
    now = time.time()

    for path in root.rglob("*.py"):
        if any(part in {".git", "__pycache__", "node_modules"} for part in path.parts):
            continue

        basenames[path.name].append(path)

        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            match = TODO_PATTERN.search(line)
            if match:
                store.emit(
                    "FILE_MUTATION",
                    source=source,
                    path=str(path),
                    payload={"kind": "todo_found", "line": i, "text": match.group(2).strip()},
                )

        try:
            age_days = (now - path.stat().st_mtime) / 86400
            if age_days > STALE_DAYS:
                store.emit(
                    "FILE_MUTATION",
                    source=source,
                    path=str(path),
                    payload={"kind": "stale", "age_days": round(age_days)},
                )
        except OSError:
            continue

    for name, paths in basenames.items():
        if len(paths) > 1:
            store.emit(
                "FILE_MUTATION",
                source=source,
                path=name,
                payload={"kind": "duplicate_name", "locations": [str(p) for p in paths]},
            )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 scout.py /path/to/scan")
        sys.exit(1)
    store = PheromoneStore()
    scan(sys.argv[1], store)
    print("Scout pass done. Check pheromones.jsonl or run swarm_digest.py.")
