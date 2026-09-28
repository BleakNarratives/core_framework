#!/usr/bin/env python3
"""
dna_tag.py (v2)

Two real changes from v1, per correction:
  1. ORIGIN is auto-detected from a one-time local device config
     (~/.dna_tag_origin), not typed manually every run — no more
     mismatched-device mistakes.
  2. Default mode is now --scan-dir: it lists untagged files in a
     directory and asks per-file (tag now / skip so you can move it
     first). It does NOT stamp automatically just because a file
     exists in a scanned directory — you still decide, per file.

Standalone single-file stamping (the v1 behavior) still exists via
--file, for when you already know exactly what you want tagged.

Usage:
    # One-time per device, or auto-prompted on first run:
    python3 dna_tag.py --set-origin A9

    # The normal workflow — scan a directory you just opened:
    python3 dna_tag.py --scan-dir .

    # Direct single-file stamp, origin still auto-detected:
    python3 dna_tag.py --file myfile.py --pillar swarm-coordination \\
        --role "does the thing" --tier 2
"""

import argparse
import ast
import sys
from datetime import date
from pathlib import Path

CONFIG_PATH = Path.home() / ".dna_tag_origin"

TAG_TEMPLATE = """
# [DNA_TAG]
# ORIGIN: {origin}
# PILLAR: {pillar}
# DEPS: {deps}
# ROLE: {role}
# AUTHOR: {author}
# SESSION: {session}
# TIER: {tier}
# [/DNA_TAG]
"""

TIER_OPTIONS = {
    "1": "Core (foundational, load-bearing)",
    "2": "System (major subsystem)",
    "3": "Module (standard component)",
    "4": "Utility (helper/one-off)",
}


def get_device_origin() -> str:
    """Reads the device's own identity from local config. Prompts once
    and saves if it's never been set on this device before — after that,
    every stamp on this device is correct by construction, no typing."""
    if CONFIG_PATH.exists():
        return CONFIG_PATH.read_text().strip()

    print("No device origin set yet for this device.")
    origin = input("What is this device's name? (e.g. A9, Moto4, Crostini-Chromebook): ").strip()
    CONFIG_PATH.write_text(origin)
    print(f"Saved. Every stamp from this device will now say ORIGIN: {origin} automatically.")
    return origin


def set_origin(origin: str):
    CONFIG_PATH.write_text(origin)
    print(f"Device origin set to: {origin}")


def prompt_choice(label: str, options: dict) -> str:
    print(f"\n{label}:")
    for k, v in options.items():
        print(f"  {k}) {v}")
    choice = input("Pick: ").strip()
    return choice if choice in options else list(options.keys())[-1]


def has_tag(path: Path) -> bool:
    try:
        return "[DNA_TAG]" in path.read_text(errors="ignore")
    except (OSError, UnicodeDecodeError):
        return True  # can't read it safely — treat as "leave it alone"


def stamp_file(path: Path, origin: str, fields: dict):
    original = path.read_text()
    tag = TAG_TEMPLATE.format(origin=origin, **fields)
    path.write_text(tag + "\n" + original)
    print(f"Stamped {path}")


def interactive_stamp(path: Path, origin: str):
    print(f"\n--- {path} ---")
    pillar = input("PILLAR: ").strip() or "unspecified"
    role = input("ROLE (one line): ").strip() or "unspecified"
    deps = input("DEPS (comma-separated, or blank): ").strip() or "none"
    author = input("AUTHOR [Bleak]: ").strip() or "Bleak"
    session = input(f"SESSION [{date.today().isoformat()}]: ").strip() or date.today().isoformat()
    tier = prompt_choice("TIER", TIER_OPTIONS)
    stamp_file(path, origin, {
        "pillar": pillar, "role": role, "deps": deps,
        "author": author, "session": session, "tier": tier,
    })


def infer_fields(path: Path, dir_name: str) -> dict:
    """Best-effort inference so a big batch doesn't need 23 rounds of
    manual questions. Anything it can't confidently infer gets an
    honest 'unspecified' rather than a guess dressed up as certainty."""
    role = "unspecified"
    deps = []
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
        docstring = ast.get_docstring(tree)
        if docstring:
            role = docstring.strip().splitlines()[0][:100]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                deps.append(node.module.split(".")[0])
    except (SyntaxError, ValueError):
        role = "unspecified — file did not parse cleanly, needs manual look"

    return {
        "pillar": dir_name,
        "role": role,
        "deps": ",".join(sorted(set(deps))) or "none",
        "author": "Bleak",
        "session": date.today().isoformat(),
        "tier": "3",
    }


def auto_scan_dir(dir_path: str, origin: str):
    """Non-interactive per-file: infer everything, show the whole batch
    once, one confirm to write all of it. TIER defaults to 3 (Module) —
    review and bump anything that's actually Core/System by hand after."""
    root = Path(dir_path)
    untagged = [p for p in root.glob("*.py") if p.is_file() and not has_tag(p)]

    if not untagged:
        print(f"No untagged .py files in {root} — nothing to do.")
        return

    dir_name = root.resolve().name
    proposed = {p: infer_fields(p, dir_name) for p in untagged}

    print(f"Proposed tags for {len(untagged)} files (PILLAR defaults to '{dir_name}', TIER defaults to 3 — review before committing):\n")
    for p, fields in proposed.items():
        print(f"  {p.name}")
        print(f"    ROLE: {fields['role']}")
        print(f"    DEPS: {fields['deps']}")
        print()

    confirm = input("Write all of these? [y] yes / [n] cancel / [e] edit one first: ").strip().lower()
    if confirm == "e":
        target = input("Which filename to edit? ").strip()
        match = next((p for p in untagged if p.name == target), None)
        if match:
            interactive_stamp(match, origin)
            del proposed[match]
        confirm = input("Write the rest as proposed? [y/n]: ").strip().lower()

    if confirm == "y":
        for p, fields in proposed.items():
            stamp_file(p, origin, fields)
        print(f"\nStamped {len(proposed)} files.")
    else:
        print("Cancelled — nothing written.")


def scan_dir(dir_path: str, origin: str):
    """The core workflow: list what's untagged, decide per file. Never
    stamps without an explicit yes for that specific file."""
    root = Path(dir_path)
    untagged = [
        p for p in root.glob("*.py")
        if p.is_file() and not has_tag(p)
    ]

    if not untagged:
        print(f"No untagged .py files in {root} — nothing to do.")
        return

    print(f"Untagged files in {root}:")
    for p in untagged:
        print(f"  {p.name}")

    print("\nFor each file: [t]ag now, [s]kip (move it first), [q]uit scan.")
    for p in untagged:
        choice = input(f"\n{p.name} — t/s/q? ").strip().lower()
        if choice == "q":
            break
        if choice == "t":
            interactive_stamp(p, origin)
        else:
            print(f"Skipped — move it to where it belongs, then re-scan.")


def main():
    parser = argparse.ArgumentParser(description="DNA_TAG provenance tool.")
    parser.add_argument("--set-origin", help="Set this device's origin name once")
    parser.add_argument("--scan-dir", help="Scan a directory for untagged files, one-by-one interactive")
    parser.add_argument("--auto-scan-dir", help="Scan a directory, infer fields automatically, one confirm for the whole batch")
    parser.add_argument("--file", help="Stamp a single specific file directly")
    parser.add_argument("--pillar")
    parser.add_argument("--deps")
    parser.add_argument("--role")
    parser.add_argument("--author")
    parser.add_argument("--session")
    parser.add_argument("--tier")
    args = parser.parse_args()

    if args.set_origin:
        set_origin(args.set_origin)
        return

    origin = get_device_origin()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {args.file}")
            sys.exit(1)
        if has_tag(path):
            print(f"{args.file} already has a DNA_TAG — not double-stamping.")
            return
        if any([args.pillar, args.role, args.deps, args.author, args.session, args.tier]):
            fields = {
                "pillar": args.pillar or "unspecified",
                "deps": args.deps or "none",
                "role": args.role or "unspecified",
                "author": args.author or "Bleak",
                "session": args.session or date.today().isoformat(),
                "tier": args.tier or "3",
            }
            stamp_file(path, origin, fields)
        else:
            interactive_stamp(path, origin)
        return

    if args.auto_scan_dir is not None:
        auto_scan_dir(args.auto_scan_dir, origin)
        return

    # Default: scan-dir workflow, defaulting to current directory
    scan_dir(args.scan_dir or ".", origin)


if __name__ == "__main__":
    main()
