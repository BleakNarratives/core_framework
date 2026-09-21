"""Runs the Cutting Room project's own suite from inside the repository suite.

Cutting Room keeps its tests in `projects/cuttingroom/tests` and needs its own
top-level directory (`-t projects/cuttingroom`), so `python -m unittest discover -s
tests` never reaches them. That is the same gap the herald wrapper was written to
close: a project whose suite the documented command cannot see is a project whose
breakage is discovered by whoever runs it next, or not at all.

Running the suite as a subprocess keeps one source of truth: if the language's tests
move, break, or stop being discovered, this fails instead of quietly covering
nothing.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUTTINGROOM = ROOT / "projects" / "cuttingroom"
CUTTINGROOM_TESTS = CUTTINGROOM / "tests"
SUMMARY_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


class CuttingRoomSuiteWiringTest(unittest.TestCase):
    def test_cuttingroom_test_tree_is_where_this_wrapper_expects_it(self):
        self.assertTrue(
            CUTTINGROOM_TESTS.is_dir(),
            f"cuttingroom tests moved; expected {CUTTINGROOM_TESTS}",
        )
        self.assertTrue(
            (CUTTINGROOM_TESTS / "test_cuttingroom.py").is_file(),
            "cuttingroom's test module is missing",
        )

    def test_cuttingroom_suite_passes_under_the_documented_invocation(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", str(CUTTINGROOM_TESTS),
                "-t", str(CUTTINGROOM),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output[-3000:])

        match = SUMMARY_RE.search(output)
        self.assertIsNotNone(
            match,
            f"no unittest summary in cuttingroom output:\n{output[-1500:]}",
        )
        count = int(match.group(1))
        # A moved top-level directory can make discovery succeed with zero tests,
        # which would make this wrapper a no-op rather than a check.
        self.assertGreater(count, 0, "cuttingroom suite reported zero tests")


if __name__ == "__main__":
    unittest.main()
