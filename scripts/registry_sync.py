#!/usr/bin/env python3
"""
Meridian registry sync — lightweight workspace manifest scanner.

Scans live project trees, writes/refreshes the centralized
`meridian_manifest.json`, and embeds the DELETION_LOCKOUT list so any
consumer (cleanup scripts, agents, humans) can check lockout status before
touching archive content.

Read-only with respect to everything it scans. The only file it writes is
the manifest itself.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/home/bleaknarratives")
MANIFEST = HOME / "FISH-VAG-SOS" / "meridian_manifest.json"
LOCKOUT_DOC = HOME / "FISH-VAG-SOS" / "DELETION_LOCKOUT.md"
ARCHIVE = HOME / "._archive" / "duplicates"
CENSUS = HOME / "FISH-VAG-SOS" / "duplicates_census_2026-09-15.json"

# Top-level dirs that are workspace projects worth listing (not dotfiles,
# not system/tooling noise). Kept deliberately permissive; the manifest is
# descriptive, not a permission.
SKIP_PREFIXES = (".", "_", "$")
SKIP_NAMES = {"node_modules", "venv", ".venv", "__pycache__", "Downloads",
              "docs", "fixtures", "templates", "schemas", "outputs", "data",
              "inputs", "files", "include", "lib", "opt", "etc", "mnt", "w"}


def parse_lockout():
    """Extract locked + diverged project names from the lockout doc."""
    locked, diverged = [], []
    section = None
    for line in LOCKOUT_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Locked projects"):
            section = "locked"
            continue
        if line.startswith("## Diverged"):
            section = "diverged"
            continue
        if line.startswith("## "):
            section = None
            continue
        if section and line.strip() and not line.startswith("**"):
            names = [n.strip() for n in line.split(",") if n.strip()]
            (locked if section == "locked" else diverged).extend(names)
    return locked, diverged


def scan_project(root: Path):
    """Cheap project summary: file counts, py count, last-modified."""
    stats = {"files": 0, "py_files": 0, "last_modified": None}
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in
                           ("node_modules", ".git", "__pycache__", "venv", ".venv")]
            for name in filenames:
                stats["files"] += 1
                if name.endswith(".py"):
                    stats["py_files"] += 1
                fp = Path(dirpath) / name
                try:
                    mtime = fp.stat().st_mtime
                except OSError:
                    continue
                if stats["last_modified"] is None or mtime > stats["last_modified"]:
                    stats["last_modified"] = mtime
    except OSError:
        pass
    if stats["last_modified"]:
        stats["last_modified"] = datetime.fromtimestamp(
            stats["last_modified"], tz=timezone.utc
        ).isoformat()
    else:
        stats["last_modified"] = None
    return stats


def main():
    locked, diverged = parse_lockout()

    projects = {}
    for entry in sorted(HOME.iterdir()):
        if entry.name.startswith(SKIP_PREFIXES) or entry.name in SKIP_NAMES:
            continue
        if not entry.is_dir():
            continue
        projects[entry.name] = scan_project(entry)

    archive_projects = sorted(
        d for d in os.listdir(ARCHIVE)
        if (ARCHIVE / d).is_dir() and not d.startswith(".")
    ) if ARCHIVE.is_dir() else []

    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "live_projects": projects,
        "live_project_count": len(projects),
        "archive": {
            "root": str(ARCHIVE),
            "projects": archive_projects,
            "deletion_lockout_active": True,
            "locked_last_known_copy": locked,
            "diverged": diverged,
        },
        "census_reference": str(CENSUS),
    }

    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest written: {MANIFEST}")
    print(f"  live projects:      {len(projects)}")
    print(f"  archive projects:   {len(archive_projects)}")
    print(f"  locked (LKC):       {len(locked)}")
    print(f"  diverged:           {len(diverged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
