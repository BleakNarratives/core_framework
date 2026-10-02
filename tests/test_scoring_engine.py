#!/usr/bin/env python3
"""
core_framework/tests/test_scoring_engine.py

Deterministic tests for the asymmetric medium-agnostic ScoutLeaderboard.

All timing is injected via a fake clock so novelty behaviour is reproducible
and no test depends on wall-clock time.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.bin.scout_vehicle import (  # noqa: E402
    CROSS_MEDIUM_BOUNTY,
    EARLY_PREDICTOR_BONUS,
    FALSE_POSITIVE_PENALTY,
    ScoutLeaderboard,
)


class FakeClock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def ledger(tmp_path):
    clock = FakeClock()
    lb = ScoutLeaderboard(leaderboard_path=tmp_path / "lb.json", clock=clock)
    return lb, clock


def _finding(ticker="TSLA", scout_type="distress", severity="CRITICAL", confidence=0.9, medium=None):
    finding = {
        "ticker": ticker,
        "scout_type": scout_type,
        "severity": severity,
        "confidence": confidence,
        "signals": ["test signal"],
    }
    if medium is not None:
        finding["medium"] = medium
    return finding


def test_asymmetric_medium_weighting(ledger):
    lb, _ = ledger
    filings = lb.record_finding("gemini-cli", _finding("TSLA"))
    news = lb.record_finding("vibe-cli", _finding("AAPL"))
    # filings: 50 * 3.5 * 0.9 ~= 157 ; news: 10 * 1.0 * 0.9 = 9
    assert filings >= 150
    assert news == 9
    assert filings > news * 10


def test_medium_can_be_explicit(ledger):
    lb, _ = ledger
    pts = lb.record_finding("unknown-agent", _finding("MSFT", medium="news"))
    assert pts == 9


def test_duplicate_inside_min_interval_is_zero(ledger):
    lb, _ = ledger
    first = lb.record_finding("gemini-cli", _finding("TSLA"))
    second = lb.record_finding("gemini-cli", _finding("TSLA"))
    assert first > 0
    assert second == 0


def test_novelty_decays_over_time(ledger):
    lb, clock = ledger
    first = lb.record_finding("gemini-cli", _finding("TSLA"))
    clock.advance(lb.novelty_decay_seconds / 2)  # half of full recovery
    second = lb.record_finding("gemini-cli", _finding("TSLA"))
    assert 0 < second < first


def test_cross_medium_bounty_and_early_predictor(ledger):
    lb, _ = ledger
    # Vibe (fast) flags an early distress signal first.
    news_pts = lb.record_finding("vibe-cli", _finding("TSLA", confidence=0.8))
    assert news_pts > 0

    # Gemini (deep) confirms the same ticker:scout_type.
    deep_pts = lb.record_finding("gemini-cli", _finding("TSLA", confidence=0.8))

    # Deep base (50*3.5*0.8=140) plus the cross-medium bounty.
    assert deep_pts >= 140 + CROSS_MEDIUM_BOUNTY
    assert lb.scores["agents"]["gemini-cli"]["bounties"] == 1
    assert lb.scores["agents"]["vibe-cli"]["early_predictor_bonuses"] == 1
    # Vibe retroactively receives the early-predictor bonus.
    assert lb.scores["agents"]["vibe-cli"]["total_score"] == news_pts + EARLY_PREDICTOR_BONUS
    # Pending signal is cleared after confirmation.
    assert "TSLA:distress" not in lb.scores["pending_signals"]


def test_pending_signal_expires_after_ttl(ledger):
    lb, clock = ledger
    lb.record_finding("vibe-cli", _finding("TSLA", confidence=0.8))
    assert "TSLA:distress" in lb.scores["pending_signals"]

    # Let the early signal go stale.
    clock.advance(lb.pending_signal_ttl_seconds + 1)

    deep = lb.record_finding("gemini-cli", _finding("TSLA", confidence=0.8))
    # Base only (50*3.5*0.8 = 140); no cross-medium bounty is granted.
    assert deep == 140
    assert "TSLA:distress" not in lb.scores["pending_signals"]


def test_false_positive_penalty(ledger):
    lb, _ = ledger
    finding = _finding("TSLA")
    finding["false_positive"] = True
    assert lb.record_finding("vibe-cli", finding) == FALSE_POSITIVE_PENALTY
    assert lb.scores["agents"]["vibe-cli"]["false_positives"] == 1


def test_legacy_list_format_migrates(tmp_path):
    import json

    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "agents": {"gemini-cli": {"total_score": 10, "discoveries": 1, "critical_hits": 0}},
        "seen_signals": ["TSLA:distress:CRITICAL"],
    }))

    clock = FakeClock()
    lb = ScoutLeaderboard(leaderboard_path=path, clock=clock)
    assert isinstance(lb.scores["seen_signals"], dict)
    # The legacy fingerprint stays suppressed within the minimum interval.
    assert lb.record_finding("gemini-cli", _finding("TSLA")) == 0
