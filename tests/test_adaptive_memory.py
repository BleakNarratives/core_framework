#!/usr/bin/env python3
"""
core_framework/tests/test_adaptive_memory.py

Deterministic tests for AdaptiveQueryMemory: reward, decay, exploration,
mutation, persistence, and the ScoutVehicle integration hook.
"""

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.shared.adaptive_memory import AdaptiveQueryMemory  # noqa: E402


class FakeClock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _memory(tmp_path, clock, exploration_rate=0.0):
    return AdaptiveQueryMemory(
        path=tmp_path / "mem.json",
        clock=clock,
        exploration_rate=exploration_rate,
        rng=random.Random(1234),
    )


def test_reward_accumulates_pheromone(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock)
    rec = mem.record_run("debt covenant default risk", "sec_8k", payload_bytes=1000, high_alpha_count=4, confidence=0.88)
    assert rec.pheromone > 0
    assert rec.high_alpha_yield_count == 4
    assert rec.yield_ratio == 4 / 1000


def test_pheromone_decays_half_life(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock)
    rec = mem.record_run("risk", "src", payload_bytes=100, high_alpha_count=2, confidence=1.0)
    peak = rec.pheromone
    clock.advance(mem.half_life_seconds)
    ranked = mem.top_patterns(limit=1)
    assert ranked[0].pheromone == round(peak * 0.5, 0) or abs(ranked[0].pheromone - peak / 2) < 1e-6


def test_zero_yield_adds_no_pheromone_then_decays(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock)
    mem.record_run("sentiment", "news", payload_bytes=500, high_alpha_count=3, confidence=0.5)
    peak = mem.records["news::sentiment"].pheromone
    clock.advance(1000)
    mem.record_run("sentiment", "news", payload_bytes=500, high_alpha_count=0, confidence=0.0)
    assert mem.records["news::sentiment"].pheromone < peak


def test_exploration_rate_controls_mutation(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock, exploration_rate=1.0)
    mem.record_run("debt default", "sec", payload_bytes=100, high_alpha_count=5, confidence=0.9)
    plan = mem.plan(limit=3)
    assert any(p["explored"] for p in plan)

    mem2 = _memory(tmp_path / "b", clock, exploration_rate=0.0)
    mem2.record_run("debt default", "sec", payload_bytes=100, high_alpha_count=5, confidence=0.9)
    plan2 = mem2.plan(limit=3)
    assert plan2 and not any(p["explored"] for p in plan2)


def test_mutate_query_changes_tokens():
    rng = random.Random(7)
    out = AdaptiveQueryMemory.mutate_query("debt covenant risk", rng)
    assert out != "debt covenant risk"


def test_persistence_roundtrip(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock)
    mem.record_run("revenue growth", "filings", payload_bytes=200, high_alpha_count=1, confidence=0.7)
    reloaded = AdaptiveQueryMemory(path=tmp_path / "mem.json", clock=clock)
    assert "filings::revenue growth" in reloaded.records


def test_scout_vehicle_adaptive_hook(tmp_path):
    from core_framework.bin.scout_vehicle import ScoutLeaderboard, ScoutVehicle

    clock = FakeClock()
    mem = _memory(tmp_path, clock, exploration_rate=0.0)
    ledger = ScoutLeaderboard(leaderboard_path=tmp_path / "lb.json")
    vehicle = ScoutVehicle(agent_id="Gemini-Core-Partner", leaderboard=ledger, adaptive_memory=mem)
    vehicle.run_patrol_pass(
        ["TSLA"],
        [{"ticker": "TSLA", "scout_type": "distress", "severity": "CRITICAL",
          "signals": ["debt covenant breach"], "confidence": 0.92}],
    )
    snapshot = vehicle.record_adaptive_yields("debt covenant default risk", "sec_8k")
    assert snapshot is not None
    assert snapshot["pheromone"] > 0
    # plan surfaces the learned pattern
    plan = vehicle.plan_adaptive_watchlist(limit=3)
    assert any(p["query_pattern"] == "debt covenant default risk" for p in plan)


def test_scout_vehicle_without_adaptive_memory_is_noop(tmp_path):
    from core_framework.bin.scout_vehicle import ScoutLeaderboard, ScoutVehicle

    ledger = ScoutLeaderboard(leaderboard_path=tmp_path / "lb.json")
    vehicle = ScoutVehicle(leaderboard=ledger)
    assert vehicle.plan_adaptive_watchlist() == []
    assert vehicle.record_adaptive_yields("anything") is None
