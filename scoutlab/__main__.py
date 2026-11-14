"""ScoutLab command line interface.

Examples (run from your project directory):
  python -m scoutlab init
  python -m scoutlab goal "find early financial distress signals"
  python -m scoutlab scan
  python -m scoutlab rate FINDING_ID yes
  python -m scoutlab report

The engine reads local JSON only. Ratings personalize relevance ranking; they do
not train or validate a real-world prediction model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import DEFAULT_DIRS, ScoutLab, choose_default_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scoutlab", description="Private offline scout that learns from your relevance ratings")
    parser.add_argument("--root", type=Path, default=None, help="project directory (default: RootBase if present, otherwise current directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="create the local database and settings")
    goal = commands.add_parser("goal", help="set what the scout should look for")
    goal.add_argument("text", nargs="+", help="your scouting goal")
    scan = commands.add_parser("scan", help="index local JSON signals and rank them")
    scan.add_argument("--dir", action="append", default=None, help="directory to scan; repeatable")
    scan.add_argument("--input", action="append", default=[], help="specific JSON file; repeatable")
    scan.add_argument("--limit", type=int, default=20, help="maximum items read from each file")
    rate = commands.add_parser("rate", help="teach the ranking from your judgment")
    rate.add_argument("finding_id")
    rate.add_argument("label", choices=("yes", "no"))
    report = commands.add_parser("report", help="show highest-ranked findings")
    report.add_argument("--limit", type=int, default=20)
    commands.add_parser("stats", help="show indexed and rated counts")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = (args.root or choose_default_root()).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"project directory does not exist: {root}")
    app = ScoutLab(root)
    if args.command == "init":
        app.initialize()
        print(f"ScoutLab ready. Private state: {app.state_dir}")
    elif args.command == "goal":
        text = " ".join(args.text)
        terms = app.set_goal(text)
        print(f"Goal saved: {text}\nSearch terms: {', '.join(terms)}")
    elif args.command == "scan":
        if args.limit < 1 or args.limit > 500:
            parser.error("--limit must be between 1 and 500")
        directories = args.dir if args.dir is not None else DEFAULT_DIRS
        count, paths = app.scan(directories=directories, explicit=args.input, per_file_limit=args.limit)
        print(f"Scanned {len(paths)} files; indexed {count} records.")
        app.write_report()
        app.print_report(limit=15)
    elif args.command == "rate":
        app.rate(args.finding_id, args.label == "yes")
        print("Saved. Your feedback now changes future relevance rankings.")
    elif args.command == "report":
        app.print_report(limit=max(1, args.limit))
        path = app.write_report()
        print(f"JSON report: {path}")
    elif args.command == "stats":
        print(json.dumps(app.stats(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
