#!/usr/bin/env python3
"""
core_framework/tests/test_launcher.py

Argument-parsing and daemon-environment tests for the unified launcher.
These do NOT spawn real systems; they verify the contract that keeps agents
from hanging on child file descriptors.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.launchers import unified  # noqa: E402


def test_parse_all_and_detach():
    args = unified.parse_args(["all", "--detach"])
    assert args.targets == ["all"]
    assert args.detach is True


def test_parse_targets_with_forwarded_args():
    args = unified.parse_args(["code_city", "--arg", "debug"])
    assert args.targets == ["code_city"]
    assert args.arg == ["debug"]


def test_no_targets_returns_zero():
    assert unified.main([]) == 0


def test_child_env_is_unbuffered():
    env = unified.child_env()
    assert env["PYTHONUNBUFFERED"] == "1"


def test_detach_creates_pid_and_log(tmp_path, monkeypatch):
    """A detached child should not block and should write a log file."""
    # Use a trivial child script so no canonical system is started.
    script = tmp_path / "child.py"
    script.write_text("import time, sys\nprint('hello', flush=True)\ntime.sleep(0.1)\n")
    monkeypatch.setitem(unified.COMMANDS, "code_city", script)
    monkeypatch.setattr(unified, "LOG_DIR", tmp_path / "logs")

    proc = unified.launch_one("code_city", detach=True, extra_args=[])
    proc.wait(timeout=10)
    assert proc.returncode == 0
    log_text = (tmp_path / "logs" / "code_city.log").read_text()
    assert "hello" in log_text
