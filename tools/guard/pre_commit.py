#!/usr/bin/env python3
"""
tools/guard/pre_commit.py — the commit gate.

Purpose: make the *good* path the default. A codebase rots because nothing
stops the next commit from adding generated files, unparseable Python, or
undefined names. This gate is intentionally small: it blocks only things that
are unambiguously wrong, and reports the rest.

Blocks (exit 1):
  - staged generated artifacts (__pycache__, *.pyc/*.pyo, editor backups)
  - staged files under thoth_orchestrator/foxwood_backup/ (timestamped dumps)
  - staged Python that does not compile (checked in-process, writes no .pyc)

Advisory (reported, never blocks) — real-bug lint if ruff is on PATH:
  - E9 syntax, F63/F7 placeholder, F82 undefined, F821 undefined name, F401/F841

Design notes:
  - No third-party imports. Works on a clean machine with only Python.
  - Compiles from source text via `compile()`, so it never litters .pyc files.
  - Ruff runs only on files already staged, so pre-existing debt elsewhere
    cannot block an unrelated commit.

Install:  ln -sf ../../tools/guard/pre_commit.py .git/hooks/pre-commit
Disable:  rm -f .git/hooks/pre-commit
Bypass a single commit:  git commit --no-verify
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Paths whose presence in the index is almost always a mistake. Everything
# here is a generated or transient artifact; source belongs elsewhere.
BLOCKED_SUFFIXES = (".pyc", ".pyo", ".orig", ".rej")
BLOCKED_DIR_PARTS = {"__pycache__"}
BLOCKED_PREFIXES = ("thoth_orchestrator/foxwood_backup/",)

# Advisory only. Kept narrow so the gate stays trustworthy: every entry is a
# finding that is genuinely a bug or dead code, not a style preference.
RUFF_SELECT = "E9,F63,F7,F82,F821,F401,F841"

# A real finding line is `path:line:col: CODE message`. ruff also prints summary
# lines ("Found N errors.", "[*] N fixable...") that must not be counted.
FINDING_RE = re.compile(r"^.+:\d+:\d+: [A-Z]+\d+")


def _git(*args: str) -> str:
    return subprocess.run(
        ("git", *args), capture_output=True, text=True, check=True
    ).stdout


def staged_files() -> list[str]:
    """Added/copied/modified files in the index, repo-relative, forward slashes."""
    out = _git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_blocked_artifact(path: str) -> bool:
    if path.startswith(BLOCKED_PREFIXES):
        return True
    if Path(path).suffix in BLOCKED_SUFFIXES:
        return True
    return any(part in BLOCKED_DIR_PARTS for part in Path(path).parts)


def compile_errors(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        p = Path(path)
        if p.suffix != ".py" or not p.is_file():
            continue
        try:
            source = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: unreadable ({exc})")
            continue
        try:
            compile(source, path, "exec")
        except SyntaxError as exc:
            errors.append(f"{path}:{exc.lineno}: {exc.msg}")
    return errors


def ruff_findings(paths: list[str]) -> tuple[list[str], bool]:
    """Return (findings, ruff_available). Never raises."""
    py = [p for p in paths if p.endswith(".py") and Path(p).is_file()]
    if not py:
        return [], True
    try:
        proc = subprocess.run(
            ("ruff", "check", "--select", RUFF_SELECT,
             "--output-format", "concise", *py),
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return [], False
    if proc.returncode == 127:
        return [], False
    if proc.returncode == 0:
        # ruff prints "All checks passed!" on success; that is not a finding.
        return [], True
    lines = [ln for ln in proc.stdout.splitlines() if FINDING_RE.match(ln)]
    return lines, True


def main() -> int:
    files = staged_files()
    if not files:
        return 0

    blocked = [f for f in files if is_blocked_artifact(f)]
    errors = compile_errors(files)

    if blocked:
        print("pre-commit: refusing to commit generated artifacts:", file=sys.stderr)
        for path in blocked:
            print(f"  - {path}", file=sys.stderr)
        print(
            "\n  These are build/runtime outputs. Keep them on disk but out of git:\n"
            "  git rm --cached <path>   (or add the pattern to .gitignore)\n"
            "  Bypass once with: git commit --no-verify",
            file=sys.stderr,
        )

    if errors:
        print("pre-commit: staged Python does not compile:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    if blocked or errors:
        return 1

    findings, ruff_ok = ruff_findings(files)
    if findings:
        print(f"pre-commit: {len(findings)} advisory lint finding(s) in staged files:")
        for line in findings[:15]:
            print(f"  {line}")
        if len(findings) > 15:
            print(f"  … and {len(findings) - 15} more (ruff check --select {RUFF_SELECT})")
        print("  (advisory only — not blocking)")
    elif ruff_ok:
        print("pre-commit: ok — staged Python compiles, no blocked artifacts.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
