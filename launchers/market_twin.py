#!/usr/bin/env python3
"""
core_framework/launchers/market_twin.py

Convenience launcher: runs Vertical AI and feeds its output through the
market-twin adapter into Code City's WebSocket backend.

Usage:
    python market_twin.py --text "expand into healthcare SaaS"
    python market_twin.py --file path/to/plan.txt
"""

import argparse
import logging
import sys
from pathlib import Path

from core_framework.adapters.market_twin import MarketTwinTranslator, ScoutIntel, TrackVerdict, MarketEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def stub_boardroom_and_simulate(text: str) -> tuple[list[ScoutIntel], list[TrackVerdict], list[MarketEvent]]:
    """Stub for the real Vertical AI pipeline. Replace with canonical imports."""
    logger.info("[market_twin] Using stub pipeline; wire to canonical Vertical AI later.")
    scouts = [ScoutIntel(target_name="Acme Corp", segment="enterprise", risk_score=20, opportunity_score=80, value=50000)]
    verdicts = [TrackVerdict(name="Track A", thesis="Land and expand", overall_fitness=82)]
    events = [MarketEvent(event_type="earthquake", segment="regulatory", severity=4, description="New compliance rule")]
    return scouts, verdicts, events


def main():
    parser = argparse.ArgumentParser(description="Market Twin: Vertical AI → Code City")
    parser.add_argument("--text", help="Idea / plan text")
    parser.add_argument("--file", help="Path to a plan document")
    args = parser.parse_args()

    if not args.text and not args.file:
        parser.print_help()
        sys.exit(0)

    text = args.text or Path(args.file).read_text(errors="ignore")

    scouts, verdicts, events = stub_boardroom_and_simulate(text)

    translator = MarketTwinTranslator()
    for intel in scouts:
        translator.add_scout_intel(intel)
    for verdict in verdicts:
        translator.add_track_verdict(verdict)
    for event in events:
        translator.add_market_event(event)

    city_scene = translator.to_city_scene()
    logger.info("City scene ready: %s", city_scene["metadata"])
    print(city_scene)


if __name__ == "__main__":
    main()
