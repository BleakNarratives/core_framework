#!/usr/bin/env python3
"""
core_framework/tests/test_cli.py

Tests for the scout_vehicle CLI (offline, no network) and the domino.sh entry
point. The shell test only runs `help`, which touches nothing.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRAMEWORK = REPO_ROOT / "core_framework"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.bin.scout_vehicle import cli  # noqa: E402

SEC = FRAMEWORK / "fixtures" / "sec_filings.json"
NEWS = FRAMEWORK / "fixtures" / "news_feed.json"


def test_cli_offline_ingest_exports(tmp_path):
    rc = cli([
        "--ingest", f"sec={SEC}",
        "--ingest", f"news={NEWS}",
        "--query", "debt covenant default risk",
        "--export", str(tmp_path),
        "--memory", str(tmp_path / "mem.json"),
        "--leaderboard", str(tmp_path / "lb.json"),
        "--plan",
    ])
    assert rc == 0
    assert (tmp_path / "market_twin.json").exists()
    assert (tmp_path / "alpha_stream.csv").exists()
    assert (tmp_path / "mem.json").exists()


def test_cli_demo_mode_default(tmp_path):
    # No --broadcast and no ingest -> demo findings, no network broadcast attempt.
    rc = cli([
        "--export", str(tmp_path),
        "--memory", str(tmp_path / "mem.json"),
        "--leaderboard", str(tmp_path / "lb.json"),
    ])
    assert rc == 0
    rows = (tmp_path / "alpha_stream.csv").read_text().strip().splitlines()
    assert len(rows) == 3  # header + 2 demo findings


def test_domino_root_wrapper_exists():
    assert (REPO_ROOT / "domino.sh").exists()


def test_domino_help_runs():
    script = FRAMEWORK / "bin" / "domino.sh"
    assert script.exists()
    result = subprocess.run(
        ["bash", str(script), "help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "domino" in result.stdout.lower()
