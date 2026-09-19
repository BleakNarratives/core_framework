#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: codebuddy-session
# PILLAR: thoth
# ROLE: central-control
# TIER: Brain (1)
# AUTHOR: BleakNarratives
# SESSION: 2026-09-07 MotherBrain scaffold — consumes agent_bus, emits decisions
# [/DNA_TAG]
"""
MotherBrain — central decision / analysis unit for the Thoth ecosystem.

Sits ABOVE agent_bus. Consumes events, runs analysis + predictive + decision
hooks, and emits decisions back onto the bus for Thoth (and the swarm) to act on.

v0 is intentionally minimal and REAL:
  - ingests events from agent_bus since last offset (no replay on first run)
  - analyzes: counts by event_type / source / channel
  - predicts: trivial heuristic (hottest sources) — stub for real ML later
  - decides: rule-based (throttle hot sources; idle when quiet)
  - emits motherbrain.decision events back to the bus

Extension points (the ML / predictive modeling the user wants) live in
predict() and decide() — swap the v0 heuristics for real models without
touching the bus plumbing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Same dir as agent_bus.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_bus  # noqa: E402

STATE_FILE = Path(os.environ.get(
    "MOTHERBRAIN_STATE",
    str(Path(agent_bus.BUS_DIR) / "motherbrain_state.json"),
))


class MotherBrain:
    def __init__(self, source: str = "motherbrain"):
        self.source = source
        self.state = self._load_state()
        # First run: don't replay history — start at the current bus head.
        if "offset" not in self.state:
            self.state["offset"] = agent_bus.current_line_count()
            self._save_state()

    # ---- state persistence ----
    def _load_state(self) -> Dict[str, Any]:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as h:
                    return json.load(h)
            except Exception:
                return {}
        return {}

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as h:
            json.dump(self.state, h, indent=2)

    # ---- ingest: pull new events since last tick ----
    def ingest(self, limit: int = 500) -> List[Dict[str, Any]]:
        events, next_offset = agent_bus.read_events(
            offset=self.state.get("offset", 0), limit=limit
        )
        self.state["offset"] = next_offset
        self._save_state()
        return events

    # ---- analysis: the "analysis of the codebase / event flow" hook ----
    def analyze(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        by_channel: Dict[str, int] = {}
        for e in events:
            et = e.get("event_type", "?")
            src = e.get("source", "?")
            ch = e.get("channel", "?")
            by_type[et] = by_type.get(et, 0) + 1
            by_source[src] = by_source.get(src, 0) + 1
            by_channel[ch] = by_channel.get(ch, 0) + 1
        return {
            "ingested": len(events),
            "by_event_type": by_type,
            "by_source": by_source,
            "by_channel": by_channel,
        }

    # ---- predictive modeling hook (stub for real ML) ----
    def predict(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        hot = sorted(
            analysis.get("by_source", {}).items(),
            key=lambda x: -x[1],
        )[:3]
        return {
            "hot_sources": [s for s, _ in hot],
            "model_version": "v0-heuristic",
        }

    # ---- decision making ----
    def decide(
        self,
        analysis: Dict[str, Any],
        prediction: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []
        # v0 rule: any source emitting > 5 events in one tick gets throttled.
        for src, cnt in analysis.get("by_source", {}).items():
            if cnt > 5:
                decisions.append({
                    "decision": "throttle",
                    "target_source": src,
                    "reason": f"{cnt} events in last tick",
                })
        if not decisions:
            decisions.append({
                "decision": "idle",
                "reason": f"no throttle needed (ingested={analysis.get('ingested', 0)})",
            })
        return decisions

    # ---- emit decisions back onto the bus ----
    def emit_decisions(self, decisions: List[Dict[str, Any]]) -> None:
        for d in decisions:
            agent_bus.emit_event(
                "motherbrain.decision",
                payload=d,
                source=self.source,
                channel="motherbrain",
                tags=["decision"],
            )

    # ---- main loop tick ----
    def tick(self) -> Dict[str, Any]:
        events = self.ingest()
        analysis = self.analyze(events)
        prediction = self.predict(analysis)
        decisions = self.decide(analysis, prediction)
        self.emit_decisions(decisions)
        return {
            "analysis": analysis,
            "prediction": prediction,
            "decisions": decisions,
        }


if __name__ == "__main__":
    mb = MotherBrain()
    result = mb.tick()
    print(json.dumps(result, indent=2))
