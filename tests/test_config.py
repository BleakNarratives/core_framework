#!/usr/bin/env python3
"""
core_framework/tests/test_config.py

Verify shared config resolves paths correctly.
"""

from pathlib import Path

from core_framework.shared.config import (
    CODE_CITY_ENTRY,
    CODE_CITY_ROOT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    MODMIND_ENTRY,
    MODMIND_ROOT,
    REPO_ROOT,
    VERTICAL_AI_ENTRY,
    VERTICAL_AI_ROOT,
    validate_paths,
)


def test_repo_root_is_parent_of_framework():
    assert REPO_ROOT.parent.name != ""


def test_code_city_root_exists():
    assert CODE_CITY_ROOT.exists(), f"{CODE_CITY_ROOT} missing"


def test_modmind_root_exists():
    assert MODMIND_ROOT.exists(), f"{MODMIND_ROOT} missing"


def test_vertical_ai_root_exists():
    assert VERTICAL_AI_ROOT.exists(), f"{VERTICAL_AI_ROOT} missing"


def test_validate_paths_returns_bools():
    result = validate_paths()
    assert isinstance(result, dict)
    for key, value in result.items():
        assert isinstance(value, bool)


def test_defaults():
    assert DEFAULT_HOST == "0.0.0.0"
    assert DEFAULT_PORT == 8765
