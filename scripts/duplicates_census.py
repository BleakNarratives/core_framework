#!/usr/bin/env python3
"""
Duplicates census — live vs archive diff for ._archive/duplicates/.

For each project directory in ./._archive/duplicates/, check whether a
same-named directory exists in the active workspace (home root), and if so
whether contents differ. Projects with NO live counterpart are flagged as
LAST_KNOWN_COPY and must be excluded from any dedup/deletion routine
(they are the only surviving copy).

Read-only. Writes nothing outside its report.
Output: JSON report on stdout; human summary on stderr.
"""

import hashlib
import json
import os
import sys

# The workspace root is the user's home; resolving it beats pinning a username.
HOME = os.path.expanduser("~")
ARCHIVE = os.path.join(HOME, "._archive", "duplicates")
# Noise to ignore when hashing a project tree.
IGNORE_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".venv", ".cache"}


def hash_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while True:
                block = fh.read(chunk)
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def tree_digest(root):
    """Order-independent content digest of all files under root."""
    hashes = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            fp = os.path.join(dirpath, name)
            rel = os.path.relpath(fp, root)
            h = hash_file(fp)
            if h is not None:
                hashes.append(f"{rel}:{h}")
    hashes.sort()
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest(), len(hashes)


def main():
    if not os.path.isdir(ARCHIVE):
        print(f"Archive not found: {ARCHIVE}", file=sys.stderr)
        return 2

    report = {"archive_root": ARCHIVE, "projects": [], "orphans": []}
    projects = sorted(
        d for d in os.listdir(ARCHIVE)
        if os.path.isdir(os.path.join(ARCHIVE, d)) and not d.startswith(".")
    )
    report["total_projects"] = len(projects)

    for name in projects:
        archive_path = os.path.join(ARCHIVE, name)
        live_path = os.path.join(HOME, name)
        entry = {
            "project": name,
            "archive_path": archive_path,
            "live_counterpart": live_path if os.path.exists(live_path) else None,
        }
        if entry["live_counterpart"] is None:
            entry["status"] = "LAST_KNOWN_COPY"
            report["orphans"].append(name)
        else:
            arc_digest, arc_files = tree_digest(archive_path)
            live_digest, live_files = tree_digest(live_path)
            entry["archive_files"] = arc_files
            entry["live_files"] = live_files
            if arc_digest == live_digest:
                entry["status"] = "IDENTICAL"
            else:
                entry["status"] = "DIVERGED"
        report["projects"].append(entry)
        print(f"[{entry['status']:>16}] {name}", file=sys.stderr)

    report["orphan_count"] = len(report["orphans"])
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")

    print(
        f"\nSummary: {len(projects)} projects | "
        f"{report['orphan_count']} LAST_KNOWN_COPY (locked from deletion) | "
        f"{sum(1 for p in report['projects'] if p['status'] == 'IDENTICAL')} identical | "
        f"{sum(1 for p in report['projects'] if p['status'] == 'DIVERGED')} diverged",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
