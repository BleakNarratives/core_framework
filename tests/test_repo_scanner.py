"""
repo_scanner tests.

Fully offline and deterministic: every fixture is written into a temp dir, so
the scanner is never pointed at the live repo tree. Mirrors the sandboxed
import pattern in test_boardroom_paths_offline.py because the module lives
under a path that is not importable as a package.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "Code-City-Apocalypse" / "Code_City" / "repo_scanner.py"
)

# Code-City-Apocalypse/ sits outside the repo's gitignore allowlist (which
# tracks only src/tools/templates/tests/docs/projects/rag_storage), so the
# scanner module is deliberately untracked. On a clean clone it is absent and
# these tests skip with a reason rather than erroring on import.
requires_scanner = unittest.skipIf(
    not MODULE_PATH.exists(),
    f"repo_scanner.py not present in this checkout: {MODULE_PATH}",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("offline_repo_scanner", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rs = _load_module() if MODULE_PATH.exists() else None


@requires_scanner
class TestScanText(unittest.TestCase):
    def test_counts_are_measured_not_invented(self):
        text = "a = 1\n\n# comment\nb = 2\n"
        m = rs.scan_text(text)
        self.assertEqual(m["lines"], 4)
        self.assertEqual(m["blank_lines"], 1)
        self.assertEqual(m["comment_lines"], 1)
        self.assertEqual(m["code_lines"], 2)

    def test_clean_file_scores_zero(self):
        m = rs.scan_text("def f():\n    return 1\n")
        self.assertEqual(m["flaw_score"], 0)
        self.assertEqual(m["todos"], 0)

    def test_todo_markers_are_detected(self):
        m = rs.scan_text("x = 1  # TODO: wire this up\ny = 2  # FIXME: broken\n")
        self.assertEqual(m["todos"], 2)
        self.assertGreater(m["flaw_score"], 0)

    def test_deep_nesting_is_detected(self):
        flat = rs.scan_text("\n".join(f"    x{i} = {i}" for i in range(3)))
        deep = rs.scan_text("\n".join("    " * 8 + f"x{i} = {i}" for i in range(3)))
        self.assertGreater(deep["max_indent"], flat["max_indent"])
        self.assertGreater(deep["flaw_score"], flat["flaw_score"])

    def test_tabs_count_as_four(self):
        self.assertEqual(rs._indent_width("\t\tx = 1"), 8)
        self.assertEqual(rs._indent_width("    x = 1"), 4)
        self.assertEqual(rs._indent_width("x = 1"), 0)

    def test_bare_except_is_detected(self):
        clean = rs.scan_text("try:\n    pass\nexcept ValueError:\n    pass\n")
        bare = rs.scan_text("try:\n    pass\nexcept:\n    pass\n")
        self.assertEqual(clean["signals"]["bare_except"], 0)
        self.assertEqual(bare["signals"]["bare_except"], 1)
        self.assertGreater(bare["flaw_score"], clean["flaw_score"])

    def test_flaw_score_is_clamped_to_0_100(self):
        awful = "\n".join("    " * 12 + f"x{i} = {i}  # TODO FIXME HACK XXX" for i in range(200))
        self.assertLessEqual(rs.scan_text(awful)["flaw_score"], 100)

    def test_scan_text_is_pure(self):
        """Same input must yield identical output (determinism, AGENTS.md §6)."""
        text = "a = 1  # TODO\n" * 50
        self.assertEqual(rs.scan_text(text), rs.scan_text(text))


@requires_scanner
class TestScanRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "pkg").mkdir()
        (self.tmp / "node_modules").mkdir()
        (self.tmp / "__pycache__").mkdir()
        (self.tmp / "pkg" / "good.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        (self.tmp / "pkg" / "bad.py").write_text(
            "\n".join("    " * 10 + f"x{i} = {i}  # TODO" for i in range(30)),
            encoding="utf-8",
        )
        (self.tmp / "readme.md").write_text("# hi\n", encoding="utf-8")
        (self.tmp / "data.bin").write_bytes(b"\x00\x01\x02binary")
        # Vendored/build trees must not appear as buildings.
        (self.tmp / "node_modules" / "dep.py").write_text("z = 1\n", encoding="utf-8")
        (self.tmp / "__pycache__" / "cached.py").write_text("q = 1\n", encoding="utf-8")

    def test_scans_source_files_and_prunes(self):
        city = rs.scan_repo(self.tmp)
        paths = {b["path"] for b in city["buildings"]}
        self.assertIn("pkg/good.py", paths)
        self.assertIn("pkg/bad.py", paths)
        self.assertIn("readme.md", paths)
        self.assertNotIn("data.bin", paths)  # binary, no recognised suffix
        self.assertFalse(any(p.startswith("node_modules/") for p in paths))
        self.assertFalse(any(p.startswith("__pycache__/") for p in paths))

    def test_totals_are_internally_consistent(self):
        city = rs.scan_repo(self.tmp)
        t = city["totals"]
        self.assertEqual(t["files"], len(city["buildings"]))
        self.assertEqual(t["lines"], sum(b["lines"] for b in city["buildings"]))
        self.assertEqual(t["code_lines"], sum(b["code_lines"] for b in city["buildings"]))
        self.assertEqual(t["todos"], sum(b["todos"] for b in city["buildings"]))
        self.assertAlmostEqual(
            t["mean_flaw"], round(t["flaw_score"] / t["files"], 2), places=2
        )

    def test_height_derives_from_code_lines(self):
        city = rs.scan_repo(self.tmp)
        for b in city["buildings"]:
            self.assertEqual(b["height"], 1 + (b["code_lines"] // 40))

    def test_language_detected(self):
        city = rs.scan_repo(self.tmp)
        langs = {b["path"]: b["language"] for b in city["buildings"]}
        self.assertEqual(langs["pkg/good.py"], "python")
        self.assertEqual(langs["readme.md"], "docs")

    def test_determinism(self):
        a = rs.scan_repo(self.tmp)
        b = rs.scan_repo(self.tmp)
        self.assertEqual(rs.city_digest(a), rs.city_digest(b))

    def test_ordering_is_heaviest_first_then_path(self):
        city = rs.scan_repo(self.tmp)
        keys = [(-b["mass"], b["path"]) for b in city["buildings"]]
        self.assertEqual(keys, sorted(keys))

    def test_max_files_sets_truncated_flag(self):
        city = rs.scan_repo(self.tmp, max_files=1)
        self.assertTrue(city["truncated"])
        self.assertLessEqual(len(city["buildings"]), 1)

    def test_empty_dir_has_no_division_error(self):
        empty = Path(tempfile.mkdtemp())
        city = rs.scan_repo(empty)
        self.assertEqual(city["totals"]["files"], 0)
        self.assertEqual(city["totals"]["mean_flaw"], 0.0)

    def test_non_directory_raises(self):
        with self.assertRaises(NotADirectoryError):
            rs.scan_repo(self.tmp / "readme.md")

    def test_summarize_ranks_worst_first(self):
        city = rs.scan_repo(self.tmp)
        rows = rs.summarize(city, top=2)
        self.assertLessEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "pkg/bad.py")


@requires_scanner
class TestWriteCityJson(unittest.TestCase):
    def test_writes_valid_json_with_digest(self):
        tmp = Path(tempfile.mkdtemp())
        city = rs.scan_repo(tmp)
        out = rs.write_city_json(city, tmp / "city.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "code_city/1")
        self.assertEqual(data["digest"], rs.city_digest(city))
        self.assertIn("buildings", data)

    def test_no_temp_files_left_behind(self):
        tmp = Path(tempfile.mkdtemp())
        rs.write_city_json(rs.scan_repo(tmp), tmp / "city.json")
        self.assertEqual([p.name for p in tmp.iterdir()], ["city.json"])

    def test_creates_parent_dirs(self):
        tmp = Path(tempfile.mkdtemp())
        out = rs.write_city_json(rs.scan_repo(tmp), tmp / "nested" / "deep" / "city.json")
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
