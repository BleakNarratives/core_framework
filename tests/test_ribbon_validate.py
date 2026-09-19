"""Offline regression tests for the ribbon bundle validator.

`src/ui/ribbon/validate.py` is normally run by hand:

    python3 src/ui/ribbon/validate.py

These tests pin the `validate_bundle` contract and prove the CLI gate actually
trips. Two properties matter and are asserted below:

1. The guard proof is real. `fixtures_invalid/empty.json` is documented in
   `QRD.md` as the file that "must FAIL (proves guard trips)", but the CLI only
   scans `fixtures/`, so nothing exercised it. The rejection is asserted here.
2. No live side effects. `validate.py` rewrites `analysis_report.json` in its
   own directory on every run, so every CLI case executes against a throwaway
   copy of the ribbon directory and the live report is checked for mutation.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RIBBON_DIR = ROOT / "src" / "ui" / "ribbon"
BUNDLE_PATH = RIBBON_DIR / "ribbon.spec.json"
SCHEMA_PATH = RIBBON_DIR / "spec.schema.json"
FIXTURES_DIR = RIBBON_DIR / "fixtures"
FIXTURES_INVALID_DIR = RIBBON_DIR / "fixtures_invalid"
LIVE_REPORT = RIBBON_DIR / "analysis_report.json"


def _load_validator():
    spec = importlib.util.spec_from_file_location("ribbon_validate", RIBBON_DIR / "validate.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Loading must not run main(); main() is guarded by __name__.
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _read_bundle(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _valid_bundle() -> dict:
    return _read_bundle(BUNDLE_PATH)


def _schema() -> dict:
    return _read_bundle(SCHEMA_PATH)


def _errors(bundle: dict) -> list:
    return validator.validate_bundle(bundle, _schema())


class TestRibbonShippedArtifacts(unittest.TestCase):
    """The bundle and every positive fixture must stay clean."""

    def test_shipped_bundle_passes(self):
        self.assertEqual(_errors(_valid_bundle()), [])

    def test_every_positive_fixture_passes(self):
        fixtures = sorted(FIXTURES_DIR.glob("*.json"))
        # Three fixtures ship today; assert the set isn't empty so a moved or
        # renamed directory fails loudly instead of passing vacuously.
        self.assertTrue(fixtures, f"no fixtures found under {FIXTURES_DIR}")
        for path in fixtures:
            with self.subTest(fixture=path.name):
                self.assertEqual(_errors(_read_bundle(path)), [])

    def test_shipped_invalid_fixture_is_rejected(self):
        """The documented guard proof, which the CLI itself never runs."""
        path = FIXTURES_INVALID_DIR / "empty.json"
        self.assertTrue(path.is_file(), f"missing guard fixture: {path}")
        errs = _errors(_read_bundle(path))
        self.assertTrue(errs, "empty ribbon array must not validate")
        self.assertIn("ribbons must be non-empty array", errs)


class TestRibbonRuleCoverage(unittest.TestCase):
    """Rule-by-rule checks against a copy of the shipped bundle."""

    def setUp(self):
        self.bundle = _valid_bundle()
        self.ribbon = self.bundle["ribbons"][0]

    def _expect_error(self, fragment: str):
        errs = _errors(self.bundle)
        self.assertTrue(
            any(fragment in e for e in errs),
            f"expected an error containing {fragment!r}, got {errs}",
        )
        return errs

    def test_version_and_kind_are_pinned(self):
        self.bundle["version"] = "ribbon.v2"
        self._expect_error("version must be 'ribbon.v1'")

        self.bundle = _valid_bundle()
        self.bundle["kind"] = "ribbons"
        self._expect_error("kind must be 'ribbon'")

    def test_ribbons_must_be_a_non_empty_array(self):
        for value in ([], {}, None, "hero"):
            with self.subTest(ribbons=value):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"] = value
                errs = _errors(self.bundle)
                # Validation stops here rather than cascading per-ribbon noise.
                self.assertEqual(errs, ["ribbons must be non-empty array"])

    def test_duplicate_ribbon_ids_are_rejected(self):
        twin = copy.deepcopy(self.ribbon)
        self.bundle["ribbons"].append(twin)
        self._expect_error(f"ribbon id duplicate: {self.ribbon['id']!r}")

    def test_ribbon_id_pattern(self):
        for bad_id in ("Hero Ribbon", "HeroRibbon", "hero.ribbon", ""):
            with self.subTest(ribbon_id=bad_id):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["id"] = bad_id
                self._expect_error("must match ^[a-z0-9_-]+$")

    def test_missing_ribbon_id_is_rejected_not_defaulted(self):
        del self.ribbon["id"]
        self._expect_error("must match ^[a-z0-9_-]+$")

    def test_path_needs_at_least_two_points(self):
        for points in ([], [[10, 10]], None, "10,10"):
            with self.subTest(points=points):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["path"]["points"] = points
                self._expect_error("path.points must have >=2 points")

    def test_points_must_be_numeric_pairs(self):
        for bad_point in ([10], [10, 20, 30], ["10", 20], [10, "20"], 10, None):
            with self.subTest(point=bad_point):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["path"]["points"] = [[0, 0], bad_point]
                self._expect_error("must be [x,y] numbers")

    def test_stroke_must_be_rrggbb(self):
        for stroke in ("7c5cff", "#7c5cf", "#7c5cfff", "#gggggg", 12438015, None):
            with self.subTest(stroke=stroke):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["stroke"] = stroke
                self._expect_error("style.stroke must be #RRGGBB")

    def test_width_range_is_inclusive_at_the_edges(self):
        for width in (0.5, 32, 3, 16.25):
            with self.subTest(width=width):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["width"] = width
                self.assertEqual(_errors(self.bundle), [])

        for width in (0.4, 32.01, 0, -3, "4", None):
            with self.subTest(width=width):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["width"] = width
                self._expect_error("style.width must be 0.5..32")

    def test_animation_easing_enum(self):
        for easing in ("linear", "ease-in", "ease-out", "ease-in-out"):
            with self.subTest(easing=easing):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["animation"]["easing"] = easing
                self.assertEqual(_errors(self.bundle), [])

        self.bundle["ribbons"][0]["animation"]["easing"] = "bounce"
        self._expect_error("animation.easing invalid")

    def test_animation_duration_floor_is_inclusive(self):
        self.bundle["ribbons"][0]["animation"]["duration_ms"] = 100
        self.assertEqual(_errors(self.bundle), [])

        for duration in (99, 0, -1, 1200.5, "1200", None):
            with self.subTest(duration_ms=duration):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["animation"]["duration_ms"] = duration
                self._expect_error("animation.duration_ms must be >=100 int")

    def test_animation_block_is_optional(self):
        del self.ribbon["animation"]
        self.assertEqual(_errors(self.bundle), [])

    def test_path_closed_must_be_boolean(self):
        self.ribbon["path"]["closed"] = True
        self.assertEqual(_errors(self.bundle), [])

        for closed in ("yes", 1, 0, None):
            with self.subTest(closed=closed):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["path"]["closed"] = closed
                self._expect_error("path.closed must be boolean")

    def test_style_opacity_range_is_inclusive_at_the_edges(self):
        for opacity in (0, 1, 0.5, 0.95):
            with self.subTest(opacity=opacity):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["opacity"] = opacity
                self.assertEqual(_errors(self.bundle), [])

        for opacity in (-0.1, 1.1, 5, "0.5", True):
            with self.subTest(opacity=opacity):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["opacity"] = opacity
                self._expect_error("style.opacity must be 0..1")

    def test_style_dash_must_be_a_numeric_array(self):
        for dash in ([4, 2], [1], [], [0.5, 1.5]):
            with self.subTest(dash=dash):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["dash"] = dash
                self.assertEqual(_errors(self.bundle), [])

        for dash in ("4", 4, [4, "2"], [True], {"a": 1}, [None]):
            with self.subTest(dash=dash):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["style"]["dash"] = dash
                self._expect_error("style.dash must be an array of numbers")

    def test_animation_direction_enum(self):
        for direction in ("forward", "reverse", "alternate"):
            with self.subTest(direction=direction):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["animation"]["direction"] = direction
                self.assertEqual(_errors(self.bundle), [])

        self.bundle["ribbons"][0]["animation"]["direction"] = "sideways"
        self._expect_error("animation.direction invalid")

    def test_animation_loop_must_be_boolean(self):
        for loop in (True, False):
            with self.subTest(loop=loop):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["animation"]["loop"] = loop
                self.assertEqual(_errors(self.bundle), [])

        for loop in (1, 0, "true", None):
            with self.subTest(loop=loop):
                self.bundle = _valid_bundle()
                self.bundle["ribbons"][0]["animation"]["loop"] = loop
                self._expect_error("animation.loop must be boolean")

    def test_booleans_are_not_accepted_as_numbers(self):
        """JSON Schema's `number` excludes booleans, but Python's bool is an int."""
        cases = (
            (lambda b: b["ribbons"][0]["style"].__setitem__("width", True), "style.width must be 0.5..32"),
            (lambda b: b["ribbons"][0]["path"].__setitem__("points", [[True, 0], [1, 1]]), "must be [x,y] numbers"),
        )
        for mutate, fragment in cases:
            with self.subTest(fragment=fragment):
                self.bundle = _valid_bundle()
                mutate(self.bundle)
                self._expect_error(fragment)

    def test_malformed_shapes_are_reported_not_raised(self):
        """A raised exception would never reach analysis_report.json.

        Each of these previously crashed the gate with TypeError/AttributeError
        instead of returning an error list.
        """
        cases = (
            ("ribbon is a string", lambda b: b["ribbons"].__setitem__(0, "nope"), "ribbon must be an object"),
            ("ribbon is a number", lambda b: b["ribbons"].__setitem__(0, 7), "ribbon must be an object"),
            ("path is a string", lambda b: b["ribbons"][0].__setitem__("path", "abc"), "path must be an object"),
            ("style is a string", lambda b: b["ribbons"][0].__setitem__("style", "red"), "style must be an object"),
            ("animation is a number", lambda b: b["ribbons"][0].__setitem__("animation", 5), "animation must be an object"),
            ("animation is a string", lambda b: b["ribbons"][0].__setitem__("animation", "ease-in"), "animation must be an object"),
        )
        for label, mutate, fragment in cases:
            with self.subTest(case=label):
                self.bundle = _valid_bundle()
                mutate(self.bundle)
                self._expect_error(fragment)


class TestRibbonCliGate(unittest.TestCase):
    """CLI exit codes and the "never pollutes the bundle" promise."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sandbox = Path(self._tmp.name) / "ribbon"
        # validate.py derives ROOT from its own location, so the copy is fully
        # self-contained: every report write lands inside the sandbox.
        shutil.copytree(
            RIBBON_DIR,
            self.sandbox,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        self.live_report_before = LIVE_REPORT.read_bytes()
        self.addCleanup(self._assert_live_report_untouched)

    def _assert_live_report_untouched(self):
        self.assertEqual(
            LIVE_REPORT.read_bytes(),
            self.live_report_before,
            "CLI test must not rewrite the live analysis_report.json",
        )

    def _run_cli(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.sandbox / "validate.py")],
            cwd=str(self.sandbox),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def _sandbox_report(self) -> dict:
        return _read_bundle(self.sandbox / "analysis_report.json")

    def _original_bundle_bytes(self) -> bytes:
        return BUNDLE_PATH.read_bytes()

    def test_cli_passes_and_writes_report_into_the_sandbox(self):
        result = self._run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("3 fixtures", result.stdout)

        report = self._sandbox_report()
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["fixture_errors"], {})
        # Paths point into the sandbox, which proves the live report was not the
        # file that got written.
        self.assertTrue(report["bundle"].startswith(str(self.sandbox)))
        self.assertEqual(
            (self.sandbox / "ribbon.spec.json").read_bytes(),
            self._original_bundle_bytes(),
        )

    def test_cli_exits_2_and_preserves_the_bundle_when_a_fixture_is_bad(self):
        fixture = self.sandbox / "fixtures" / "single.json"
        broken = _read_bundle(fixture)
        broken["ribbons"][0]["style"]["stroke"] = "not-a-hex"
        fixture.write_text(json.dumps(broken), encoding="utf-8")
        before = self._original_bundle_bytes()

        result = self._run_cli()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)

        report = self._sandbox_report()
        self.assertEqual(report["errors"], [], "bundle itself was valid")
        self.assertIn("single.json", report["fixture_errors"])
        # The bundle is never rewritten, even when a fixture fails.
        self.assertEqual((self.sandbox / "ribbon.spec.json").read_bytes(), before)

    def test_cli_exits_1_when_the_bundle_itself_is_invalid(self):
        bundle = _read_bundle(self.sandbox / "ribbon.spec.json")
        bundle["version"] = "ribbon.v2"
        (self.sandbox / "ribbon.spec.json").write_text(json.dumps(bundle), encoding="utf-8")

        result = self._run_cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)

        report = self._sandbox_report()
        self.assertTrue(
            any("version must be 'ribbon.v1'" in e for e in report["errors"]),
            report["errors"],
        )


if __name__ == "__main__":
    unittest.main()
