#!/usr/bin/env python3
"""
core_framework/shared/config.py

Central configuration and path resolution for the unified framework.
All paths point to existing source trees; nothing is copied here.
"""

import os
import socket
from pathlib import Path

socket.setdefaulttimeout(5.0)

# ---------------------------------------------------------------------------
# Root discovery
# ---------------------------------------------------------------------------
FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Canonical source roots (read-only pointers)
# ---------------------------------------------------------------------------
CODE_CITY_ROOT = REPO_ROOT / "Code-City-Apocalypse"
MODMIND_ROOT = CODE_CITY_ROOT / "Code_City_Unified" / "modmind_unified"
VERTICAL_AI_ROOT = REPO_ROOT / "The-Werkz" / "Official-Vertical-AI-Boardroom"
VERTICAL_ENGINE_ROOT = REPO_ROOT / "vertical_ai_engine"

# ---------------------------------------------------------------------------
# Canonical entry points
# ---------------------------------------------------------------------------
CODE_CITY_ENTRY = CODE_CITY_ROOT / "code_city_apocalypse.py"
MODMIND_ENTRY = MODMIND_ROOT / "src" / "modmind_architect.py"
VERTICAL_AI_ENTRY = VERTICAL_AI_ROOT / "vertical_ai.py"

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
DEFAULT_HOST = os.getenv("CORE_FRAMEWORK_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("CORE_FRAMEWORK_PORT", "8765"))


def validate_paths() -> dict:
    """Return health of each canonical path."""
    return {
        "code_city": CODE_CITY_ENTRY.exists(),
        "modmind": MODMIND_ENTRY.exists(),
        "vertical_ai": VERTICAL_AI_ENTRY.exists(),
    }
