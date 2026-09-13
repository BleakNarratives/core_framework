# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/find_canonical_loom.py
# ROLE: find_canonical_loom.py — see canonical at ~/projects/agents/sim/find_canonical_loom.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
"""
find_canonical_loom.py

Groups duplicate-named files (celtic_loom_complete.py, celtic_crypto.py,
loom_reader.py, etc.) by basename, shows size + mtime for each copy, and
flags which pairs are byte-identical vs. diverged. Doesn't move or delete
anything — same read-only philosophy as triage_pass.py.

Usage:
    python3 find_canonical_loom.py loom_search.txt

loom_search.txt should be one file path per line (exactly what you
already generated).
"""

import filecmp
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime


def hash_file(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, PermissionError) as e:
        return f"UNREADABLE: {e}"


def main(list_path: str):
    with open(list_path) as f:
        paths = [line.strip() for line in f if line.strip()]

    by_basename = defaultdict(list)
    for p in paths:
        by_basename[os.path.basename(p)].append(p)

    dupes = {name: plist for name, plist in by_basename.items() if len(plist) > 1}

    if not dupes:
        print("No duplicate basenames found.")
        return

    for name, plist in sorted(dupes.items()):
        print(f"\n=== {name} ({len(plist)} copies) ===")
        hashes = {}
        for p in plist:
            if not os.path.exists(p):
                print(f"  [MISSING] {p}")
                continue
            size = os.path.getsize(p)
            mtime = datetime.fromtimestamp(os.path.getmtime(p)).isoformat()
            h = hash_file(p)
            hashes[p] = h
            print(f"  {p}")
            print(f"    size={size}B  modified={mtime}  hash={h[:12]}...")

        unique_hashes = set(hashes.values())
        if len(unique_hashes) == 1:
            print("  -> All copies are byte-identical. Safe to keep newest, delete rest.")
        else:
            print("  -> Copies have DIVERGED — contents differ. Manual review needed before picking canonical.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 find_canonical_loom.py loom_search.txt")
        sys.exit(1)
    main(sys.argv[1])
