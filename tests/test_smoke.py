#!/usr/bin/env python3
"""
core_framework/tests/test_smoke.py

Smoke tests for the core_framework launchers.
Verifies that canonical entry points exist and are importable.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRAMEWORK_ROOT = REPO_ROOT / "core_framework"


def test_code_city_entry_exists():
    entry = REPO_ROOT / "Code-City-Apocalypse" / "code_city_apocalypse.py"
    assert entry.exists(), f"Code City entry missing: {entry}"


def test_modmind_entry_exists():
    entry = (
        REPO_ROOT
        / "Code-City-Apocalypse"
        / "Code_City_Unified"
        / "modmind_unified"
        / "src"
        / "modmind_architect.py"
    )
    assert entry.exists(), f"ModMind entry missing: {entry}"


def test_vertical_ai_entry_exists():
    entry = (
        REPO_ROOT
        / "The-Werkz"
        / "Official-Vertical-AI-Boardroom"
        / "vertical_ai.py"
    )
    assert entry.exists(), f"Vertical AI entry missing: {entry}"


def test_launchers_importable():
    sys.path.insert(0, str(FRAMEWORK_ROOT))
    try:
        import core_framework.launchers.code_city  # noqa: F401
        import core_framework.launchers.modmind  # noqa: F401
        import core_framework.launchers.vertical_ai  # noqa: F401
        import core_framework.launchers.unified  # noqa: F401
    finally:
        sys.path.remove(str(FRAMEWORK_ROOT))
