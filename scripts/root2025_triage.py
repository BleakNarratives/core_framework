#!/usr/bin/env python3
"""
root_2025 conflict-file triage.

Scans the flattened root_2025_* conflict artifacts in the NAT recovery
intake, extracts per-file imports and header signals, and classifies each
into one of three actions:

  PORT     — stdlib-only or light-dependency file, plausible standalone
             utility worth porting into a live tree.
  ARCHIVE  — historical context worth keeping as a snapshot (large
             frameworks, heavy deps, one-off experiments).
  DISCARD  — near-empty, non-Python data, or trivially small stubs.

Read-only. Writes its JSON report to stdout.
"""

import ast
import json
import os
import re
import sys

CONFLICTS = (
    "/home/bleaknarratives/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/"
    "android/root_2026/ModMind/nat_vcs/.nat/conflicts"
)

# Deps that make a file heavy: classified ARCHIVE unless the file is tiny.
HEAVY_DEPS = {
    "torch", "tensorflow", "numpy", "pandas", "cv2", "matplotlib",
    "scipy", "sklearn", "transformers", "whisper", "requests",
}
STDLIB_OK = {
    "os", "sys", "json", "re", "time", "math", "pathlib", "datetime",
    "typing", "hashlib", "uuid", "logging", "collections", "itertools",
    "functools", "subprocess", "shutil", "tempfile", "argparse", "base64",
    "threading", "queue", "socket", "struct", "random", "csv", "sqlite3",
    "io", "abc", "enum", "dataclasses", "textwrap", "traceback", "warnings",
    "copy", "glob", "fnmatch", "zipfile", "tarfile", "gzip", "ast",
}

MIN_PORT_LINES = 40       # too small = stub → DISCARD candidate
LARGE_ARCHIVE_LINES = 400  # big files go to ARCHIVE even if deps are light


def classify(path):
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return "DISCARD", {"reason": f"unreadable: {exc}"}, set(), 0

    lines = src.count("\n")
    info = {"lines": lines}

    # First docstring / header comment as description
    m = re.search(r'"""(.*?)"""', src, re.DOTALL) or re.search(r"'''(.*?)'''", src, re.DOTALL)
    if m:
        info["docstring"] = " ".join(m.group(1).split())[:140]

    imports = set()
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
    except SyntaxError:
        info["parse"] = "syntax-error"

    info["imports"] = sorted(imports)
    heavy = sorted(imports & HEAVY_DEPS)
    if heavy:
        info["heavy_deps"] = heavy

    if lines < MIN_PORT_LINES:
        return "DISCARD", info, imports, lines
    if heavy:
        return "ARCHIVE", info, imports, lines
    if lines > LARGE_ARCHIVE_LINES:
        return "ARCHIVE", info, imports, lines
    if imports and not imports.issubset(STDLIB_OK):
        # Unknown third-party deps: archive pending manual review
        info["unknown_deps"] = sorted(imports - STDLIB_OK)
        return "ARCHIVE", info, imports, lines
    return "PORT", info, imports, lines


def main():
    files = sorted(f for f in os.listdir(CONFLICTS) if f.startswith("root_2025"))
    report = {"root": CONFLICTS, "total_files": len(files),
              "PORT": [], "ARCHIVE": [], "DISCARD": []}
    for name in files:
        path = os.path.join(CONFLICTS, name)
        action, info, imports, lines = classify(path)
        report[action].append({"file": name, **info})
        print(f"[{action:>8}] {lines:>6}L  {name}", file=sys.stderr)

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    print(
        f"\nTriage: {len(files)} files | PORT {len(report['PORT'])} | "
        f"ARCHIVE {len(report['ARCHIVE'])} | DISCARD {len(report['DISCARD'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
