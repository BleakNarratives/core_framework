from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerticalAIOutreachTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakeNode:
            def __init__(self, text: str, attrs=None):
                self.text = text
                self.attrs = attrs or {}

            def __getitem__(self, key):
                return self.attrs[key]

        class FakeBusiness:
            def select_one(self, selector):
                values = {
                    ".dbg0pd": FakeNode("Acme"),
                    ".YDIN4c": FakeNode("4.8"),
                    ".UY7F9": FakeNode("10"),
                }
                return values.get(selector)

        class FakeBeautifulSoup:
            def __init__(self, text, parser):
                self.text = text

            def select(self, selector):
                return [FakeBusiness()] if selector == ".Nv2PK" else []

        fake_bs4 = types.ModuleType("bs4")
        fake_bs4.BeautifulSoup = FakeBeautifulSoup
        fake_requests = types.ModuleType("requests")
        fake_requests.get = lambda *args, **kwargs: None
        with patch.dict(sys.modules, {"bs4": fake_bs4, "requests": fake_requests}):
            cls.scraper = load_module("vertical_ai_scraper_test", ROOT / "vertical_ai" / "scrape_google_reviews.py")
        cls.outreach = load_module("vertical_ai_outreach_test", ROOT / "vertical_ai" / "automate_outreach.py")
        cls.adapter = load_module("vertical_ai_adapter_test", ROOT / "vertical_ai" / "outreach_adapter.py")

    def test_scraper_uses_mocked_response_and_filters_fields(self):
        response = Mock(text='<div class="Nv2PK"><div class="dbg0pd">Acme</div><span class="YDIN4c">4.8</span><span class="UY7F9">10</span></div>')
        with patch.object(self.scraper.requests, "get", return_value=response) as get:
            result = self.scraper.get_google_reviews("restaurants", "Wellington", num_businesses=1)
        get.assert_called_once()
        self.assertEqual(result[0]["name"], "Acme")
        self.assertEqual(result[0]["rating"], "4.8")
        self.assertEqual(result[0]["website"], "No Website")

    def test_smtp_success_is_fully_mocked(self):
        server = Mock()
        server.__enter__ = Mock(return_value=server)
        server.__exit__ = Mock(return_value=False)
        with patch.object(self.outreach.smtplib, "SMTP", return_value=server) as smtp:
            self.outreach.send_email("sender@example.test", "synthetic", "recipient@example.test", "Subject", "Body")
        smtp.assert_called_once_with("smtp.gmail.com", 587)
        server.starttls.assert_called_once_with()
        server.login.assert_called_once_with("sender@example.test", "synthetic")
        server.sendmail.assert_called_once()

    def test_smtp_failure_does_not_escape_or_retry(self):
        with patch.object(self.outreach.smtplib, "SMTP", side_effect=OSError("offline")) as smtp:
            self.outreach.send_email("sender@example.test", "synthetic", "recipient@example.test", "Subject", "Body")
        smtp.assert_called_once_with("smtp.gmail.com", 587)

    def test_handoff_is_dry_run_and_contains_no_recipient_or_secret(self):
        result = self.adapter.build_handoff({
            "session_id": "vai_test",
            "context": {"label": "Acme Plumbing", "data": {"content": "private notes"}},
            "champion": {"name": "Fast Booking", "thesis": "Reduce missed calls", "first_action": "Pilot", "target_outcome": "5 bookings"},
            "outreach": {"platform_variants": {"email": "Hello", "linkedin": "Hi", "sms": "Call"}},
        })
        self.assertEqual(result["mode"], "dry-run")
        self.assertFalse(result["send"])
        self.assertFalse(result["credentials_required"])
        self.assertIsNone(result["review"]["recipient_address"])
        self.assertNotIn("private notes", str(result))

    def test_handoff_write_is_local_only(self):
        with TemporaryDirectory() as directory:
            path = self.adapter.write_handoff({"session_id": "vai_test"}, Path(directory) / "handoff.json")
            self.assertTrue(path.is_file())
            self.assertIn('"send": false', path.read_text())


if __name__ == "__main__":
    unittest.main()
