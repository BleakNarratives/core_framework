import json
import os
import time
import logging
import asyncio
import sys

# Add venv to path to access installed dependencies
sys.path.insert(0, os.path.abspath(".venv/lib/python3.13/site-packages"))

from typing import Dict, List, Any
from core_framework.adapters.market_twin import MarketTwinTranslator

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
# Janus / JaneBox Leaderboard Engine
# ---------------------------------------------------------------------------
class ScoutLeaderboard:
    """Tracks agent/model discovery precision, deduplication, and scoring."""
    
    def __init__(self, leaderboard_path: str = "scout_leaderboard.json"):
        self.path = leaderboard_path
        self.scores = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"agents": {}, "seen_signals": []}

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.scores, f, indent=2)

    def record_finding(self, agent_id: str, finding: Dict[str, Any]) -> int:
        ticker = finding.get("ticker", "UNKNOWN")
        scout_type = finding.get("scout_type", "general")
        severity = finding.get("severity", "INFO")
        
        # Unique fingerprint to prevent duplicate scoring
        fingerprint = f"{ticker}:{scout_type}:{severity}"
        if fingerprint in self.scores["seen_signals"]:
            return 0  # No points for redundant findings

        self.scores["seen_signals"].append(fingerprint)

        # Base scoring matrix
        base_points = {"CRITICAL": 100, "WARNING": 50, "INFO": 10}.get(severity, 10)
        confidence = finding.get("confidence", 0.5)
        points = int(base_points * confidence)

        # Update Agent Stats
        if agent_id not in self.scores["agents"]:
            self.scores["agents"][agent_id] = {"total_score": 0, "discoveries": 0, "critical_hits": 0}

        stats = self.scores["agents"][agent_id]
        stats["total_score"] += points
        stats["discoveries"] += 1
        if severity == "CRITICAL":
            stats["critical_hits"] += 1

        self.save()
        return points

# ---------------------------------------------------------------------------
# Autonomous Scout Vehicle
# ---------------------------------------------------------------------------
class ScoutVehicle:
    """Autonomous workbench driver that executes patrol passes across target watchlists."""
    
    def __init__(self, agent_id: str = "Gemini-Free-Swarm"):
        self.agent_id = agent_id
        self.leaderboard = ScoutLeaderboard()
        self.translator = MarketTwinTranslator()

    def run_patrol_pass(self, watchlist: List[str], raw_scout_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Executes a patrol run, scores findings, and translates to 3D Market Twin state."""
        print(f"=== [SCOUT VEHICLE] ACTIVE PATROL PASS ({self.agent_id}) ===")
        print(f"Target Watchlist: {', '.join(watchlist)}")

        scored_count = 0
        total_points = 0

        for finding in raw_scout_results:
            pts = self.leaderboard.record_finding(self.agent_id, finding)
            if pts > 0:
                scored_count += 1
                total_points += pts
            self.translator.add_axe_scout_finding(finding)

        ws_payload = self.translator.to_ws_payload()
        print(f"Patrol Complete: {scored_count} unique findings scored (+{total_points} pts).")
        print(f"3D Scene Built : {len(ws_payload['data']['city']['buildings'])} buildings, "
              f"{len(ws_payload['data']['city']['monsters'])} monsters.")
        
        return ws_payload

    async def broadcast_payload(self, ws_url: str = DEFAULT_WS_URL) -> None:
        """Connect to the Code City TCP/Socket backend and broadcast the current twin payload."""
        import socket
        from urllib.parse import urlparse

        if not self.translator.buildings and not self.translator.monsters:
            logger.info("No market-twin entities to broadcast.")
            return

        payload = self.translator.to_ws_payload()
        message = json.dumps(payload)

        parsed_url = urlparse(ws_url)
        host = parsed_url.hostname or "localhost"
        port = parsed_url.port or 8765

        print(f"[ScoutVehicle] Connecting to {host}:{port} to broadcast market twin via TCP...")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((host, port))
                s.sendall(message.encode('utf-8'))
                print("[ScoutVehicle] Broadcast successful.")
        except Exception as exc:
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
            "confidence": 0.92
        },
        {
            "ticker": "NVDA",
            "scout_type": "competitive",
            "severity": "WARNING",
            "signals": ["Custom ASIC displacement"],
            "confidence": 0.78
        }
    ]

    vehicle = ScoutVehicle(agent_id="Gemini-Core-Partner")
    payload = vehicle.run_patrol_pass(watchlist, mock_agent_discoveries)

    ws_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WS_URL
    asyncio.run(vehicle.broadcast_payload(ws_url))
