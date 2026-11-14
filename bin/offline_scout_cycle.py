#!/usr/bin/env python3
"""Run one bounded, fixture-backed scout cycle and export a traceable report.

This is deliberately offline by default. It reuses the canonical core_framework
ingestion, scoring, and export pipeline; it does not pretend fixture runs are
live market intelligence or model training.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core_framework.adapters.ingest_adapter import collect_offline
from core_framework.bin.scout_vehicle import ScoutLeaderboard, ScoutVehicle
from core_framework.shared.adaptive_memory import AdaptiveQueryMemory
from core_framework.shared.config import FRAMEWORK_ROOT, OUTPUT_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")

    specs = [
        f"sec={FRAMEWORK_ROOT / 'fixtures' / 'sec_filings.json'}",
        f"news={FRAMEWORK_ROOT / 'fixtures' / 'news_feed.json'}",
    ]
    findings = collect_offline(specs, limit=args.limit)
    # Preserve source URLs in the report evidence fields by loading the fixture
    # records separately; adapters currently normalize them away.
    evidence = []
    for spec in specs:
        source, _, filename = spec.partition("=")
        path = Path(filename)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload[:args.limit]:
            evidence.append({"source": source, **item})

    args.output.mkdir(parents=True, exist_ok=True)
    vehicle = ScoutVehicle(
        agent_id="core-framework-offline",
        leaderboard=ScoutLeaderboard(leaderboard_path=args.output / "scout_leaderboard.json"),
        adaptive_memory=AdaptiveQueryMemory(path=args.output / "adaptive_memory.json"),
    )
    watchlist = sorted({item["ticker"] for item in findings if item.get("ticker") != "UNKNOWN"})
    vehicle.run_patrol_pass(watchlist or ["UNKNOWN"], findings)
    vehicle.record_adaptive_yields("fixture distress monitoring", "offline-fixtures")
    exported = vehicle.export_alpha_streams(output_dir=args.output)
    report = {
        "mode": "offline-fixtures",
        "warning": "Fixture demonstration only; not live data, validated predictions, or investment advice.",
        "findings": vehicle.processed_findings,
        "evidence": evidence,
        "exports": exported,
    }
    report_path = args.output / "scout_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Offline scout cycle complete: {len(findings)} findings -> {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
