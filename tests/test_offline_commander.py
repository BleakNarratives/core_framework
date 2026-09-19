"""Regression tests for the #tts / #scan handlers in offline_commander.

The defect these cover: `from termux_voice import tts` used to sit *inside*
`OfflineCommander.__init__`. An import inside a function binds a local, so
`handle_tts` and `handle_scan` -- which reference the bare name `tts` -- had no
binding in their own scope and raised NameError the first time either ran.
The module compiled cleanly, which is why it went unnoticed.

Constraints (per AGENTS.md section 6):
  - No network access, no provider calls, no credentials.
  - The stub-based loader still stubs smart_coder / project_memory so handler
    behaviour can be tested in isolation. The module-level import problem that
    used to make the file unrunnable is now FIXED -- offline_commander resolves
    tools/coding from __file__, and project_memory (absent from the first-party
    tree) is optional, mirroring what smart_coder.py already did. TestImportability
    exercises the real import path rather than the stubbed one.

Run: python -m unittest tests.test_offline_commander -v
"""

import importlib.util
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "scraping" / "offline_commander.py"


class _FakeCoder:
    """Stand-in for smart_coder.SmartCoder (constructor takes no args)."""

    def generate_from_description(self, description, language):
        return {"files": {}}


class _FakeMemory:
    def learn_pattern(self, *args, **kwargs):
        return None


def _load_commander(install_tts):
    """Import offline_commander.py by path with its sibling deps stubbed.

    Args:
        install_tts: when True a fake `termux_voice` module is placed on
            sys.modules so the real-import branch runs; when False the import
            is left to fail, exercising the _SilentTTS fallback.

    Returns:
        (module, fake_termux_voice_or_None)
    """
    smart_coder = types.ModuleType("smart_coder")
    smart_coder.SmartCoder = _FakeCoder
    project_memory = types.ModuleType("project_memory")
    project_memory.memory = _FakeMemory()

    stubs = {"smart_coder": smart_coder, "project_memory": project_memory}
    fake_tts_module = None
    if install_tts:
        fake_tts_module = types.ModuleType("termux_voice")
        fake_tts_module.tts = mock.Mock()
        stubs["termux_voice"] = fake_tts_module

    # Unique name per load so two loads never share a cached module object.
    name = f"_offline_commander_under_test_{int(install_tts)}"
    with mock.patch.dict(sys.modules, stubs):
        sys.modules.pop(name, None)
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
    return module, fake_tts_module


class TestOfflineCommanderTTS(unittest.TestCase):
    def test_tts_handler_reaches_speak(self):
        module, fake_tts = _load_commander(install_tts=True)
        commander = module.OfflineCommander()

        result = commander.process_command("#tts hello there")

        self.assertEqual(result["status"], "tts_spoken")
        self.assertEqual(result["text"], "hello there")
        fake_tts.tts.speak.assert_called_once_with("hello there")

    def test_scan_handler_reaches_speak(self):
        module, fake_tts = _load_commander(install_tts=True)
        commander = module.OfflineCommander()

        result = commander.process_command("#scan /tmp/somewhere")

        self.assertEqual(result["status"], "scanning")
        self.assertEqual(result["path"], "/tmp/somewhere")
        fake_tts.tts.speak.assert_called_once_with(
            "Scanning directory /tmp/somewhere"
        )

    def test_scan_without_argument_defaults_to_cwd(self):
        module, fake_tts = _load_commander(install_tts=True)
        commander = module.OfflineCommander()

        result = commander.process_command("#scan")

        self.assertEqual(result["path"], ".")

    def test_missing_backend_degrades_instead_of_raising(self):
        """No termux_voice installed: handlers must still return normally.

        Before the fix this raised NameError; a host without a speech backend
        must not lose the whole commander.
        """
        module, _ = _load_commander(install_tts=False)
        commander = module.OfflineCommander()

        self.assertEqual(
            commander.process_command("#tts offline")["status"], "tts_spoken"
        )
        self.assertEqual(
            commander.process_command("#scan /tmp")["status"], "scanning"
        )

    def test_memory_guard_survives_project_memory_being_absent(self):
        """handle_python must not break when project_memory is not installed.

        project_memory has no first-party copy, so `memory` is legitimately
        None here. Before the guard this raised AttributeError: 'NoneType'
        object has no attribute 'learn_pattern'.
        """
        module, _ = _load_commander(install_tts=True)
        module.memory = None
        commander = module.OfflineCommander()

        result = commander.process_command("#python anything at all")

        self.assertEqual(result["status"], "python_generated")


class TestImportability(unittest.TestCase):
    """The module must be runnable from its own directory and from anywhere.

    It used to fail at import: `from smart_coder import SmartCoder` sits at module
    level, but smart_coder.py lives in tools/coding/, not beside this file. These
    tests use the REAL modules -- no stubs -- so a regression in the path shim or
    in the optional project_memory import fails here.
    """

    def test_real_import_resolves_smart_coder(self):
        name = "_offline_commander_real_import"
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)

        self.assertIsNotNone(module.SmartCoder)
        self.assertEqual(module.SmartCoder.__module__, "smart_coder")
        self.assertIn(str(module._CODING_DIR), sys.path)
        # project_memory is absent first-party; the contract is "optional", not
        # "present", so accept either rather than pinning the environment.
        self.assertTrue(
            module.memory is None or hasattr(module.memory, "learn_pattern")
        )
        # Re-running the shim must not keep prepending duplicates.
        spec.loader.exec_module(module)
        self.assertEqual(sys.path.count(str(module._CODING_DIR)), 1)

    def test_runs_as_a_script_from_a_foreign_cwd(self):
        """__file__-relative resolution, not cwd-relative."""
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "#tts path check"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RESULT: tts_spoken", proc.stdout)

    def test_runs_as_a_script_from_its_own_directory(self):
        """The original failure mode: cwd == the module's own folder."""
        proc = subprocess.run(
            [sys.executable, MODULE_PATH.name, "#tts local check"],
            cwd=str(MODULE_PATH.parent), capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("ModuleNotFoundError", proc.stderr)
        self.assertIn("RESULT: tts_spoken", proc.stdout)


if __name__ == "__main__":
    unittest.main()
