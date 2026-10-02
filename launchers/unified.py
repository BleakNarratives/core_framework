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

Daemon / subshell safety:
    python unified.py all --detach

``--detach`` starts every child in its own session with stdin closed and
stdout/stderr redirected to per-system log files. The coordinator returns
immediately with the PIDs, so an agent running inside a sandboxed subshell is
never left holding an open pipe to a long-lived child process.

Note: This is a coordinator only. Each system runs in its own process with
its own sys.path and dependencies. No shared state is assumed.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = FRAMEWORK_ROOT.parent
LAUNCHERS = FRAMEWORK_ROOT / "launchers"

# Allow `python core_framework/launchers/unified.py ...` from any cwd.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.shared.config import LOG_DIR, inject_venv_paths  # noqa: E402

COMMANDS = {
    "code_city": LAUNCHERS / "code_city.py",
    "modmind": LAUNCHERS / "modmind.py",
    "vertical_ai": LAUNCHERS / "vertical_ai.py",
}


def require_python() -> str:
    return sys.executable


def child_env() -> dict:
    """Environment for children: unbuffered I/O and any resolvable venv paths."""
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    extra = [p for p in inject_venv_paths() if p]
    if extra:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(extra + ([existing] if existing else []))
    return env


def launch_one(name: str, detach: bool, extra_args: list[str]):
    script = COMMANDS[name]
    if not script.exists():
        raise SystemExit(f"[core_framework] Missing launcher: {script}")

    cmd = [require_python(), str(script), *extra_args]
    print(f"[core_framework] Starting {name} -> {script}")

    if not detach:
        # Attached mode still closes inherited fds so a sandboxed parent can
        # wait without the child holding unrelated descriptors open.
        return subprocess.Popen(
            cmd,
            cwd=str(FRAMEWORK_ROOT),
            env=child_env(),
            stdin=subprocess.DEVNULL,
            close_fds=True,
        )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{name}.log"
    log_handle = open(log_path, "ab", buffering=0)  # noqa: SIM115 - parent-owned handle
    proc = subprocess.Popen(
        cmd,
        cwd=str(FRAMEWORK_ROOT),
        env=child_env(),
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log_handle.close()
    print(f"[core_framework] {name} detached (pid={proc.pid}) -> {log_path}")
    return proc


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="core_framework.launchers.unified",
        description="Start any combination of Code City, ModMind, and Vertical AI.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=[],
        help="One or more of: " + " | ".join(sorted(COMMANDS)) + " (or 'all')",
    )
    parser.add_argument(
        "--detach",
        action="store_true",
        help="Start children in their own session with logs redirected and return immediately.",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Repeatable argument forwarded to every child launcher.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    targets = [t.lower() for t in args.targets]
    if not targets:
        print(__doc__)
        print("Available targets:", " | ".join(sorted(COMMANDS)))
        return 0

    if "all" in targets:
        targets = sorted(COMMANDS.keys())

    unknown = sorted(set(targets) - COMMANDS.keys())
    if unknown:
        raise SystemExit(f"[core_framework] Unknown target(s): {unknown}")

    procs = []
    try:
        for target in targets:
            procs.append(launch_one(target, args.detach, args.arg))
        if args.detach:
            return 0
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[core_framework] Shutting down...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
