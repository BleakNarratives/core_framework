"""Offline smoke test for Boardroom path resolution.

The test copies only _paths.py into a temporary directory. Importing that copy
creates canonical directories inside the temporary directory, never in the live
Boardroom workspace.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


BOARDROOM = Path(__file__).resolve().parents[1] / "The-Werkz" / "Official-Vertical-AI-Boardroom"


class BoardroomPathsOfflineTest(unittest.TestCase):
    def test_paths_create_isolated_canonical_tree(self) -> None:
        source = BOARDROOM / "_paths.py"
        self.assertTrue(source.is_file())
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory)
            copied = sandbox / "_paths.py"
            text = source.read_text(encoding="utf-8")
            # The module derives ROOT from its own file location, so this copy
            # makes every generated directory land inside the temp directory.
            copied.write_text(text, encoding="utf-8")
            spec = importlib.util.spec_from_file_location("offline_boardroom_paths", copied)
            self.assertIsNotNone(spec)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            self.assertEqual(module.ROOT, sandbox)
            self.assertEqual(module.SESSION_DIRS["vai"], sandbox / "outputs" / "sessions" / "vai")
            self.assertEqual(module.PROJECTS, sandbox / "data" / "projects")
            for path in module.SESSION_DIRS.values():
                self.assertTrue(path.is_dir())
            self.assertTrue(module.PROJECTS.is_dir())
            self.assertFalse((BOARDROOM / "outputs" / "sessions" / "offline_boardroom_paths").exists())


if __name__ == "__main__":
    unittest.main()
