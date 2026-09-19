from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_tools():
    attempts = {"count": 0}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, query, max_results=3):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("synthetic transient failure")
            return [{"title": "Result", "href": "https://example.test"}]

    duck = types.ModuleType("duckduck_search")
    duck.DDGS = FakeDDGS

    langchain = types.ModuleType("langchain")
    tools = types.ModuleType("langchain.tools")
    tools.tool = lambda function: function
    langchain.tools = tools

    trafilatura = types.ModuleType("trafilatura")
    trafilatura.fetch_url = lambda url: "downloaded"
    trafilatura.extract = lambda text, include_formatting=True: "x" * 20000

    with patch.dict(sys.modules, {        "duckduckgo_search": duck, "langchain": langchain, "langchain.tools": tools, "trafilatura": trafilatura}):
        spec = importlib.util.spec_from_file_location("vertical_radar_tools_test", ROOT / "vertical_radar" / "src" / "tools" / "tools.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, attempts


class VerticalRadarOfflineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools, cls.attempts = load_tools()

    def test_search_retries_then_returns_result(self):
        result = self.tools.search_tool("synthetic query")
        self.assertIn("Result: https://example.test", result)
        self.assertEqual(self.attempts["count"], 3)

    def test_scraper_failure_is_bounded_error(self):
        with patch.object(self.tools.trafilatura, "fetch_url", side_effect=RuntimeError("offline")):
            result = self.tools.scrape_web_data("https://example.test")
        self.assertIn("Failed to scrape the source", result)
        self.assertLess(len(result), 500)

    def test_scraper_bounds_extracted_content(self):
        result = self.tools.scrape_web_data("https://example.test")
        self.assertEqual(len(result), 15000)


if __name__ == "__main__":
    unittest.main()
