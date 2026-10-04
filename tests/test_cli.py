#!/usr/bin/env python3
"""
core_framework/tests/test_cli.py

Tests for the scout_vehicle CLI (offline, no network) and the domino.sh entry
point. The shell test only runs `help`, which touches nothing.
"""

import json
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


def test_cli_memory_persists_and_accumulates_across_runs(tmp_path, monkeypatch):
    """End-to-end persistence proof: run the scout CLI twice as two separate
    invocations against the same adaptive_memory.json; run 2 must LOAD run 1's
    learned state and BUILD ON it (runs increments, pheromone grows). Each run
    gets a fresh leaderboard so run 2's findings score fresh and feed new
    pheromone instead of being deduped to zero by the novelty window."""
    # This cloud checkout lacks the outer-repo tools/ package that
    # collect_offline binds to, so stub the source function with fixed
    # findings. The persistence path under test (memory load -> record ->
    # atomic save) is untouched by this seam.
    import core_framework.adapters.ingest_adapter as ingest_adapter

    stub_findings = [
        {"ticker": "TSLA", "scout_type": "distress", "severity": "CRITICAL",
         "signals": ["Debt covenant breach"], "confidence": 0.9, "medium": "filings"},
        {"ticker": "RBI", "scout_type": "regulatory", "severity": "CRITICAL",
         "signals": ["Consent order"], "confidence": 0.85, "medium": "filings"},
        {"ticker": "NVDA", "scout_type": "competitive", "severity": "WARNING",
         "signals": ["ASIC displacement"], "confidence": 0.7, "medium": "news"},
    ]
    monkeypatch.setattr(
        ingest_adapter, "collect_offline", lambda specs, limit=20: list(stub_findings)
    )

    mem_path = tmp_path / "mem.json"

    def run_once(n):
        return cli([
            "--ingest", f"sec={SEC}",
            "--ingest", f"news={NEWS}",
            "--query", "debt covenant default risk",
            "--export", str(tmp_path),
            "--memory", str(mem_path),
            "--leaderboard", str(tmp_path / f"lb{n}.json"),
            "--plan", "--json",
        ])

    assert run_once(1) == 0
    snap1 = json.loads(mem_path.read_text())
    key = "offline::debt covenant default risk"
    assert snap1["records"][key]["runs"] == 1
    p1 = snap1["records"][key]["pheromone"]

    assert run_once(2) == 0
    snap2 = json.loads(mem_path.read_text())
    assert snap2["records"][key]["runs"] == 2
    assert snap2["records"][key]["pheromone"] > p1
    # The learned plan is served back to the CLI (--plan) from run 2's load.
    assert snap2["records"][key]["high_alpha_yield_count"] >= 3


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
