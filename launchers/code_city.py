#!/usr/bin/env python3
"""
core_framework/launchers/code_city.py

Thin pointer into the canonical Code City source tree.
Launches: ~/Code-City-Apocalypse/code_city_apocalypse.py

Sidecars preserved in place:
- crash_feeder.py, crash_monster.py
- red_team_attacks.py, defensive_fortifications.py, security_audit.py
- Code_City/, Code_City_Unified/, backend/, frontend/
- src/buildings/arena.py (the actual Code City Arena PvP system)
- rampage-refactor/, obelisk/, plugins/

Architecture note:
Code City is both a visualization (files→buildings, bugs→monsters) AND an arena
system (src/buildings/arena.py). The arena exists but is not yet wired to the
Vertical AI genetic arena champion track. See design/ for restoration plan.
"""

import sys
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve canonical source root without copying anything
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODE_CITY_ROOT = REPO_ROOT / "Code-City-Apocalypse"
CANONICAL_ENTRY = CODE_CITY_ROOT / "code_city_apocalypse.py"

# Inject canonical root so relative imports inside Code City keep working
sys.path.insert(0, str(CODE_CITY_ROOT))

if not CANONICAL_ENTRY.exists():
    raise SystemExit(
        f"[core_framework] Canonical Code City entry not found: {CANONICAL_ENTRY}"
    )


def launch():
    import runpy
    sys.argv = [str(CANONICAL_ENTRY), *sys.argv[1:]]
    runpy.run_path(str(CANONICAL_ENTRY), run_name="__main__")


if __name__ == "__main__":
    launch()
