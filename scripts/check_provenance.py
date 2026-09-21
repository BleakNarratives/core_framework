#!/usr/bin/env python3
"""
check_provenance.py — pre-use gate for deliverables.

Scans a target path (file or directory) and warns if it contains content
from any FOREIGN or UNKNOWN repo in PROVENANCE.md.

Usage:
    python scripts/check_provenance.py <path>
    python scripts/check_provenance.py <path> --strict   # exit 1 on any warning
    python scripts/check_provenance.py --audit            # re-scan PROVENANCE.md itself

Exit codes:
    0 — clean or only OWNED/FORK content
    1 --strict mode: FOREIGN or UNKNOWN content found
    2 — PROVENANCE.md missing or malformed
"""

import sys
import os
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROVENANCE_FILE = REPO_ROOT / "PROVENANCE.md"
BLOCKED_CLASSIFICATIONS = {"FOREIGN", "UNKNOWN"}

def parse_provenance(path: Path) -> dict:
    """Parse PROVENANCE.md into a mapping of relative_path -> classification."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    registry = {}
    current_section = ""
    for line in text.splitlines():
        line = line.rstrip()
        m = re.match(r"^## ([A-Z])", line)
        if m:
            current_section = m.group(1)
            continue
        m = re.match(r"^\| `([^`]+)` \| (\w+)", line)
        if m:
            repo_path = m.group(1).rstrip("/")
            classification = m.group(2)
            registry[repo_path] = {
                "classification": classification,
                "section": current_section,
            }
    return registry


def resolve_blocked_repos(registry: dict) -> dict:
    """Return only repos that block commercial use."""
    return {
        path: info
        for path, info in registry.items()
        if info["classification"] in BLOCKED_CLASSIFICATIONS
    }


def audit_provenance() -> bool:
    """Verify PROVENANCE.md itself is parseable and complete."""
    if not PROVENANCE_FILE.exists():
        print("FATAL: PROVENANCE.md not found at", PROVENANCE_FILE)
        return False
    registry = parse_provenance(PROVENANCE_FILE)
    blocked = resolve_blocked_repos(registry)
    print(f"PROVENANCE audit: {len(registry)} entries, {len(blocked)} blocked")
    for path, info in blocked.items():
        print(f"  BLOCKED  [{info['classification']}]  {path}")
    return True


def check_path(target: Path, registry: dict, strict: bool = False) -> bool:
    """Check whether target path touches any blocked repo. Returns True if clean."""
    blocked = resolve_blocked_repos(registry)
    if not blocked:
        print("No blocked entries in registry.")
        return True

    warnings = []
    target = target.resolve()

    if target.is_file():
        candidates = [target]
    else:
        candidates = sorted(target.rglob("*"))

    for candidate in candidates:
        if candidate.is_dir():
            continue
        rel = candidate.relative_to(REPO_ROOT)
        parts = [p.name for p in rel.parents if p.name != ""]
        # Walk up the path looking for a registry match
        for depth in range(len(parts) + 1):
            if depth == 0:
                prefix = parts[0] if parts else ""
            else:
                prefix = "/".join(parts[: len(parts) - depth + 1])
            # Try direct match and top-level match
            for key in (prefix, prefix.split("/")[0] if "/" in prefix else prefix):
                if key in blocked:
                    info = blocked[key]
                    warnings.append(
                        f"  WARNING [{info['classification']}]  {rel}  (under {key})"
                    )
                    break

    if warnings:
        print(f"WARNING: {len(warnings)} file(s) touch blocked repos:\n")
        print("\n".join(sorted(set(warnings))))
        print(
            "\nBlocked repos:\n"
            + "\n".join(
                f"  [{info['classification']}]  {path}"
                for path, info in sorted(blocked.items())
            )
        )
        print("\nAction required:")
        print("  - Remove foreign content from deliverable, OR")
        print("  - Add attribution per PROVENANCE.md rules, OR")
        print("  - Re-run with --strict only after resolving.")
        if strict:
            return False
        return False
    print("Clean: no FOREIGN or UNKNOWN content detected.")
    return True


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 0

    registry = parse_provenance(PROVENANCE_FILE)
    if not registry:
        print("FATAL: PROVENANCE.md is empty or malformed.", file=sys.stderr)
        return 2

    if args[0] == "--audit":
        return 0 if audit_provenance() else 2

    strict = "--strict" in args
    targets = [Path(a) for a in args if not a.startswith("--")]

    if not targets:
        print("No target path given.")
        return 2

    all_clean = True
    for target in targets:
        if not target.exists():
            print(f"WARNING: {target} does not exist.")
            all_clean = False
            continue
        print(f"\n--- Checking: {target} ---")
        if not check_path(target, registry, strict=strict):
            all_clean = False

    return 1 if (strict and not all_clean) else 0


if __name__ == "__main__":
    sys.exit(main())
