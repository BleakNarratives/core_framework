#!/usr/bin/env python3
"""
core_framework/launchers/modmind.py

Thin pointer into the canonical ModMind source tree.
Launches: ~/Code-City-Apocalypse/Code_City_Unified/modmind_unified/src/modmind_architect.py

Sidecars preserved in place:
- agents/, automation/, swarm/, docs/, ui_forge/, tests/, utils/
- output/, logs/

Note: modmind_architect.py is the Level 1 defense / Level 2 offense agent pipeline.
The unified ModMind system includes much more than this single entry point.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve canonical source root without copying anything
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODMIND_SRC = REPO_ROOT / "Code-City-Apocalypse" / "Code_City_Unified" / "modmind_unified" / "src"
MODMIND_ROOT = REPO_ROOT / "Code-City-Apocalypse" / "Code_City_Unified" / "modmind_unified"

# Inject src so `modmind_architect` and sibling modules resolve
sys.path.insert(0, str(MODMIND_SRC))

# Also inject root so automation/, agents/, swarm/ imports work
sys.path.insert(0, str(MODMIND_ROOT))

CANONICAL_ENTRY = MODMIND_SRC / "modmind_architect.py"

if not CANONICAL_ENTRY.exists():
    raise SystemExit(
        f"[core_framework] Canonical ModMind entry not found: {CANONICAL_ENTRY}"
    )


def launch():
    import runpy
    sys.argv = [str(CANONICAL_ENTRY), *sys.argv[1:]]
    runpy.run_path(str(CANONICAL_ENTRY), run_name="__main__")


if __name__ == "__main__":
    launch()
