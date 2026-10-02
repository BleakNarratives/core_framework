"""
AxeScout Specification for Market Twin Adapter.

Translates raw AxeScout findings into standardized ScoutIntel entities.
"""

from typing import Any, Dict

SCOUT_SEGMENT_MAP = {
    "distress": "enterprise",
    "competitive": "enterprise",
    "regulatory": "regulatory",
    "sentiment": "enterprise"
}

def format_axe_finding_to_scout_intel(raw_axe_finding: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a raw scan output from AxeScout into a standardized format
    compatible with MarketTwinTranslator entity ingestion.
    """
    return {
        "target_name": raw_axe_finding.get("ticker", "Unknown Target"),
        "segment": SCOUT_SEGMENT_MAP.get(raw_axe_finding.get("scout_type"), "enterprise"),
        "risk_score": 85 if raw_axe_finding.get("severity") == "CRITICAL" else 50 if raw_axe_finding.get("severity") == "WARNING" else 20,
        "opportunity_score": int(raw_axe_finding.get("confidence", 0.5) * 100),
        "value": 100000.0,
        "sentiment": "negative" if raw_axe_finding.get("severity") in ["CRITICAL", "WARNING"] else "positive",
    }
