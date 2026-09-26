#!/usr/bin/env python3
"""
driftguard — fail loudly when copies of a file silently diverge.

The problem
----------
When the same file exists in N places, fixes have to be applied N times, and
nothing reminds you that you only did it N-1 times. The failure is silent by
construction: the file that missed the fix still looks fine, still imports,
still passes its own tests. You find out months later from a strange incident.

This happened for real: three copies of a provider router, where a key-capture
fix reached two of them and not the third. Rotation silently degraded to a
single key in the copies that missed it.

The approach
------------
You usually *want* the copies to differ. One had a feature the others lacked;
another had an operational improvement. Forcing them identical would delete
working code. So the goal is not convergence -- it is that the *invariants*
must not drift, even when the features do.

This tool encodes the invariants as data and checks them across a file set.

    driftguard.py --config driftguard.json

Exit code 0 if every present file satisfies every invariant; 1 otherwise. That
makes it usable as a CI step, which is the only place a guard actually runs.

Config format
-------------
{
  "files": ["a/router.py", "b/router.py"],
  "missing": "skip",
  "invariants": [
    {"name": "vault capture keeps pool vars", "contains": "\\"_KEY_POOL\\""},
    {"name": "no dead branch", "not_contains": "co_varnames",
     "ignore_comments": true},
    {"name": "pins thread count", "regex": "\\"num_thread\\"\\s*:"}
  ]
}

Invariant keys
--------------
  contains / not_contains   literal substring
  regex                      Python regex, searched per line
  ignore_comments            strip whole-line comments first (default false)

`ignore_comments` exists because of a specific, repeatable way to get this
wrong: the comment that documents a fixed bug repeats the bug's text, so a
naive substring check reports a well-documented fix as an unfixed one. That
cost two false failures during development.

`missing` policy
----------------
  "skip"  (default) absent files are reported and excluded -- right when the
          files are legitimately untracked and absent in a clean clone
  "fail"  absent files are violations -- right when a missing file means the
          copy was deleted and nobody noticed

Stdlib only. No network, no clock.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class Invariant:
    """One named property every present file must satisfy."""

    name: str
    contains: Optional[str] = None
    not_contains: Optional[str] = None
    regex: Optional[str] = None
    ignore_comments: bool = False

    def __post_init__(self) -> None:
        if not any(v is not None for v in (self.contains, self.not_contains, self.regex)):
            raise ValueError(f"invariant {self.name!r} asserts nothing")
        if self.regex:
            re.compile(self.regex)  # fail at load, not mid-run

    def _text(self, source: str) -> str:
        if not self.ignore_comments:
            return source
        return "\n".join(
            ln for ln in source.splitlines() if not ln.strip().startswith("#")
        )

    def check(self, source: str) -> Optional[str]:
        """Return None if satisfied, else a human-readable reason it is not."""
        text = self._text(source)
        if self.contains is not None and self.contains not in text:
            return f"expected to contain {self.contains!r}"
        if self.not_contains is not None and self.not_contains in text:
            return f"expected NOT to contain {self.not_contains!r}"
        if self.regex is not None and not re.search(self.regex, text):
            return f"expected to match /{self.regex}/"
        return None

    def offenders(self, source: str) -> List[str]:
        """Lines to show when this invariant fails, so the report is actionable."""
        text = self._text(source)
        needles = [n for n in (self.contains, self.not_contains, self.regex) if n]
        out = []
        for i, ln in enumerate(text.splitlines(), 1):
            if any(n in ln for n in needles):
                out.append(f"    line {i}: {ln.strip()[:100]}")
        return out[:3]


@dataclass
class Report:
    violations: List[Dict[str, Any]] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "files_checked": self.checked,
            "missing": self.missing,
            "violations": self.violations,
        }


def load_config(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        try:
            import tomllib
        except ImportError:  # pragma: no cover - py<3.11
            raise SystemExit("toml config needs Python 3.11+; use JSON instead")
        return tomllib.loads(raw)
    return json.loads(raw)


def run(files: Sequence[str], invariants: Sequence[Invariant],
        missing: str = "skip", root: Optional[Path] = None) -> Report:
    root = root or Path.cwd()
    rep = Report()
    for rel in files:
        p = Path(rel) if Path(rel).is_absolute() else root / rel
        if not p.exists():
            rep.missing.append(rel)
            continue
        rep.checked += 1
        source = p.read_text(encoding="utf-8", errors="replace")
        for inv in invariants:
            reason = inv.check(source)
            if reason:
                rep.violations.append({
                    "file": rel,
                    "invariant": inv.name,
                    "reason": reason,
                    "lines": inv.offenders(source),
                })
    if missing == "fail":
        for rel in rep.missing:
            rep.violations.append({
                "file": rel, "invariant": "(file present)",
                "reason": "expected file is missing", "lines": [],
            })
    return rep


def build_invariants(specs: Sequence[Dict[str, Any]]) -> List[Invariant]:
    return [
        Invariant(
            name=s["name"],
            contains=s.get("contains"),
            not_contains=s.get("not_contains"),
            regex=s.get("regex"),
            ignore_comments=bool(s.get("ignore_comments", False)),
        )
        for s in specs
    ]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fail loudly when duplicated files silently diverge on an invariant.")
    ap.add_argument("--config", required=True, help="JSON or TOML config")
    ap.add_argument("--root", help="directory the config paths are relative to")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    cfg = load_config(cfg_path)
    root = Path(args.root) if args.root else cfg_path.resolve().parent
    invs = build_invariants(cfg.get("invariants", []))
    rep = run(cfg.get("files", []), invs, cfg.get("missing", "skip"), root)

    if args.json:
        print(json.dumps(rep.to_dict(), indent=2))
        return 0 if rep.ok else 1

    print(f"\n  driftguard — {rep.checked} file(s), {len(invs)} invariant(s)")
    if rep.missing:
        print(f"  missing ({len(rep.missing)}): {', '.join(rep.missing)}")
    if rep.ok:
        print("  all present files satisfy every invariant\n")
        return 0

    print(f"\n  {len(rep.violations)} violation(s):\n")
    for v in rep.violations:
        print(f"  {v['file']}")
        print(f"    invariant: {v['invariant']}")
        print(f"    {v['reason']}")
        for ln in v["lines"]:
            print(ln)
        print()
    print("  A fix was applied to some copies and not this one.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
