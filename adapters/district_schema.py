#!/usr/bin/env python3
"""
core_framework/adapters/district_schema.py

Mapping rules: Vertical AI market concepts → Code City district/building schema.

Districts are spatial indices for market segments.
Buildings are accounts / prospects / competitors within those segments.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Canonical segment definitions
# ---------------------------------------------------------------------------
SEGMENTS: List[str] = [
    "local_smb",
    "enterprise",
    "competitor_territory",
    "regulatory",
    "vertical_specific",
]


@dataclass
class DistrictSchema:
    """Maps a market segment to a Code City district."""

    segment: str
    color: str
    x_range: tuple[int, int]
    z_range: tuple[int, int]
    building_min_height: int = 10
    building_max_height: int = 120


DISTRICTS: Dict[str, DistrictSchema] = {
    "local_smb": DistrictSchema(
        segment="local_smb",
        color="#4CAF50",
        x_range=(-80, -20),
        z_range=(-80, -20),
    ),
    "enterprise": DistrictSchema(
        segment="enterprise",
        color="#3776ab",
        x_range=(20, 80),
        z_range=(-80, -20),
        building_min_height=40,
        building_max_height=150,
    ),
    "competitor_territory": DistrictSchema(
        segment="competitor_territory",
        color="#ce422b",
        x_range=(-80, -20),
        z_range=(20, 80),
    ),
    "regulatory": DistrictSchema(
        segment="regulatory",
        color="#ff8800",
        x_range=(20, 80),
        z_range=(20, 80),
    ),
    "vertical_specific": DistrictSchema(
        segment="vertical_specific",
        color="#61dafb",
        x_range=(-20, 20),
        z_range=(-20, 20),
    ),
}


@dataclass
class BuildingSpec:
    """Single account / prospect / competitor as a Code City building."""

    name: str
    segment: str
    value: float = 0.0
    health: int = 100
    sentiment: str = "neutral"
    district_x: Optional[int] = None
    district_z: Optional[int] = None


def _stable_position(name: str, x_range: tuple[int, int], z_range: tuple[int, int]) -> tuple[int, int]:
    """Deterministic position so the same account always appears in the same spot."""
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    seed = int(h, 16)
    x = (seed % (x_range[1] - x_range[0])) + x_range[0]
    z = ((seed >> 4) % (z_range[1] - z_range[0])) + z_range[0]
    return x, z


_SEGMENT_ALIASES = {
    "competitor": "competitor_territory",
    "prospect": "local_smb",
    "account": "enterprise",
    "lead": "local_smb",
    "regulator": "regulatory",
    "vertical": "vertical_specific",
}


def apply_schema(building: BuildingSpec) -> Dict:
    """Convert a BuildingSpec into a Code City building dict."""
    segment = _SEGMENT_ALIASES.get(building.segment, building.segment)
    district = DISTRICTS.get(segment)
    if district is None:
        raise ValueError(f"Unknown segment: {building.segment}")

    x, z = _stable_position(building.name, district.x_range, district.z_range)
    height = max(
        district.building_min_height,
        min(district.building_max_height, int(building.value / 1000)),
    )
    health = max(0, min(100, building.health))

    return {
        "id": f"account_{building.name.lower().replace(' ', '_')}",
        "name": building.name,
        "path": f"segment:{segment}",
        "full_path": f"segment:{segment}/{building.name}",
        "type": "market_building",
        "size": int(building.value),
        "lines": int(building.value / 100),
        "complexity": 1,
        "health": health,
        "position": {"x": x, "y": 0, "z": z},
        "dimensions": {
            "width": max(8, min(30, int(building.value / 5000))),
            "height": height,
            "depth": max(8, min(30, int(building.value / 5000))),
        },
        "color": district.color,
    }
