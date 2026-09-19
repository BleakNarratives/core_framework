"""Runs the herald project's own suite from inside the repository suite.

herald keeps its tests in `projects/herald/tests` and needs its own top-level
directory (`-t projects/herald`), so `python -m unittest discover -s tests` never
reaches them. Before this module that was ~130 passing tests which the documented
command could not see, and the only record of how to run them was a comment in
`test_herald.py`'s header.

Running the suite as a subprocess keeps one source of truth: if herald's tests
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
HERALD = ROOT / "projects" / "herald"
HERALD_TESTS = HERALD / "tests"
SUMMARY_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)


class HeraldSuiteWiringTest(unittest.TestCase):
    def test_herald_test_tree_is_where_this_wrapper_expects_it(self):
        self.assertTrue(
            HERALD_TESTS.is_dir(),
            f"herald tests moved; expected {HERALD_TESTS}",
        )
        self.assertTrue(
            (HERALD_TESTS / "test_herald.py").is_file(),
            "herald's main test module is missing",
        )

    def test_herald_suite_passes_under_the_documented_invocation(self):
        result = subprocess.run(
            [
                sys.executable, "-m", "unittest", "discover",
                "-s", str(HERALD_TESTS),
                "-t", str(HERALD),
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
            f"no unittest summary in herald output:\n{output[-1500:]}",
        )
        count = int(match.group(1))
        # A moved top-level directory can make discovery succeed with zero tests,
        # which would make this wrapper a no-op rather than a check.
        self.assertGreater(count, 0, "herald suite reported zero tests")


if __name__ == "__main__":
    unittest.main()
