#!/usr/bin/env python3
"""
core_framework/shared/adaptive_memory.py

Reinforcement memory for the adaptive scouting loop.

This is the *local, network-free* foundation of the free-cloud blueprint:
it stores query/source yield records, applies an exponential pheromone decay,
and selects the next queries with an epsilon-greedy explore/exploit step.

It performs no network I/O and depends only on the standard library, so it is
safe inside GitHub Actions, Modal, or a sandboxed subshell. Cloud persistence
(MongoDB Atlas / Tiger Cloud / Turso) can later mirror ``to_dict()`` — the
in-memory contract is the source of truth here.

Model:
  * Every (data_source, query_pattern) pair is a record.
  * Pheromone accumulates proportional to high-alpha yield and confidence.
  * Pheromone decays exponentially with a configurable half-life.
  * ``plan()`` exploits top-yield patterns and, with probability
    ``exploration_rate``, mutates one of them to "feel around".
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HALF_LIFE_SECONDS = 7 * 24 * 60 * 60.0  # one week
DEFAULT_EXPLORATION_RATE = 0.1                  # ~10% epsilon-greedy exploration

# Small, deterministic synonym/expansion map used when mutating a query.
QUERY_SYNONYMS: dict[str, list[str]] = {
    "distress": ["solvency stress", "liquidity strain"],
    "debt": ["leverage", "credit facility"],
    "covenant": ["credit agreement", "indenture"],
    "risk": ["exposure", "downside"],
    "competitor": ["rival", "market share"],
    "regulatory": ["compliance", "enforcement"],
    "sentiment": ["chatter", "social tone"],
    "revenue": ["top line", "bookings"],
}


@dataclass
class YieldRecord:
    """One query/source pair's running performance."""

    query_pattern: str
    data_source: str
    runs: int = 0
    payload_bytes_total: int = 0
    high_alpha_yield_count: int = 0
    confidence_ema: float = 0.0
    pheromone: float = 0.0
    yield_ratio: float = 0.0
    last_seen_utc: float = 0.0
    last_decay_utc: float = 0.0
    time_of_day_utc: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.data_source}::{self.query_pattern}"


class AdaptiveQueryMemory:
    """JSON-backed reinforcement memory for adaptive query selection."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        half_life_seconds: float | None = None,
        exploration_rate: float | None = None,
        clock=time.time,
        rng: random.Random | None = None,
    ):
        self.path = Path(path) if path else None
        # None means "caller did not pin this knob", which lets the config saved
        # alongside the history be restored on load (so decay/exploration
        # semantics survive process termination and can't silently drift
        # between runs on differently-configured machines). Explicit values
        # always win over the saved file.
        self._half_life_explicit = half_life_seconds is not None
        self._exploration_explicit = exploration_rate is not None
        self.half_life_seconds = (
            half_life_seconds
            if self._half_life_explicit
            else DEFAULT_HALF_LIFE_SECONDS
        )
        self.exploration_rate = (
            exploration_rate
            if self._exploration_explicit
            else DEFAULT_EXPLORATION_RATE
        )
        self._clock = clock
        self._rng = rng or random.Random()
        self.records: dict[str, YieldRecord] = {}
        if self.path and self.path.exists():
            self._load()

    # -- persistence --------------------------------------------------------
    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            # A torn/corrupt file must never be silently clobbered by the next
            # save(): quarantine the broken bytes under a timestamped suffix so
            # they survive for forensics, warn loudly, and start empty. (With
            # atomic saves below this should never fire — it is the safety net.)
            quarantine = self.path.with_name(
                f"{self.path.name}.corrupt-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            try:
                os.replace(self.path, quarantine)
                print(
                    f"[adaptive_memory] corrupt memory quarantined: "
                    f"{self.path} -> {quarantine} ({exc})",
                    file=sys.stderr,
                )
            except OSError:
                print(
                    f"[adaptive_memory] corrupt memory at {self.path} "
                    f"could not be quarantined: {exc}",
                    file=sys.stderr,
                )
            data = {}
        except OSError:
            return  # unreadable path (permissions/fs); treat as empty
        # Restore the decay/exploration config saved with this history so
        # run-over-run semantics hold firm across reboots and machines.
        saved_half_life = data.get("half_life_seconds")
        if saved_half_life is not None and not self._half_life_explicit:
            self.half_life_seconds = float(saved_half_life)
        saved_exploration = data.get("exploration_rate")
        if saved_exploration is not None and not self._exploration_explicit:
            self.exploration_rate = float(saved_exploration)
        for key, raw in (data.get("records") or {}).items():
            try:
                self.records[key] = YieldRecord(**raw)
            except TypeError:
                continue

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "half_life_seconds": self.half_life_seconds,
            "exploration_rate": self.exploration_rate,
            "records": {k: asdict(v) for k, v in self.records.items()},
        }
        # Atomic persistence: write a sibling temp file, fsync it, then
        # os.replace() over the live path. os.replace is atomic on POSIX and
        # same-volume Windows, so a crash mid-write can never leave a torn
        # adaptive_memory.json: every reader sees either the previous full
        # state or the new full state, never a half-written one. Concurrent
        # single-agent writers degrade to last-write-wins, which is correct
        # for one process owning the loop.
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)  # never leave tmp litter
            except OSError:
                pass
            raise

    def to_dict(self) -> dict:
        return {
            "records": {k: asdict(v) for k, v in self.records.items()},
            "half_life_seconds": self.half_life_seconds,
            "exploration_rate": self.exploration_rate,
        }

    # -- decay --------------------------------------------------------------
    def _decay_all(self, now: float) -> None:
        if self.half_life_seconds <= 0:
            return
        for rec in self.records.values():
            last = rec.last_decay_utc or rec.last_seen_utc or now
            dt = max(0.0, now - last)
            if dt > 0:
                rec.pheromone *= 0.5 ** (dt / self.half_life_seconds)
            rec.last_decay_utc = now

    # -- reward -------------------------------------------------------------
    def record_run(
        self,
        query_pattern: str,
        data_source: str,
        *,
        payload_bytes: int = 0,
        high_alpha_count: int = 0,
        confidence: float = 0.0,
        now: float | None = None,
    ) -> YieldRecord:
        """Record one run and reward/decay the pattern accordingly.

        Reward is proportional to high-alpha yield and confidence; a run that
        produces nothing adds no pheromone, and decay is only applied if 
        new yield is actually evaluated.
        """
        now = self._clock() if now is None else now
        if high_alpha_count > 0:
            self._decay_all(now)

        key = f"{data_source}::{query_pattern}"
        rec = self.records.get(key)
        if rec is None:
            rec = YieldRecord(query_pattern=query_pattern, data_source=data_source)
            self.records[key] = rec

        payload_bytes = max(0, int(payload_bytes))
        high_alpha_count = max(0, int(high_alpha_count))
        rec.runs += 1
        rec.payload_bytes_total += payload_bytes
        rec.high_alpha_yield_count += high_alpha_count
        alpha = 0.3
        rec.confidence_ema = (alpha * confidence) + ((1 - alpha) * rec.confidence_ema)
        rec.pheromone += high_alpha_count * (0.5 + confidence)
        rec.yield_ratio = (
            rec.high_alpha_yield_count / rec.payload_bytes_total
            if rec.payload_bytes_total
            else 0.0
        )
        rec.last_seen_utc = now
        rec.last_decay_utc = now
        rec.time_of_day_utc = datetime.fromtimestamp(now, tz=timezone.utc).hour
        self.save()
        return rec

    # -- selection ----------------------------------------------------------
    def top_patterns(
        self,
        limit: int = 5,
        *,
        time_window_seconds: float | None = None,
        now: float | None = None,
    ) -> list[YieldRecord]:
        now = self._clock() if now is None else now
        self._decay_all(now)
        pool = list(self.records.values())
        if time_window_seconds is not None:
            cutoff = now - time_window_seconds
            pool = [r for r in pool if r.last_seen_utc >= cutoff]
        pool.sort(key=lambda r: (r.pheromone, r.yield_ratio), reverse=True)
        return pool[:limit]

    @staticmethod
    def mutate_query(query: str, rng: random.Random) -> str:
        """Return a lightly mutated query to explore nearby search space."""
        tokens = query.split()
        candidates = [(i, t) for i, t in enumerate(tokens) if t.lower() in QUERY_SYNONYMS]
        if not candidates:
            return f"{query} filing"
        idx, token = rng.choice(candidates)
        replacement = rng.choice(QUERY_SYNONYMS[token.lower()])
        tokens[idx] = replacement
        return " ".join(tokens)

    def plan(self, limit: int = 5, *, now: float | None = None) -> list[dict]:
        """Epsilon-greedy plan: exploit top patterns, mutate one to explore.

        Returns dictionaries ready to feed a patrol run, each tagged with
        ``explored`` and the current ``pheromone``.
        """
        now = self._clock() if now is None else now
        ranked = self.top_patterns(limit=limit, now=now)
        plan: list[dict] = [
            {
                "query_pattern": r.query_pattern,
                "data_source": r.data_source,
                "pheromone": round(r.pheromone, 4),
                "yield_ratio": round(r.yield_ratio, 6),
                "explored": False,
            }
            for r in ranked
        ]

        if plan and self._rng.random() < self.exploration_rate:
            idx = self._rng.randrange(len(plan))
            plan[idx] = dict(plan[idx])
            plan[idx]["query_pattern"] = self.mutate_query(plan[idx]["query_pattern"], self._rng)
            plan[idx]["explored"] = True
        return plan
