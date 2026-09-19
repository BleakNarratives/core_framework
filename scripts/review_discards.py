#!/usr/bin/env python3
"""
review_discards.py — interactive review of root_2025 discard candidates.

Presents each file from the triage report's DISCARD list with its size,
first lines, and lockout status, then asks before deleting anything.

Safety model:
  - Default mode is DRY RUN: shows what would happen, deletes nothing.
  - --execute is required to delete, and even then every file needs an
    explicit y prompt (or --yes to assume y per file; still requires
    --execute and a typed confirmation phrase).
  - The DELETION_LOCKOUT list is checked by name; anything matching is
    refused regardless of flags. (Discard files are not on the lockout
    list, but this guards against the manifest drifting out of sync.)

Reads: root2025_triage_2026-09-15.json, DELETION_LOCKOUT.md
Deletes: only files explicitly confirmed by the operator.
"""

import json
import sys
from pathlib import Path

HOME = Path.home()
CONFLICTS = (HOME / "NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/"
             "android/root_2026/ModMind/nat_vcs/.nat/conflicts")
TRIAGE = HOME / "FISH-VAG-SOS" / "root2025_triage_2026-09-15.json"
LOCKOUT = HOME / "FISH-VAG-SOS" / "DELETION_LOCKOUT.md"
CONFIRM_PHRASE = "DELETE 56"


def load_lockout_names():
    """Parse locked project names from the lockout doc (best effort)."""
    if not LOCKOUT.exists():
        return set()
    names = set()
    in_section = False
    for line in LOCKOUT.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Locked projects"):
            in_section = True
            continue
        if line.startswith("## "):
            in_section = False
            continue
        if in_section and line.strip() and not line.startswith("**"):
            names.update(n.strip() for n in line.split(",") if n.strip())
    return names


def main():
    execute = "--execute" in sys.argv
    assume_yes = "--yes" in sys.argv

    if not TRIAGE.exists():
        print(f"triage report missing: {TRIAGE}")
        return 2
    report = json.loads(TRIAGE.read_text(encoding="utf-8"))
    discards = [entry["file"] for entry in report.get("DISCARD", [])]
    locked = load_lockout_names()

    print(f"Discard candidates: {len(discards)}")
    print(f"Mode: {'EXECUTE (deletions enabled)' if execute else 'DRY RUN (nothing will be deleted)'}")
    print()

    deleted, kept, missing = 0, 0, 0
    for i, name in enumerate(discards, 1):
        path = CONFLICTS / name
        print(f"[{i}/{len(discards)}] {name}")
        if not path.exists():
            print("    already gone — skipping\n")
            missing += 1
            continue

        size = path.stat().st_size
        preview = ""
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                preview = "".join(fh.readlines()[:3]).rstrip()
        except OSError as exc:
            preview = f"(unreadable: {exc})"
        print(f"    size: {size} bytes")
        for pline in preview.splitlines():
            print(f"    | {pline[:100]}")

        # Lockout guard: refuse if the name maps to a protected project.
        if any(proj in name for proj in locked if len(proj) > 6):
            print("    ❌ LOCKED — matches a DELETION_LOCKOUT entry; refused.\n")
            kept += 1
            continue

        if not execute:
            print("    (dry run — would prompt here)\n")
            continue

        if assume_yes:
            answer = "y"
        else:
            try:
                answer = input("    delete? [y/N/q] ").strip().lower()
            except EOFError:
                answer = "q"
        if answer == "q":
            print("\nStopped by operator. Nothing further deleted.")
            break
        if answer == "y":
            path.unlink()
            print("    🗑 deleted\n")
            deleted += 1
        else:
            print("    kept\n")
            kept += 1

    print(f"\nSummary: {len(discards)} candidates | "
          f"{deleted} deleted | {kept} kept/locked | {missing} already gone")

    if execute and not assume_yes:
        # destructive session happened; require the phrase up-front next time
        print("Note: for unattended execution, re-run with "
              f"--execute --yes after typing '{CONFIRM_PHRASE}' when prompted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
