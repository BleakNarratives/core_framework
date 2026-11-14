import json
import tempfile
import unittest
from pathlib import Path

from scoutlab.engine import ScoutLab


class ScoutLabTests(unittest.TestCase):
    def test_scan_report_and_feedback_personalize_ranking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "market_signals.json").write_text(json.dumps([
                {"ticker": "AAA", "title": "Debt covenant warning", "url": "https://example.test/a", "severity": "WARNING", "observed": "2026-01-01"},
                {"ticker": "BBB", "title": "New product launch", "url": "https://example.test/b", "severity": "INFO", "observed": "2026-01-02"},
            ]), encoding="utf-8")
            with ScoutLab(root) as app:
                app.initialize()
                app.set_goal("debt covenant distress")
                count, paths = app.scan(directories=("fixtures",))
                self.assertEqual(count, 2)
                self.assertEqual(len(paths), 1)
                before = app.ranked(2)
                debt_id = next(row["id"] for _, row in before if "Debt" in row["title"])
                other_id = next(row["id"] for _, row in before if "product" in row["title"])
                self.assertGreater(before[0][0], before[1][0])
                app.rate(other_id, True)
                after = app.ranked(2)
                self.assertGreater(after[0][0], next(score for score, row in before if row["id"] == other_id))
                self.assertEqual(app.stats()["ratings"], 1)
                self.assertTrue(app.write_report().is_file())
                app.rate(debt_id, False)

    def test_legacy_runs_schema_is_not_assumed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with ScoutLab(root) as app:
                app.initialize()
                self.assertEqual(app.scan(directories=())[0], 0)
                self.assertEqual(app.stats()["runs"], 1)


if __name__ == "__main__":
    unittest.main()
