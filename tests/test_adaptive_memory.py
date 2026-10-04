#!/usr/bin/env python3
"""
core_framework/tests/test_adaptive_memory.py

Deterministic tests for AdaptiveQueryMemory: reward, decay, exploration,
mutation, persistence, and the ScoutVehicle integration hook.
"""

import json
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


def test_state_accumulates_across_runs(tmp_path):
    # The actual persistence contract: state written in run 1 is not merely
    # re-readable in run 2, it is *built upon* (runs increment, pheromone grows).
    clock = FakeClock()
    path = tmp_path / "mem.json"

    run1 = AdaptiveQueryMemory(path=path, clock=clock)
    r1 = run1.record_run("debt covenant", "sec", payload_bytes=100, high_alpha_count=2, confidence=0.9)
    p1, runs1 = r1.pheromone, r1.runs

    clock.advance(60)
    run2 = AdaptiveQueryMemory(path=path, clock=clock)  # fresh process, same file
    r2 = run2.record_run("debt covenant", "sec", payload_bytes=100, high_alpha_count=2, confidence=0.9)

    assert r2.runs == runs1 + 1
    assert r2.pheromone > p1  # decay over 60 s is tiny; accumulation dominates
    assert r2.high_alpha_yield_count == 4


def test_save_is_atomic_and_leaves_no_tmp(tmp_path):
    clock = FakeClock()
    mem = _memory(tmp_path, clock)
    mem.record_run("q", "src", payload_bytes=10, high_alpha_count=1, confidence=0.5)
    mem.record_run("q", "src", payload_bytes=10, high_alpha_count=1, confidence=0.5)

    path = tmp_path / "mem.json"
    assert not (tmp_path / "mem.json.tmp").exists()  # temp is replaced, not left
    data = json.loads(path.read_text())  # live file is always complete JSON
    assert data["records"]["src::q"]["runs"] == 2


def test_corrupt_memory_is_quarantined_not_clobbered(tmp_path, capsys):
    path = tmp_path / "mem.json"
    path.write_text('{"records": {"src::q": {"run')  # torn write garbage

    mem = AdaptiveQueryMemory(path=path, clock=FakeClock())
    assert mem.records == {}  # starts empty...
    assert "corrupt memory quarantined" in capsys.readouterr().err
    quarantined = list(tmp_path.glob("mem.json.corrupt-*"))
    assert len(quarantined) == 1  # ...but the broken bytes survive for forensics
    assert "torn write garbage" in quarantined[0].read_text() or 'src::q' in quarantined[0].read_text()

    # The next save writes a fresh valid file and does NOT delete the quarantine.
    mem.record_run("q", "src", payload_bytes=5, high_alpha_count=1, confidence=0.5)
    assert json.loads(path.read_text())["records"]["src::q"]["runs"] == 1
    assert len(list(tmp_path.glob("mem.json.corrupt-*"))) == 1


def test_stale_tmp_file_does_not_break_saving(tmp_path):
    # A crash between temp-write and replace leaves a .tmp behind; the next
    # save must overwrite it and keep the live file valid.
    path = tmp_path / "mem.json"
    (tmp_path / "mem.json.tmp").write_text("garbage")

    mem = AdaptiveQueryMemory(path=path, clock=FakeClock())
    mem.record_run("q", "src", payload_bytes=5, high_alpha_count=1, confidence=0.5)

    assert json.loads(path.read_text())["records"]["src::q"]["runs"] == 1
    assert not (tmp_path / "mem.json.tmp").exists()


def test_pheromone_decay_survives_process_restart(tmp_path):
    # Decay is lazy: it is recomputed from the persisted ``last_decay_utc``
    # whenever a later process reads or records. This proves the decay clock
    # itself survives termination — a reboot cannot reset the pheromone.
    clock = FakeClock()
    path = tmp_path / "mem.json"
    mem1 = AdaptiveQueryMemory(path=path, clock=clock, exploration_rate=0.0)
    mem1.record_run("debt covenant", "sec", payload_bytes=100, high_alpha_count=4, confidence=1.0)
    peak = mem1.records["sec::debt covenant"].pheromone  # 4 * (0.5 + 1.0) = 6

    clock.advance(mem1.half_life_seconds)  # one full half-life passes, then "reboot"
    mem2 = AdaptiveQueryMemory(path=path, clock=clock, exploration_rate=0.0)
    ranked = mem2.top_patterns(limit=1)
    assert abs(ranked[0].pheromone - peak / 2) < 1e-6


def test_saved_decay_config_is_restored_and_explicit_wins(tmp_path):
    # Scoring-weight config (half-life, exploration rate) is persisted with the
    # history and restored on load, so run-over-run semantics are stable even
    # when the next process uses different constructor defaults. An explicit
    # constructor value still outranks the saved file.
    clock = FakeClock()
    path = tmp_path / "mem.json"
    mem1 = AdaptiveQueryMemory(
        path=path, clock=clock, half_life_seconds=100.0, exploration_rate=0.25
    )
    mem1.record_run("q", "src", payload_bytes=5, high_alpha_count=1, confidence=0.5)

    reloaded = AdaptiveQueryMemory(path=path, clock=clock)  # no explicit config
    assert reloaded.half_life_seconds == 100.0
    assert reloaded.exploration_rate == 0.25

    overridden = AdaptiveQueryMemory(path=path, clock=clock, half_life_seconds=999.0)
    assert overridden.half_life_seconds == 999.0


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
