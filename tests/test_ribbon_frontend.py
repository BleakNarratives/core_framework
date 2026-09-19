"""Front-end contract tests for the ribbon draw animation.

`MRD.md` lists five sign-off boxes and all five are still unticked, because how
a ribbon *looks* is a human judgement. This module covers what a machine can
actually check, so the unticked boxes are only about pixels:

1. `ribbon.js` behavior, executed for real against a stub DOM in Node
   (`tests/fixtures/ribbon_dom_harness.js`). Node is optional: if it is absent
   the behavioral cases skip with a visible reason instead of silently passing.
2. The static wiring in `ribbon.css` and `demo.html` — the fallback keyframes,
   the reduced-motion override, and the vars the CSS consumes.
3. The inline bundle embedded in `demo.html`, run through the real validator,
   so the demo cannot drift away from `ribbon.v1`.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RIBBON_DIR = ROOT / "src" / "ui" / "ribbon"
RIBBON_JS = RIBBON_DIR / "ribbon.js"
RIBBON_CSS = RIBBON_DIR / "ribbon.css"
DEMO_HTML = RIBBON_DIR / "demo.html"
HARNESS = ROOT / "tests" / "fixtures" / "ribbon_dom_harness.js"
NODE = shutil.which("node")

# Case names the harness must report. Asserting on these means a harness that
# stops running cases fails the test instead of passing vacuously.
EXPECTED_HARNESS_CASES = (
    "defers_init_until_dom_ready",
    "easing_math_matches_css_keywords",
    "creates_svg_in_the_svg_namespace",
    "path_geometry_builds_move_and_line_commands",
    "closed_path_appends_z",
    "stroke_attributes_are_copied_from_the_spec",
    "opacity_is_omitted_when_absent",
    "css_variables_come_from_the_measured_length_and_spec",
    "animation_defaults_are_applied_when_the_block_is_missing",
    "malformed_json_is_skipped_without_throwing",
    "empty_ribbon_list_is_skipped",
    "missing_get_total_length_degrades_without_animate",
    "existing_svg_is_reused_not_duplicated",
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("ribbon_validate_fe", RIBBON_DIR / "validate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


class TestRibbonCssContract(unittest.TestCase):
    """The CSS fallback must work with JavaScript disabled."""

    def setUp(self):
        self.css = RIBBON_CSS.read_text(encoding="utf-8")

    def test_keyframes_drive_dash_offset_from_len(self):
        self.assertIn("@keyframes ribbon-draw", self.css)
        self.assertRegex(self.css, r"stroke-dashoffset:\s*var\(--len")

    def test_animation_uses_dur_and_easing_vars_with_defaults(self):
        # Defaults matter: with JS disabled the vars are never set by script.
        self.assertRegex(self.css, r"animation:\s*ribbon-draw\s+var\(--dur,\s*1800ms\)")
        self.assertRegex(self.css, r"var\(--easing,\s*ease-in-out\)")

    def test_reduced_motion_disables_the_animation(self):
        block = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(?P<body>[^}]*\{[^}]*\}[^}]*)\}",
            self.css,
        )
        self.assertIsNotNone(block, "ribbon.css must honour prefers-reduced-motion")
        body = block.group("body")
        self.assertIn("animation: none", body)
        self.assertIn("stroke-dashoffset: 0", body)

    def test_dash_array_is_bound_to_the_measured_length(self):
        self.assertRegex(self.css, r"stroke-dasharray:\s*var\(--len")


class TestRibbonDemoContract(unittest.TestCase):
    """demo.html is the file the MRD asks a human to open."""

    def setUp(self):
        self.html = DEMO_HTML.read_text(encoding="utf-8")

    def test_demo_loads_both_the_css_and_the_js(self):
        self.assertRegex(self.html, r'<link[^>]+href="ribbon\.css"')
        self.assertRegex(self.html, r'<script[^>]+src="ribbon\.js"')

    def test_demo_uses_the_documented_wrap_markup(self):
        self.assertIn('class="ribbon-wrap"', self.html)
        self.assertIn("data-ribbon=", self.html)

    def test_inline_bundle_validates_against_ribbon_v1(self):
        """The hand-copied demo bundle must not drift from the contract."""
        match = re.search(r"data-ribbon='(?P<spec>[^']+)'", self.html)
        self.assertIsNotNone(match, "demo.html must carry an inline data-ribbon bundle")
        bundle = json.loads(match.group("spec"))
        self.assertEqual(validator.validate_bundle(bundle, {}), [])

    def test_guard_commands_advertised_by_the_demo_actually_exist(self):
        """The demo points a reader at snapshot/rollback, so the tool must have them."""
        self.assertIn("guard.sh", self.html)
        guard = ROOT / "tools" / "guard" / "guard.sh"
        self.assertTrue(guard.is_file(), "demo.html advertises tools/guard/guard.sh")
        source = guard.read_text(encoding="utf-8")
        for subcommand in ("snap", "rollback"):
            with self.subTest(subcommand=subcommand):
                self.assertRegex(
                    source,
                    rf"(?m)^\s*{subcommand}\)",
                    f"guard.sh must dispatch the '{subcommand}' subcommand",
                )


class TestRibbonJsBehavior(unittest.TestCase):
    """Real execution of ribbon.js in Node against a stub DOM."""

    def _run_harness(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [NODE, str(HARNESS)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    @unittest.skipUnless(NODE, "node not installed; ribbon.js behavior cannot be executed")
    def test_all_harness_cases_pass(self):
        result = self._run_harness()
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("FAIL ", output)

    @unittest.skipUnless(NODE, "node not installed; ribbon.js behavior cannot be executed")
    def test_harness_reports_every_expected_case(self):
        """Guards against the harness silently skipping its own cases."""
        result = self._run_harness()
        passed = {line.split(" ", 1)[1] for line in result.stdout.splitlines() if line.startswith("OK ")}
        missing = [case for case in EXPECTED_HARNESS_CASES if case not in passed]
        self.assertEqual(missing, [], f"harness did not report: {missing}")

    def test_js_asset_exists_and_is_dependency_free(self):
        source = RIBBON_JS.read_text(encoding="utf-8")
        self.assertTrue(source.strip(), "ribbon.js must not be empty")
        # Zero-dep is a stated property of this asset.
        self.assertNotIn("require(", source.replace("module.exports", ""))
        self.assertNotIn("import ", source)


if __name__ == "__main__":
    unittest.main()
