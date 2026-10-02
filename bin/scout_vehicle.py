import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Allow direct execution (`python core_framework/bin/scout_vehicle.py`) from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core_framework.shared.adaptive_memory import AdaptiveQueryMemory  # noqa: E402
from core_framework.shared.config import (  # noqa: E402
    LEADERBOARD_PATH,
    OUTPUT_DIR,
    inject_venv_paths,
)

# Resolve a venv that actually has `websockets` before attempting the import.
inject_venv_paths("websockets")

from core_framework.adapters.market_twin import MarketTwinTranslator  # noqa: E402

try:
    import websockets
except ImportError:  # pragma: no cover - optional broadcaster dependency
    websockets = None

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ScoutVehicle")

# Default WebSocket endpoint for the Code City backend
DEFAULT_WS_URL = os.getenv("CODE_CITY_WS_URL", "ws://localhost:8765")

# ---------------------------------------------------------------------------
# Medium-agnostic asymmetric scoring constants
#
# Points = Base Value * Difficulty Multiplier * Confidence * Novelty
# plus cross-medium verification bounties and false-positive penalties.
# ---------------------------------------------------------------------------
MEDIUM_PROFILES: Dict[str, Dict[str, Any]] = {
    # Dense, high-context, near-ground-truth documents (Gemini CLI).
    "filings": {"base": 50, "multiplier": 3.5, "tier": "deep"},
    "regulatory": {"base": 50, "multiplier": 3.5, "tier": "deep"},
    # Rapid, low-context, variable signal-to-noise feeds (Vibe CLI).
    "news": {"base": 10, "multiplier": 1.0, "tier": "fast"},
    "social": {"base": 10, "multiplier": 1.0, "tier": "fast"},
    # Unknown / unclassified medium: between the two extremes.
    "general": {"base": 25, "multiplier": 1.5, "tier": "general"},
}
DEFAULT_MEDIUM = "general"

CROSS_MEDIUM_BOUNTY = 100   # deep agent confirms a fast agent's early signal
EARLY_PREDICTOR_BONUS = 25  # retroactive credit to the fast agent
FALSE_POSITIVE_PENALTY = -20

NOVELTY_DECAY_SECONDS = 24 * 60 * 60.0  # full novelty recovered after one day
NOVELTY_MIN_INTERVAL = 5 * 60.0         # ignore exact repeats within five minutes

# A fast "early signal" only counts as confirmable while it is fresh. Without a
# TTL, a pending signal from an old run could win a cross-medium bounty much
# later — long after the news stopped being news.
PENDING_SIGNAL_TTL_SECONDS = 3 * 24 * 60 * 60.0  # 3 days


# ---------------------------------------------------------------------------
# Janus / JaneBox Leaderboard Engine
# ---------------------------------------------------------------------------
class ScoutLeaderboard:
    """Tracks agent/model discovery precision, deduplication, and scoring.

    Persistence format (scout_leaderboard.json):
        {
          "agents": {agent_id: {...stats...}},
          "seen_signals": {"agent_id::ticker:type:severity": {"ts": float, "agent": str}},
          "pending_signals": {signal_key: {...}}
        }

    ``seen_signals`` is agent-scoped so cross-medium confirmation (two agents
    on one signal) is possible, while a single looping agent is still deduped.
    Legacy files that stored ``seen_signals`` as a plain list, or as unscoped
    fingerprints, are read and supported on load; see ``_load``.
    """

    def __init__(
        self,
        leaderboard_path: str | Path | None = None,
        clock=time.time,
        novelty_decay_seconds: float = NOVELTY_DECAY_SECONDS,
        novelty_min_interval: float = NOVELTY_MIN_INTERVAL,
        pending_signal_ttl_seconds: float = PENDING_SIGNAL_TTL_SECONDS,
    ):
        self.path = Path(leaderboard_path) if leaderboard_path else Path(LEADERBOARD_PATH)
        self._clock = clock
        self.novelty_decay_seconds = novelty_decay_seconds
        self.novelty_min_interval = novelty_min_interval
        self.pending_signal_ttl_seconds = pending_signal_ttl_seconds
        self.scores = self._load()
        self._prune_pending_signals(self._clock())

    # -- persistence --------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        empty = {"agents": {}, "seen_signals": {}, "pending_signals": {}}
        if not self.path.exists():
            return empty
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except Exception:
            return empty

        if not isinstance(data, dict):
            return empty
        data.setdefault("agents", {})
        data.setdefault("pending_signals", {})

        seen = data.get("seen_signals", {})
        if isinstance(seen, list):
            # Legacy format: a flat list of fingerprints with no timestamps.
            # Stamp them with "now" so previously-suppressed duplicates stay
            # suppressed for at least the minimum interval after migration.
            now = self._clock()
            data["seen_signals"] = {fp: {"ts": now, "agent": "legacy"} for fp in seen}
        elif not isinstance(seen, dict):
            data["seen_signals"] = {}
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.scores, f, indent=2)

    def _prune_pending_signals(self, now: float) -> list[str]:
        """Drop pending signals older than the TTL. Returns the pruned keys."""
        pending = self.scores.get("pending_signals")
        if not isinstance(pending, dict):
            self.scores["pending_signals"] = {}
            return []
        expired = [
            key for key, value in pending.items()
            if not isinstance(value, dict)
            or (now - float(value.get("ts", 0.0))) > self.pending_signal_ttl_seconds
        ]
        for key in expired:
            del pending[key]
        return expired

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def resolve_medium(agent_id: str, finding: Dict[str, Any]) -> str:
        """Classify a finding's medium, preferring an explicit field.

        Falls back to agent-name heuristics so existing callers that never set
        ``medium`` still get sane asymmetric weighting.
        """
        explicit = str(finding.get("medium", "")).lower()
        if explicit in MEDIUM_PROFILES:
            return explicit
        lowered = (agent_id or "").lower()
        if "gemini" in lowered or "filing" in lowered or "sec" in lowered:
            return "filings"
        if "vibe" in lowered or "news" in lowered or "social" in lowered:
            return "news"
        return DEFAULT_MEDIUM

    def _agent(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self.scores["agents"]:
            self.scores["agents"][agent_id] = {
                "total_score": 0,
                "discoveries": 0,
                "critical_hits": 0,
                "bounties": 0,
                "early_predictor_bonuses": 0,
                "false_positives": 0,
                "penalty_points": 0,
            }
        stats = self.scores["agents"][agent_id]
        # Backfill keys for agents loaded from older leaderboard files.
        for key, default in (
            ("bounties", 0),
            ("early_predictor_bonuses", 0),
            ("false_positives", 0),
            ("penalty_points", 0),
        ):
            stats.setdefault(key, default)
        return stats

    def _credit(self, agent_id: str, points: int, severity: str) -> int:
        stats = self._agent(agent_id)
        stats["total_score"] += points
        if points > 0:
            stats["discoveries"] += 1
        if severity == "CRITICAL" and points > 0:
            stats["critical_hits"] += 1
        return points

    # -- scoring ------------------------------------------------------------
    def record_finding(self, agent_id: str, finding: Dict[str, Any]) -> int:
        """Score one finding and return the points credited to ``agent_id``.

        Formula: ``Base Value * Difficulty Multiplier * Confidence * Novelty``.

        Side effects beyond ``agent_id``:
          * A deep (filings/regulatory) finding that confirms a fast
            (news/social) agent's pending signal earns the deep agent a
            ``+CROSS_MEDIUM_BOUNTY``; the original fast agent retroactively
            earns ``+EARLY_PREDICTOR_BONUS``.
          * A finding flagged ``false_positive`` applies
            ``FALSE_POSITIVE_PENALTY`` and returns that negative value.

        Returns 0 for exact repeats inside the novelty minimum interval.
        """
        ticker = finding.get("ticker", "UNKNOWN")
        scout_type = finding.get("scout_type", "general")
        severity = finding.get("severity", "INFO")
        confidence = float(finding.get("confidence", 0.5))
        medium = self.resolve_medium(agent_id, finding)

        # False positives are penalised regardless of prior sightings.
        if finding.get("false_positive"):
            stats = self._agent(agent_id)
            stats["false_positives"] += 1
            stats["penalty_points"] += FALSE_POSITIVE_PENALTY
            stats["total_score"] += FALSE_POSITIVE_PENALTY
            self.save()
            return FALSE_POSITIVE_PENALTY

        now = self._clock()
        self._prune_pending_signals(now)
        fingerprint = f"{ticker}:{scout_type}:{severity}"
        signal_key = f"{ticker}:{scout_type}"

        # Deduplicate per agent: a single loop agent must not farm points by
        # resubmitting the same signal, but two different agents reporting the
        # same signal legitimately score (that is the cross-medium case).
        seen = self.scores["seen_signals"]
        scoped_key = f"{agent_id}::{fingerprint}"
        prev = seen.get(scoped_key)
        if prev is None:
            prev = seen.get(fingerprint)  # legacy bare key from pre-migration files
        if prev is not None:
            prev_ts = prev.get("ts", 0.0) if isinstance(prev, dict) else float(prev)
            elapsed = now - prev_ts
            if elapsed < self.novelty_min_interval:
                return 0
            novelty = min(1.0, elapsed / self.novelty_decay_seconds)
        else:
            novelty = 1.0
        seen[scoped_key] = {"ts": now, "agent": agent_id}

        profile = MEDIUM_PROFILES.get(medium, MEDIUM_PROFILES[DEFAULT_MEDIUM])
        points = int(round(profile["base"] * profile["multiplier"] * confidence * novelty))

        # Cross-medium verification.
        if profile["tier"] == "deep":
            pending = self.scores["pending_signals"].get(signal_key)
            if pending and pending.get("agent_id") != agent_id:
                points += CROSS_MEDIUM_BOUNTY
                self._agent(agent_id)["bounties"] += 1
                predictor = pending.get("agent_id")
                if predictor:
                    self._agent(predictor)["early_predictor_bonuses"] += 1
                    self._credit(predictor, EARLY_PREDICTOR_BONUS, "INFO")
                del self.scores["pending_signals"][signal_key]
        elif profile["tier"] == "fast":
            self.scores["pending_signals"][signal_key] = {
                "agent_id": agent_id,
                "ticker": ticker,
                "scout_type": scout_type,
                "ts": now,
            }

        self._credit(agent_id, points, severity)
        self.save()
        return points


# ---------------------------------------------------------------------------
# Autonomous Scout Vehicle
# ---------------------------------------------------------------------------
class ScoutVehicle:
    """Autonomous workbench driver that executes patrol passes across target watchlists."""

    def __init__(
        self,
        agent_id: str = "Gemini-Free-Swarm",
        leaderboard: ScoutLeaderboard | None = None,
        adaptive_memory: AdaptiveQueryMemory | None = None,
    ):
        self.agent_id = agent_id
        self.leaderboard = leaderboard or ScoutLeaderboard()
        self.translator = MarketTwinTranslator()
        self.adaptive = adaptive_memory
        self.processed_findings: List[Dict[str, Any]] = []

    def run_patrol_pass(self, watchlist: List[str], raw_scout_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes a patrol run, scores findings, and translates to 3D Market Twin state."""
        print(f"=== [SCOUT VEHICLE] ACTIVE PATROL PASS ({self.agent_id}) ===")
        print(f"Target Watchlist: {', '.join(watchlist)}")

        scored_count = 0
        total_points = 0

        for finding in raw_scout_results:
            pts = self.leaderboard.record_finding(self.agent_id, finding)
            medium = self.leaderboard.resolve_medium(self.agent_id, finding)
            if pts > 0:
                scored_count += 1
                total_points += pts
            self.processed_findings.append({
                "timestamp": datetime.now().isoformat(),
                "agent_id": self.agent_id,
                "ticker": finding.get("ticker", "UNKNOWN"),
                "scout_type": finding.get("scout_type", "general"),
                "severity": finding.get("severity", "INFO"),
                "confidence": finding.get("confidence", 0.5),
                "medium": medium,
                "points": pts,
                "signals": finding.get("signals", []),
            })
            self.translator.add_axe_scout_finding(finding)

        ws_payload = self.translator.to_ws_payload()
        print(f"Patrol Complete: {scored_count} unique findings scored (+{total_points} pts).")
        print(f"3D Scene Built : {len(ws_payload['data']['city']['buildings'])} buildings, "
              f"{len(ws_payload['data']['city']['monsters'])} monsters.")

        return ws_payload

    def run_ingested_patrol(
        self,
        source: Any,
        limit: int = 20,
        query_pattern: str | None = None,
    ) -> Dict[str, Any]:
        """Ingest from a TrendSource, then run a normal, scored patrol pass.

        This closes the offline loop: source -> findings -> score -> translate ->
        export, with no network. When adaptive memory is attached and a
        ``query_pattern`` is given, the run's yield is recorded too.
        """
        from core_framework.adapters.ingest_adapter import IngestAdapter

        adapter = IngestAdapter(getattr(source, "name", "local"))
        findings = adapter.collect(source, limit=limit)
        watchlist = sorted({f["ticker"] for f in findings if f.get("ticker") != "UNKNOWN"})
        payload = self.run_patrol_pass(watchlist or ["UNKNOWN"], findings)
        if self.adaptive is not None and query_pattern:
            self.record_adaptive_yields(query_pattern, getattr(source, "name", "local"))
        return payload

    # -- adaptive loop (optional; no-op without an AdaptiveQueryMemory) ----
    def plan_adaptive_watchlist(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Observe past yields and propose the next query/source set.

        Returns an empty list when no adaptive memory is attached, so callers
        can always invoke this without changing default behaviour.
        """
        if self.adaptive is None:
            return []
        return self.adaptive.plan(limit=limit)

    def record_adaptive_yields(
        self,
        query_pattern: str,
        data_source: str = "scout_vehicle",
        high_alpha_threshold: int = 100,
    ) -> Dict[str, Any] | None:
        """Feed this patrol's outcome back into the adaptive memory.

        A "high alpha" finding is one whose score clears
        ``high_alpha_threshold``. Returns the updated record snapshot, or None
        when no adaptive memory is attached.
        """
        if self.adaptive is None:
            return None
        payload_bytes = sum(len(json.dumps(f.get("signals", []))) for f in self.processed_findings)
        high_alpha = sum(1 for f in self.processed_findings if f.get("points", 0) >= high_alpha_threshold)
        confidences = [float(f.get("confidence", 0.0)) for f in self.processed_findings]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        record = self.adaptive.record_run(
            query_pattern,
            data_source,
            payload_bytes=payload_bytes,
            high_alpha_count=high_alpha,
            confidence=confidence,
        )
        return {
            "query_pattern": record.query_pattern,
            "data_source": record.data_source,
            "pheromone": round(record.pheromone, 4),
            "high_alpha_yield_count": record.high_alpha_yield_count,
            "yield_ratio": round(record.yield_ratio, 6),
        }

    # -- commercial exporters (dual stream) --------------------------------
    def export_alpha_streams(self, output_dir: str | Path | None = None) -> Dict[str, Any]:
        """Write both commercial output streams to disk.

        Stream A: ``market_twin.json``  - 3D spatial payload + scene + leaderboard snapshot.
        Stream B: ``alpha_stream.csv``  - per-finding distress intelligence for buyers.

        Returns a dict of written paths and the CSV row count.
        """
        out = Path(output_dir) if output_dir else Path(OUTPUT_DIR)
        out.mkdir(parents=True, exist_ok=True)

        market_path = out / "market_twin.json"
        alpha_path = out / "alpha_stream.csv"

        payload = self.translator.to_ws_payload()
        snapshot = {
            "generated_at": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "spatial_payload": payload,
            "leaderboard": self.leaderboard.scores,
        }
        with open(market_path, "w") as f:
            json.dump(snapshot, f, indent=2)

        fieldnames = [
            "timestamp", "agent_id", "ticker", "scout_type",
            "severity", "confidence", "medium", "points", "signals",
        ]
        with open(alpha_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.processed_findings:
                record = dict(row)
                record["signals"] = "; ".join(str(s) for s in record.get("signals", []))
                writer.writerow(record)

        return {
            "market_twin_json": str(market_path),
            "alpha_stream_csv": str(alpha_path),
            "rows": len(self.processed_findings),
        }

    async def broadcast_payload(self, ws_url: str = DEFAULT_WS_URL) -> None:
        """Broadcast the current twin payload to the Code City WebSocket backend.

        The backend is a ``websockets`` server (see
        ``Code-City-Apocalypse/backend/server.py``), so a raw TCP write is not
        valid here: the connection must complete a WebSocket handshake. This
        method degrades gracefully (logs and returns) when the server is down or
        ``websockets`` is unavailable, so it is safe to background.
        """
        if not self.translator.buildings and not self.translator.monsters:
            logger.info("No market-twin entities to broadcast.")
            return

        if websockets is None:
            logger.error(
                "websockets not installed and no candidate venv provided it; "
                "cannot broadcast market twin to %s.",
                ws_url,
            )
            return

        message = json.dumps(self.translator.to_ws_payload())
        print(f"[ScoutVehicle] Connecting to {ws_url} to broadcast market twin...")
        try:
            async with websockets.connect(ws_url, open_timeout=5.0, close_timeout=5.0) as ws:
                await ws.send(message)
            print("[ScoutVehicle] Broadcast successful.")
        except Exception as exc:  # server down, sandboxed network, etc.
            logger.error(f"[ScoutVehicle] Broadcast failed: {exc}")


# ---------------------------------------------------------------------------
# Standalone Execution Runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    watchlist = ["TSLA", "AAPL", "NVDA", "AMZN"]

    mock_agent_discoveries = [
        {
            "ticker": "TSLA",
            "scout_type": "distress",
            "severity": "CRITICAL",
            "signals": ["Debt covenants breach"],
            "confidence": 0.92,
        },
        {
            "ticker": "NVDA",
            "scout_type": "competitive",
            "severity": "WARNING",
            "signals": ["Custom ASIC displacement"],
            "confidence": 0.78,
        },
    ]

    vehicle = ScoutVehicle(agent_id="Gemini-Core-Partner")
    payload = vehicle.run_patrol_pass(watchlist, mock_agent_discoveries)

    exported = vehicle.export_alpha_streams()
    print(f"Exported alpha streams: {exported}")

    ws_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WS_URL
    asyncio.run(vehicle.broadcast_payload(ws_url))
