#!/usr/bin/env python3
"""
core_framework/tests/test_exporters.py

Verify the dual-stream commercial exporters write both artifacts locally
without touching canonical source trees.
"""

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.bin.scout_vehicle import ScoutLeaderboard, ScoutVehicle  # noqa: E402


def _make_vehicle(tmp_path):
    ledger = ScoutLeaderboard(leaderboard_path=tmp_path / "lb.json")
    return ScoutVehicle(agent_id="Gemini-Core-Partner", leaderboard=ledger)


def test_exporters_write_both_streams(tmp_path):
    vehicle = _make_vehicle(tmp_path)
    findings = [
        {
            "ticker": "TSLA",
            "scout_type": "distress",
            "severity": "CRITICAL",
            "signals": ["Debt covenant breach"],
            "confidence": 0.92,
        },
        {
            "ticker": "NVDA",
            "scout_type": "competitive",
            "severity": "WARNING",
            "signals": ["ASIC displacement"],
            "confidence": 0.78,
        },
    ]
    vehicle.run_patrol_pass(["TSLA", "NVDA"], findings)
    result = vehicle.export_alpha_streams(output_dir=tmp_path)

    market_path = Path(result["market_twin_json"])
    alpha_path = Path(result["alpha_stream_csv"])
    assert market_path.exists()
    assert alpha_path.exists()
    assert result["rows"] == 2

    snapshot = json.loads(market_path.read_text())
    assert snapshot["spatial_payload"]["type"] == "market_twin"
    assert "leaderboard" in snapshot

    with open(alpha_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert {row["ticker"] for row in rows} == {"TSLA", "NVDA"}
    assert all("medium" in row and "points" in row for row in rows)
