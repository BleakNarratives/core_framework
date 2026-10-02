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
    OUTPUT_DIR,
    REPO_ROOT,
    VERTICAL_AI_ENTRY,
    VERTICAL_AI_ROOT,
    ensure_output_dirs,
    inject_venv_paths,
    resolve_venv_site_packages,
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


def test_missing_module_resolves_to_none():
    assert resolve_venv_site_packages("definitely_missing_module_xyz") is None


def test_inject_venv_paths_returns_list_and_is_safe():
    import sys

    before = list(sys.path)
    added = inject_venv_paths("definitely_missing_module_xyz")
    assert isinstance(added, list)
    assert added == []
    assert sys.path == before


def test_ensure_output_dirs_creates_paths():
    paths = ensure_output_dirs()
    assert paths["output"].exists()
    assert paths["logs"].exists()
    assert paths["output"] == OUTPUT_DIR
