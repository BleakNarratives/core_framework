#!/usr/bin/env python3
"""
dna_tag.py

Stamps a [DNA_TAG] provenance header onto a file, matching the existing
convention found in celtic_crypto.py. Set fields via flags for scripting,
or run with no flags for an interactive picker.

Usage (flags):
    python3 dna_tag.py myfile.py --origin A9 --pillar codecity-general \\
        --deps "hashlib,json" --role "Does the thing" --author Bleak \\
        --session 2026-09-08 --tier 2

Usage (interactive):
    python3 dna_tag.py myfile.py
"""

import argparse
import sys
from datetime import date
from pathlib import Path

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

ORIGIN_OPTIONS = ["A9", "Moto4", "Crostini-Chromebook", "CodeBuddy", "Other"]


def prompt_choice(label: str, options: list) -> str:
    print(f"\n{label}:")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        choice = input("Pick a number (or type a custom value): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        if choice:
            return choice


def interactive_fields() -> dict:
    origin = prompt_choice("ORIGIN (which device/tool wrote this)", ORIGIN_OPTIONS)
    pillar = input("\nPILLAR (project area, e.g. codecity-general): ").strip() or "unspecified"
    deps = input("DEPS (comma-separated imports, or leave blank): ").strip() or "none"
    role = input("ROLE (one line: what this file does): ").strip() or "unspecified"
    author = input("AUTHOR: ").strip() or "Bleak"
    session = input(f"SESSION [{date.today().isoformat()}]: ").strip() or date.today().isoformat()

    print("\nTIER:")
    for k, v in TIER_OPTIONS.items():
        print(f"  {k}) {v}")
    tier_choice = input("Pick 1-4: ").strip()
    tier = tier_choice if tier_choice in TIER_OPTIONS else "3"

    return {
        "origin": origin, "pillar": pillar, "deps": deps,
        "role": role, "author": author, "session": session, "tier": tier,
    }


def stamp_file(target: str, fields: dict):
    path = Path(target)
    if not path.exists():
        print(f"File not found: {target}")
        sys.exit(1)

    original = path.read_text()
    if "[DNA_TAG]" in original:
        print(f"{target} already has a DNA_TAG — not double-stamping. Edit manually if you need to update it.")
        return

    tag = TAG_TEMPLATE.format(**fields)
    path.write_text(tag + "\n" + original)
    print(f"Stamped {target}:")
    print(tag)


def main():
    parser = argparse.ArgumentParser(description="Stamp a DNA_TAG provenance header onto a file.")
    parser.add_argument("target", help="File to stamp")
    parser.add_argument("--origin")
    parser.add_argument("--pillar")
    parser.add_argument("--deps")
    parser.add_argument("--role")
    parser.add_argument("--author")
    parser.add_argument("--session")
    parser.add_argument("--tier")
    args = parser.parse_args()

    flags_given = any([args.origin, args.pillar, args.deps, args.role, args.author, args.session, args.tier])

    if flags_given:
        fields = {
            "origin": args.origin or "unspecified",
            "pillar": args.pillar or "unspecified",
            "deps": args.deps or "none",
            "role": args.role or "unspecified",
            "author": args.author or "Bleak",
            "session": args.session or date.today().isoformat(),
            "tier": args.tier or "3",
        }
    else:
        fields = interactive_fields()

    stamp_file(args.target, fields)


if __name__ == "__main__":
    main()
