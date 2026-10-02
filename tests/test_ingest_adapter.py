#!/usr/bin/env python3
"""
core_framework/tests/test_ingest_adapter.py

Offline ingestion tests: trend_scraper LocalJsonSource -> findings, plus a full
network-free adapt -> patrol -> score -> export loop. No network is exercised.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.adapters.ingest_adapter import (  # noqa: E402
    IngestAdapter,
    LocalJsonSource,
    collect_offline,
    derive_medium,
    derive_scout_type,
)

ROWS = [
    {"title": "TSLA debt covenant breach escalates", "url": "u1", "observed": "2026-10-01", "score": 90, "tags": ["TSLA"]},
    {"title": "NVDA faces competitor pricing war", "url": "u2", "observed": "2026-10-01", "score": 55, "tags": ["NVDA"]},
    {"title": "general market chatter", "url": "u3", "observed": "2026-10-01", "score": 5, "tags": []},
]


def _source(tmp_path, name, rows=ROWS):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(rows))
    return LocalJsonSource(name=name, path=path)


def test_medium_mapping():
    assert derive_medium("sec") == "filings"
    assert derive_medium("news") == "news"
    assert derive_medium("mystery") == "general"


def test_scout_type_keywords():
    assert derive_scout_type("debt covenant breach") == "distress"
    assert derive_scout_type("SEC enforcement probe") == "regulatory"
    assert derive_scout_type("competitor pricing war") == "competitive"


def test_findings_from_local_source(tmp_path):
    adapter = IngestAdapter("sec")
    findings = adapter.collect(_source(tmp_path, "sec"), limit=10)
    assert len(findings) == 3

    first = findings[0]
    assert first["ticker"] == "TSLA"
    assert first["medium"] == "filings"
    assert first["scout_type"] == "distress"
    assert first["severity"] == "CRITICAL"

    assert findings[1]["ticker"] == "NVDA"
    assert findings[1]["scout_type"] == "competitive"
    assert findings[1]["severity"] == "WARNING"

    assert findings[2]["ticker"] == "UNKNOWN"
    assert findings[2]["severity"] == "INFO"


def test_news_source_maps_to_news_medium(tmp_path):
    findings = IngestAdapter("news").collect(_source(tmp_path, "news"), limit=10)
    assert all(f["medium"] == "news" for f in findings)


def test_collect_offline(tmp_path):
    path = tmp_path / "sec.json"
    path.write_text(json.dumps(ROWS))
    findings = collect_offline([f"sec={path}"], limit=10)
    assert len(findings) == 3
    assert findings[0]["medium"] == "filings"


def test_end_to_end_offline_loop(tmp_path):
    from core_framework.bin.scout_vehicle import ScoutLeaderboard, ScoutVehicle
    from core_framework.shared.adaptive_memory import AdaptiveQueryMemory

    mem = AdaptiveQueryMemory(path=tmp_path / "mem.json", exploration_rate=0.0)
    ledger = ScoutLeaderboard(leaderboard_path=tmp_path / "lb.json")
    vehicle = ScoutVehicle(agent_id="Gemini-Core-Partner", leaderboard=ledger, adaptive_memory=mem)

    payload = vehicle.run_ingested_patrol(
        _source(tmp_path, "sec"),
        limit=10,
        query_pattern="debt covenant default risk",
    )

    # 3 findings translated to buildings; scored findings tracked.
    assert len(payload["data"]["city"]["buildings"]) == 3
    assert len(vehicle.processed_findings) == 3

    exported = vehicle.export_alpha_streams(output_dir=tmp_path)
    assert exported["rows"] == 3
    assert Path(exported["alpha_stream_csv"]).exists()

    # Adaptive memory learned from the run.
    assert "sec::debt covenant default risk" in mem.records
    assert mem.records["sec::debt covenant default risk"].pheromone > 0
