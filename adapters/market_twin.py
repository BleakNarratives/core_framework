#!/usr/bin/env python3
"""
core_framework/adapters/market_twin.py

Real-pipeline translator: Vertical AI -> Code City entity stream.

Pipeline:
  user_input -> boardroom debate -> fractal simulation -> genetic arena ->
  champion track -> Code City buildings / monsters / disasters / agents

No stubs. No placeholders. Real imports from:
  ~/The-Werkz/Official-Vertical-AI-Boardroom/core/boardroom.py
  ~/The-Werkz/Official-Vertical-AI-Boardroom/core/simulator.py
  ~/The-Werkz/Official-Vertical-AI-Boardroom/core/genetics.py
  ~/The-Werkz/Official-Vertical-AI-Boardroom/core/router.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from core_framework.adapters.district_schema import (
    BuildingSpec,
    apply_schema,
    DISTRICTS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical source roots
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERTICAL_AI_ROOT = REPO_ROOT / "The-Werkz" / "Official-Vertical-AI-Boardroom"
sys.path.insert(0, str(VERTICAL_AI_ROOT))
sys.path.insert(0, str(VERTICAL_AI_ROOT / "core"))

# ---------------------------------------------------------------------------
# Real Vertical AI imports - fail loud if canonical tree is broken
# ---------------------------------------------------------------------------
try:
    from core.boardroom import run_boardroom  # noqa: E402
    from core.simulator import run_fractal_simulation  # noqa: E402
    from core.genetics import run_arena  # noqa: E402
    from router import ModelTier  # noqa: E402
    _REAL_IMPORTS = True
except IndentationError as exc:
    _REAL_IMPORTS = False
    _IMPORT_ERROR = (
        "Canonical Vertical AI core/capability_slots.py has an IndentationError "
        f"at line {exc.lineno or '?'}: {exc.msg}. "
        "This blocks all real pipeline imports. "
        "Fix that file first, then rerun."
    )
    run_boardroom = None
    run_fractal_simulation = None
    run_arena = None
    ModelTier = None
except Exception as exc:
    _REAL_IMPORTS = False
    _IMPORT_ERROR = exc
    run_boardroom = None
    run_fractal_simulation = None
    run_arena = None
    ModelTier = None

# ---------------------------------------------------------------------------
# Lightweight input carriers
# ---------------------------------------------------------------------------
class ScoutIntel:
    def __init__(self, target_name: str, segment: str = "local_smb",
                 risk_score: int = 0, opportunity_score: int = 0,
                 value: float = 0.0, sentiment: str = "neutral"):
        self.target_name = target_name
        self.segment = segment
        self.risk_score = risk_score
        self.opportunity_score = opportunity_score
        self.value = value
        self.sentiment = sentiment


class MarketEvent:
    def __init__(self, event_type: str, segment: str, severity: int = 3,
                 description: str = ""):
        self.event_type = event_type
        self.segment = segment
        self.severity = severity
        self.description = description


# ---------------------------------------------------------------------------
# Translator
# ---------------------------------------------------------------------------
from core_framework.adapters.axe_scout_spec import format_axe_finding_to_scout_intel

class MarketTwinTranslator:
    """Converts Vertical AI domain objects into Code City city-scene entities."""

    def __init__(self) -> None:
        self.buildings: list[dict] = []
        self.monsters: list[dict] = []
        self.disasters: list[dict] = []
        self.agents: list[dict] = []

    def reset(self) -> None:
        self.buildings.clear()
        self.monsters.clear()
        self.disasters.clear()
        self.agents.clear()

    def add_axe_scout_finding(self, raw_axe_finding: dict) -> dict:
        """Accepts a raw scan output from AxeScout and converts it to a 3D city entity."""
        intel_dict = format_axe_finding_to_scout_intel(raw_axe_finding)
        intel = ScoutIntel(**intel_dict)
        return self.add_scout_intel(intel)

    def add_scout_intel(self, intel: ScoutIntel) -> dict:
        building_spec = BuildingSpec(
            name=intel.target_name,
            segment=intel.segment,
            value=max(1000, int(intel.value)),
            health=100 - max(0, min(100, intel.risk_score)),
            sentiment=intel.sentiment,
        )
        building = apply_schema(building_spec)
        self.buildings.append(building)

        if intel.risk_score >= 60:
            self.monsters.append({
                "id": f"risk_{intel.target_name.lower().replace(' ', '_')}",
                "type": "sentiment_risk",
                "building_id": building["id"],
                "file_path": f"scout:{intel.target_name}",
                "file_name": intel.target_name,
                "position": {
                    "x": building["position"]["x"] + 5,
                    "y": 3,
                    "z": building["position"]["z"] + 5,
                },
                "severity": max(1, intel.risk_score // 20),
                "message": f"Risk score {intel.risk_score}/100",
                "line": 1,
                "health": max(10, 100 - intel.risk_score),
                "color": "#ff0000",
            })
        return building

    def add_track_verdict(self, verdict) -> dict:
        name = getattr(verdict, "name", str(verdict))
        fitness = float(getattr(verdict, "overall_fitness", 0.0))
        fatal_flaw = getattr(verdict, "fatal_flaw", None)
        segment = "enterprise" if fitness >= 70 else "local_smb"
        building_spec = BuildingSpec(
            name=name,
            segment=segment,
            value=max(1000, int(fitness * 1000)),
            health=100 if fitness >= 60 else 50,
            sentiment="positive" if fitness >= 70 else "mixed",
        )
        building = apply_schema(building_spec)
        self.buildings.append(building)

        if fatal_flaw:
            self.monsters.append({
                "id": f"flaw_{name.lower().replace(' ', '_')}",
                "type": "fatal_flaw",
                "building_id": building["id"],
                "file_path": f"track:{name}",
                "file_name": name,
                "position": {
                    "x": building["position"]["x"] - 3,
                    "y": 2,
                    "z": building["position"]["z"] - 3,
                },
                "severity": 8,
                "message": fatal_flaw,
                "line": 1,
                "health": 20,
                "color": "#aa00ff",
            })
        return building

    def add_market_event(self, event: MarketEvent) -> dict:
        district = DISTRICTS.get(event.segment)
        if district is None:
            logger.warning("Unknown segment for market event: %s", event.segment)
            return {}

        cx = (district.x_range[0] + district.x_range[1]) // 2
        cz = (district.z_range[0] + district.z_range[1]) // 2
        disaster_type = event.event_type.lower()
        if disaster_type not in {"fire", "air_raid", "earthquake", "lightning"}:
            disaster_type = "earthquake"

        disaster = {
            "type": disaster_type,
            "building_id": f"district_{event.segment}",
            "epicenter": {"x": cx, "z": cz},
            "magnitude": min(10.0, max(1.0, event.severity / 2)),
            "duration": max(1, min(10, event.severity)),
            "description": event.description,
        }
        self.disasters.append(disaster)
        return disaster

    def add_scout_agent(self, target_name: str, segment: str) -> dict:
        district = DISTRICTS.get(segment)
        if district is None:
            return {}

        x = (district.x_range[0] + district.x_range[1]) // 2
        z = (district.z_range[0] + district.z_range[1]) // 2
        agent = {
            "id": f"scout_{target_name.lower().replace(' ', '_')}",
            "type": "scout",
            "target": target_name,
            "status": "patrolling",
            "position": {"x": x, "y": 5, "z": z},
            "velocity": {"x": 0.3, "y": 0, "z": 0.2},
        }
        self.agents.append(agent)
        return agent

    def add_axe_scout_finding(self, finding: Dict) -> Dict:
        """Translate an axe-scout finding into market-twin entities.

        Expected shape:
        {
            "ticker": "TSLA",
            "scout_type": "distress|competitive|opportunity|regulatory",
            "severity": "CRITICAL|WARNING|INFO",
            "signals": ["..."],
            "confidence": 0.0-1.0
        }
        """
        ticker = finding.get("ticker", "UNKNOWN")
        scout_type = finding.get("scout_type", "general")
        severity = finding.get("severity", "INFO")
        signals = finding.get("signals", [])
        confidence = float(finding.get("confidence", 0.5))

        segment_map = {
            "distress": "local_smb",
            "competitive": "competitor_territory",
            "opportunity": "enterprise",
            "regulatory": "regulatory",
            "general": "vertical_specific",
        }
        segment = segment_map.get(scout_type, "vertical_specific")
        value = max(1000, int(confidence * 200000))

        building_spec = BuildingSpec(
            name=ticker,
            segment=segment,
            value=value,
            health=100,
            sentiment="negative" if severity == "CRITICAL" else "mixed" if severity == "WARNING" else "neutral",
        )
        building = apply_schema(building_spec)
        self.buildings.append(building)

        if severity in {"CRITICAL", "WARNING"}:
            self.monsters.append({
                "id": f"axe_{ticker.lower()}_{scout_type}",
                "type": scout_type,
                "building_id": building["id"],
                "file_path": f"axe_scout:{ticker}",
                "file_name": ticker,
                "position": {
                    "x": building["position"]["x"] + 4,
                    "y": 4,
                    "z": building["position"]["z"] + 4,
                },
                "severity": 8 if severity == "CRITICAL" else 5,
                "message": "; ".join(signals[:3]) if signals else scout_type,
                "line": 1,
                "health": 30 if severity == "CRITICAL" else 60,
                "color": "#ff0000" if severity == "CRITICAL" else "#ff8800",
            })

        self.agents.append({
            "id": f"axe_scout_{ticker.lower()}_{int(time.time() * 1000)}",
            "type": "axe_scout",
            "target": ticker,
            "status": "patrolling",
            "position": {
                "x": building["position"]["x"] - 2,
                "y": 6,
                "z": building["position"]["z"] - 2,
            },
            "velocity": {"x": 0.2, "y": 0, "z": 0.2},
        })
        return building

    def to_city_scene(self) -> dict:
        return {
            "metadata": {
                "twin": "market",
                "real_pipeline": _REAL_IMPORTS,
                "buildings": len(self.buildings),
                "monsters": len(self.monsters),
                "disasters": len(self.disasters),
                "agents": len(self.agents),
            },
            "city": {
                "buildings": self.buildings,
                "disasters": self.disasters,
                "monsters": self.monsters,
                "air_raids": [],
            },
            "entities": {
                "agents": self.agents,
            },
        }

    def to_ws_payload(self) -> dict:
        """Wrap the city scene in a WebSocket message ready for broadcast."""
        return {
            "type": "market_twin",
            "data": self.to_city_scene(),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# Real pipeline
# ---------------------------------------------------------------------------
def run_market_pipeline(text: str, rounds: int = 1, tracks: int = 2,
                        iterations: int = 2, generations: int = 1) -> dict:
    """Run the real Vertical AI pipeline and return a Code City city scene."""
    if not _REAL_IMPORTS:
        raise RuntimeError(
            "Cannot run real market pipeline: canonical Vertical AI imports failed. "
            f"Fix {VERTICAL_AI_ROOT}/core/capability_slots.py or rerun after patching. "
            f"Original error: {_IMPORT_ERROR}"
        )

    context = {
        "raw": text,
        "type": "text",
        "label": text[:80],
        "data": {"content": text},
        "session_id": f"vai_{hash(text) % 10**12}",
    }

    boardroom_result = run_boardroom(context, rounds=rounds)
    synthesis = boardroom_result.get("synthesis") or {}
    if not isinstance(synthesis, dict):
        synthesis = {}

    simulated = run_fractal_simulation(
        synthesis=synthesis,
        input_context=context,
        tracks=tracks,
        iterations=iterations,
    )
    if not simulated:
        simulated = []

    arena_result = run_arena(simulated, context, generations=generations)
    champion = arena_result.get("champion") or {}

    translator = MarketTwinTranslator()
    if champion:
        translator.add_track_verdict(champion)

    for item in simulated:
        meta = item.get("track_meta") or {}
        if isinstance(meta, dict) and meta.get("name"):
            class Verdict:
                pass
            v = Verdict()
            v.name = meta.get("name", "")
            v.overall_fitness = float(meta.get("fitness", 0.0))
            v.fatal_flaw = meta.get("fatal_flaw")
            translator.add_track_verdict(v)

    return translator.to_city_scene()
