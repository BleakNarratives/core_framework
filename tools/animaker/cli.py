#!/usr/bin/env python3
"""Offline Diff Theater animation proposal CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import ProposalError, compile_animation, render_css, render_tailwind, to_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="animaker", description="Compile an untrusted diff event into a proposal-only animation.")
    parser.add_argument("event", type=Path, help="Diff Theater event JSON file")
    parser.add_argument("--diff", type=Path, help="Optional UTF-8 diff text file")
    parser.add_argument("--css", action="store_true", help="Print a CSS render proposal")
    parser.add_argument("--tailwind", action="store_true", help="Print Tailwind class suggestions")
    args = parser.parse_args(argv)
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        diff = args.diff.read_text(encoding="utf-8") if args.diff else event.get("source_diff", "")
        if not isinstance(diff, str):
            raise ProposalError("diff text must be supplied with --diff or event.source_diff")
        targets = ["native"] + (["css"] if args.css else []) + (["tailwind"] if args.tailwind else [])
        proposal = compile_animation(event, diff, targets)
        print(to_json(proposal))
        if args.css:
            print("\n/* CSS render proposal */\n" + render_css(proposal), file=sys.stderr)
        if args.tailwind:
            print("\n<!-- Tailwind render proposal -->\n" + render_tailwind(proposal), file=sys.stderr)
    except (OSError, json.JSONDecodeError, ProposalError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
