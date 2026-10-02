#!/usr/bin/env python3
"""
core_framework/shared/config.py

Central configuration and path resolution for the unified framework.
All paths point to existing source trees; nothing is copied here.
"""

import os
import socket
import sys
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

# ---------------------------------------------------------------------------
# Framework-owned writable paths (never canonical source trees)
# ---------------------------------------------------------------------------
OUTPUT_DIR = FRAMEWORK_ROOT / "output"
LOG_DIR = FRAMEWORK_ROOT / "logs"
LEADERBOARD_PATH = FRAMEWORK_ROOT / "scout_leaderboard.json"

# ---------------------------------------------------------------------------
# Virtual environment dependency resolution
#
# Agents run inside sandboxed subshells that may not have the same interpreter
# as the interactive shell. Rather than hard-coding a single venv, resolve the
# first site-packages directory that actually contains the package we need.
# This mirrors the fallback list already used by
# Code-City-Apocalypse/backend/server.py.
# ---------------------------------------------------------------------------
VENV_CANDIDATES = [
    REPO_ROOT / "passive_income_swarm-env",
    REPO_ROOT / "Skin-Deep" / ".venv",
    REPO_ROOT / "The-Werkz" / "EquiNex-Universal-Dashboard" / ".venv",
]


def _site_packages(venv_root: Path) -> Path:
    py = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return venv_root / "lib" / py / "site-packages"


def resolve_venv_site_packages(module_name: str | None = None) -> Path | None:
    """Return the first candidate site-packages containing ``module_name``.

    When ``module_name`` is None, return the first existing candidate. Returns
    None when no candidate exists so callers can degrade gracefully instead of
    crashing on a missing virtual environment.
    """
    for venv_root in VENV_CANDIDATES:
        site = _site_packages(venv_root)
        if not site.exists():
            continue
        if module_name is None or (site / module_name).exists() or (site / f"{module_name}.py").exists():
            return site
    return None


def inject_venv_paths(module_name: str | None = None) -> list[str]:
    """Prepend resolvable venv site-packages to ``sys.path``.

    Idempotent: existing entries are not duplicated. Returns the list of paths
    actually added, which makes the side effect auditable in tests.
    """
    added: list[str] = []
    for venv_root in VENV_CANDIDATES:
        site = _site_packages(venv_root)
        if not site.exists():
            continue
        if module_name is not None and not (
            (site / module_name).exists() or (site / f"{module_name}.py").exists()
        ):
            continue
        path_str = str(site)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
            added.append(path_str)
        if module_name is not None:
            break
    return added


def ensure_output_dirs() -> dict:
    """Create framework-owned writable directories and return their paths."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return {"output": OUTPUT_DIR, "logs": LOG_DIR}


def validate_paths() -> dict:
    """Return health of each canonical path."""
    return {
        "code_city": CODE_CITY_ENTRY.exists(),
        "modmind": MODMIND_ENTRY.exists(),
        "vertical_ai": VERTICAL_AI_ENTRY.exists(),
    }
