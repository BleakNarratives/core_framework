from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from projects.agents.sim.site_monitor import (
    HttpResponse,
    SiteMonitor,
    SiteSource,
    _detail_metadata,
    daily_trend_report,
    parse_listings,
    parse_sitemap,
)


SOURCE = SiteSource(
    name="fixture-site",
    base_url="https://catalog.test/",
    seed_urls=("https://catalog.test/new/",),
    item_path_prefixes=("/agent/", "/tool/"),
)
ROBOTS = b"User-agent: *\nAllow: /\nDisallow: /private\n"
HTML_OLD = b"""<html><head><meta name='description' content='Latest AI tools'></head>
<body><a href='/agent/a1'>Agent Alpha</a><a href='https://evil.test/agent/no'>Bad host</a>
<a href='http://catalog.test/agent/no'>Insecure</a><a href='/private/agent/no'>No match</a>
</body></html>"""
HTML_NEW = b"""<html><head><meta name='description' content='Latest AI tools'></head>
<body><a href='/agent/a1'>Agent Alpha</a><a href='/tool/t2'>New Tool</a></body></html>"""
DETAIL_A1 = b"<html><head><title>Alpha detail</title><meta name='description' content='Agent for research'></head></html>"


class FakeFetcher:
    def __init__(self, replies: dict[str, list[HttpResponse]]):
        self.replies = {url: list(items) for url, items in replies.items()}
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int):
        self.calls.append((url, dict(headers)))
        responses = self.replies.get(url)
        if not responses:
            raise AssertionError(f"unexpected or over-served request: {url}")
        return responses.pop(0)


def ok(body: bytes, content_type: str = "text/html", headers: dict[str, str] | None = None):
    return HttpResponse(200, {"content-type": content_type, **(headers or {})}, body)


class SiteMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / "state.json"
        self.seed = SOURCE.seed_urls[0]
        self.robots_url = "https://catalog.test/robots.txt"
        self.item_a1 = "https://catalog.test/agent/a1"
        self.item_t2 = "https://catalog.test/tool/t2"

    def monitor(self, fetcher, **kwargs):
        ticks = iter(range(10_000))
        return SiteMonitor(
            self.state_path,
            sources=(SOURCE,),
            fetcher=fetcher,
            min_request_interval_seconds=0.5,
            sleeper=lambda seconds: None,
            monotonic=lambda: float(next(ticks)),
            **kwargs,
        )

    def test_parses_only_same_origin_https_listing_paths(self):
        html = """<title>Directory</title><meta name="description" content="Listings">
        <a href="/agent/a">Agent</a><a href="/tool/b">Tool</a>
        <a href="/new/?page=2">Next page</a>
        <a href="https://evil.test/agent/c">foreign</a>
        <a href="http://catalog.test/agent/d">insecure</a>
        <a href="/private/agent/e">wrong path</a><a href="/agent/a">duplicate</a>"""
        listings, pages = parse_listings(SOURCE, self.seed, html)
        self.assertEqual([item.url for item in listings], [
            "https://catalog.test/agent/a", "https://catalog.test/tool/b"
        ])
        self.assertTrue(all(item.summary == "Listings" for item in listings))
        self.assertEqual(pages, ["https://catalog.test/new?page=2"])

    def test_parses_sitemap_without_leaving_source_host_or_scope(self):
        sitemap = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://catalog.test/agent/a</loc></url>
        <url><loc>https://catalog.test/private</loc></url>
        <url><loc>https://elsewhere.test/agent/b</loc></url>
        </urlset>"""
        urls, children = parse_sitemap(sitemap, SOURCE)
        self.assertEqual(urls, ["https://catalog.test/agent/a"])
        self.assertEqual(children, [])
        with self.assertRaisesRegex(ValueError, "invalid sitemap"):
            parse_sitemap(b"not xml", SOURCE)

    def test_first_run_baselines_existing_listing_and_next_run_finds_addition(self):
        fetcher = FakeFetcher({
            self.robots_url: [ok(ROBOTS, "text/plain")],
            "https://catalog.test/new": [ok(HTML_OLD), ok(HTML_NEW)],
            self.item_a1: [ok(DETAIL_A1)],
            self.item_t2: [ok(b"<title>New Tool detail</title>")],
        })
        first = self.monitor(fetcher).run_once(as_of="2026-09-27T12:00:00Z")
        self.assertEqual([change["status"] for change in first["changes"]], ["baseline"], first["errors"])
        self.assertEqual(first["changes"][0]["url"], self.item_a1)
        self.assertEqual(first["pending_urls"]["fixture-site"], 0)
        first_state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            first_state["sources"]["fixture-site"]["items"][self.item_a1]["last_checked"],
            "2026-09-27T12:00:00Z",
        )

        second = self.monitor(fetcher).run_once(as_of="2026-09-27T12:01:00Z")
        self.assertEqual([(change["status"], change["url"]) for change in second["changes"]], [
            ("new", self.item_t2)
        ])
        self.assertEqual(second["pages_checked"], 2, second)
        self.assertEqual(second["pending_urls"]["fixture-site"], 0)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIn(self.item_t2, persisted["sources"]["fixture-site"]["items"])
        self.assertEqual(persisted["events"][-1]["status"], "new")
        self.assertNotIn("body", persisted["sources"]["fixture-site"]["items"][self.item_a1])

    def test_robots_disallow_and_rate_limit_are_respected(self):
        disallow_all = b"User-agent: *\nDisallow: /\n"
        fetcher = FakeFetcher({self.robots_url: [ok(disallow_all, "text/plain")]})
        result = self.monitor(fetcher).run_once(as_of="2026-09-27T12:00:00Z")
        self.assertEqual(len(fetcher.calls), 1)
        self.assertEqual(result["pages_checked"], 0)
        self.assertFalse(any(call[0] == self.seed for call in fetcher.calls))

        self.state_path = Path(self.temp.name) / "limited-state.json"
        limited = FakeFetcher({
            self.robots_url: [ok(ROBOTS, "text/plain")],
            "https://catalog.test/new": [HttpResponse(429, {"retry-after": "600"}, b"")],
        })
        result = self.monitor(limited).run_once(as_of="2026-09-27T12:00:00Z")
        self.assertEqual(len(limited.calls), 2, result["errors"])
        self.assertTrue(any(error["error_type"] == "HTTP429" for error in result["errors"]), result["errors"])
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["sources"]["fixture-site"]["pending"]), 1)
        self.assertIn("backoff_until", saved["sources"]["fixture-site"])

    def test_rate_limit_backoff_persists_across_monitor_instances(self):
        limited = FakeFetcher({
            self.robots_url: [ok(ROBOTS, "text/plain")],
            "https://catalog.test/new": [HttpResponse(429, {"retry-after": "600"}, b"")],
        })
        self.monitor(limited).run_once(as_of="2026-09-27T12:00:00Z")
        calls_before = len(limited.calls)
        second = self.monitor(limited).run_once(as_of="2026-09-27T12:05:00Z")
        self.assertEqual(len(limited.calls), calls_before, second["errors"])
        self.assertEqual(second["errors"][0]["error_type"], "BackoffActive")

    def test_page_budget_checkpoints_pending_work(self):
        paginated_source = SiteSource(
            "fixture-page-budget", "https://catalog.test/",
            (self.seed,), ("/agent/",),
        )
        first_page = b"<a href='/agent/a'>A</a><a href='/new/?page=2'>Next</a>"
        fetcher = FakeFetcher({
            self.robots_url: [ok(ROBOTS, "text/plain")],
            "https://catalog.test/new": [ok(first_page)],
        })
        ticks = iter(range(10_000))
        monitor = SiteMonitor(
            self.state_path, sources=(paginated_source,), fetcher=fetcher,
            min_request_interval_seconds=0.5, sleeper=lambda seconds: None,
            monotonic=lambda: float(next(ticks)), max_pages_per_run=1,
        )
        result = monitor.run_once(as_of="2026-09-27T12:00:00Z")
        self.assertGreater(result["pending_urls"]["fixture-page-budget"], 0)
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertTrue(saved["sources"]["fixture-page-budget"]["pending"])

    def test_detail_refresh_emits_update_when_metadata_changes(self):
        changed_detail = b"<title>Alpha updated</title><meta name='description' content='New description'>"
        fetcher = FakeFetcher({
            self.robots_url: [ok(ROBOTS, "text/plain")],
            self.seed: [ok(HTML_OLD), ok(HTML_OLD)],
            "https://catalog.test/new": [ok(HTML_OLD), ok(HTML_OLD)],
            self.item_a1: [ok(DETAIL_A1), ok(changed_detail)],
        })
        self.monitor(fetcher).run_once(as_of="2026-09-27T12:00:00Z")
        result = self.monitor(fetcher).run_once(as_of="2026-09-27T18:01:00Z")
        updates = [change for change in result["changes"] if change["status"] == "updated"]
        self.assertEqual(len(updates), 1)

        self.assertEqual(updates[0]["url"], self.item_a1)

    def test_detail_parser_uses_only_page_description_or_main_article_text(self):
        title, summary = _detail_metadata(
            "<title>Agent detail</title><nav>navigation text</nav>"
            "<main><p>Useful agent capability.</p><script>do not retain</script></main>"
        )
        self.assertEqual(title, "Agent detail")
        self.assertIn("Useful agent capability", summary)
        self.assertNotIn("navigation", summary)
        self.assertNotIn("do not retain", summary)

    def test_daily_report_counts_only_new_events_for_the_utc_day(self):
        state = {
            "version": 1,
            "sources": {},
            "events": [
                {
                    "site": "swarms-world", "status": "new",
                    "url": "https://swarms.world/agent/alpha",
                    "title": "<img src=x onerror=alert(1)> [Alpha agent](https://example.test)", "observed_at": "2026-09-27T02:30:00+02:00",
                },
                {
                    "site": "swarms-world", "status": "new",
                    "url": "https://swarms.world/tool/translator",
                    "title": "Translator", "observed_at": "2026-09-27T12:00:00Z",
                },
                {
                    "site": "theresanaiforthat", "status": "updated",
                    "url": "https://theresanaiforthat.com/ai/old", "title": "Old",
                    "observed_at": "2026-09-27T12:00:00Z",
                },
                {
                    "site": "theresanaiforthat", "status": "new",
                    "url": "https://theresanaiforthat.com/mcp/server",
                    "title": "Research server", "observed_at": "2026-09-28T00:00:00Z",
                },
            ],
        }
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

        report = daily_trend_report(self.state_path, "2026-09-27")

        self.assertIn("New listings recorded: 2", report)
        self.assertIn("Sources: swarms-world 2", report)
        self.assertIn("Agents 1", report)
        self.assertIn("Tools 1", report)
        self.assertIn(r"&lt;img src=x onerror=alert\(1\)&gt; \[Alpha agent\]\(https://example\.test\)", report)
        self.assertNotIn("<img", report)
        self.assertNotIn("Research server", report)
        self.assertNotIn("Old", report)
        self.assertIn("Unverified listing metadata", report)

    def test_daily_report_limits_examples_and_handles_empty_day(self):
        state = {
            "version": 1,
            "sources": {},
            "events": [
                {
                    "site": "theresanaiforthat", "status": "new",
                    "url": f"https://theresanaiforthat.com/ai/tool-{index}",
                    "title": f"Tool {index}", "observed_at": "2026-09-27T12:00:00Z",
                }
                for index in range(7)
            ],
        }
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        report = daily_trend_report(self.state_path, "2026-09-27")
        self.assertIn("New listings recorded: 7", report)
        self.assertIn("… and 2 more", report)
        self.assertEqual(report.count("Tool "), 5)

        empty = daily_trend_report(self.state_path, "2026-09-26")
        self.assertIn("New listings recorded: 0", empty)
        self.assertIn("Categories: none recorded", empty)

    def test_daily_report_rejects_invalid_date(self):
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            daily_trend_report(self.state_path, "yesterday")

    def test_invalid_existing_state_is_never_silently_replaced(self):
        self.state_path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unreadable"):
            self.monitor(FakeFetcher({}))
        self.assertEqual(self.state_path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
