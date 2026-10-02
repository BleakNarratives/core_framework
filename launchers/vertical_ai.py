#!/usr/bin/env python3
"""
core_framework/launchers/vertical_ai.py

Thin pointer into the canonical Vertical AI conductor.
Launches: ~/The-Werkz/Official-Vertical-AI-Boardroom/vertical_ai.py

Sidecars preserved in place:
- core/boardroom.py, core/simulator.py, core/genetics.py, core/mutation_engine.py
- scouts/, verticals/, data/, tools/, bridges/, legacy/

Architecture note:
The original intent was: idea → boardroom → simulator → genetic arena → champion → Code City Arena.
Current state: boardroom/simulator/genetics exist; Code City Arena integration is missing.
See design/VERTICAL_AI_ORIGINAL_VISION.md for the restoration plan.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve canonical source root without copying anything
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERTICAL_AI_ROOT = REPO_ROOT / "The-Werkz" / "Official-Vertical-AI-Boardroom"
CANONICAL_ENTRY = VERTICAL_AI_ROOT / "vertical_ai.py"

# Inject root so sibling imports like `boardroom`, `router`, `genetics` resolve
sys.path.insert(0, str(VERTICAL_AI_ROOT))

if not CANONICAL_ENTRY.exists():
    raise SystemExit(
        f"[core_framework] Canonical Vertical AI entry not found: {CANONICAL_ENTRY}"
    )


def launch():
    import runpy
    sys.argv = [str(CANONICAL_ENTRY), *sys.argv[1:]]
    runpy.run_path(str(CANONICAL_ENTRY), run_name="__main__")


if __name__ == "__main__":
    launch()
