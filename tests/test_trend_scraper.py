"""Offline tests for the trend_scraper scaffold. No network is exercised."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.ingest.trend_scraper import (
    HttpJsonSource,
    LocalJsonSource,
    TrendItem,
    aggregate,
    write_digest,
)


def _local(name, rows):
    path = Path(tempfile.mkdtemp()) / "trends.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return LocalJsonSource(name, path)


class TestTrendScraper(unittest.TestCase):
    def test_aggregate_dedupes_and_ranks_by_score(self):
        a = _local("a", [{"title": "X", "url": "u", "score": 1},
                         {"title": "Y", "url": "v", "score": 5}])
        b = _local("b", [{"title": "  x ", "url": "u", "score": 9}])  # dupe of X
        items = aggregate([a, b])
        self.assertEqual([i.title for i in items], ["Y", "X"])  # ranked, dupe dropped
        self.assertEqual(len(items), 2)

    def test_network_source_is_gated(self):
        with self.assertRaises(RuntimeError):
            HttpJsonSource("live", "http://example.test").fetch()

    def test_write_digest_uses_only_given_provenance(self):
        items = [TrendItem(source="a", title="X", url="http://x",
                           observed="2026-09-30", score=3)]
        out = Path(tempfile.mkdtemp()) / "digest.md"
        write_digest(items, out, generated="2026-09-30")
        text = out.read_text(encoding="utf-8")
        self.assertIn("| 3 | a |", text)
        self.assertIn("[X](http://x)", text)
        self.assertIn("generated: 2026-09-30", text)


if __name__ == "__main__":
    unittest.main()
