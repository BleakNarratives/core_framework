#!/usr/bin/env python3
"""
core_framework/launchers/unified.py

Unified coordinator. Starts any combination of the three core systems as
isolated subprocesses so a crash in one does not take down the container.

Usage:
    python unified.py code_city
    python unified.py modmind
    python unified.py vertical_ai
    python unified.py all
    python unified.py code_city vertical_ai

Note: This is a coordinator only. Each system runs in its own process with
its own sys.path and dependencies. No shared state is assumed.
"""

import subprocess
import sys
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
LAUNCHERS = FRAMEWORK_ROOT / "launchers"

COMMANDS = {
    "code_city": LAUNCHERS / "code_city.py",
    "modmind": LAUNCHERS / "modmind.py",
    "vertical_ai": LAUNCHERS / "vertical_ai.py",
}


def require_python() -> str:
    return sys.executable


def launch_one(name: str):
    script = COMMANDS[name]
    if not script.exists():
        raise SystemExit(f"[core_framework] Missing launcher: {script}")
    print(f"[core_framework] Starting {name} -> {script}")
    return subprocess.Popen(
        [require_python(), str(script), *sys.argv[2:]],
        cwd=str(FRAMEWORK_ROOT),
    )


def main():
    targets = [t.lower() for t in sys.argv[1:]]
    if not targets:
        print(__doc__)
        print("Available targets:", " | ".join(sorted(COMMANDS)))
        raise SystemExit(0)

    if "all" in targets:
        targets = sorted(COMMANDS.keys())

    unknown = sorted(set(targets) - COMMANDS.keys())
    if unknown:
        raise SystemExit(f"[core_framework] Unknown target(s): {unknown}")

    procs = []
    try:
        for target in targets:
            procs.append(launch_one(target))
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[core_framework] Shutting down...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()
