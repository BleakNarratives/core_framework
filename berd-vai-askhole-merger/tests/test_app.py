from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import app as webapp


class BrowserWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        webapp.DB_PATH = Path(self.temp.name) / "workbench.sqlite3"
        webapp.app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        self.client = webapp.app.test_client()

    def csrf_token(self, path: str = "/intake") -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_control_room_shows_local_signals_and_real_project_wormholes(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        for slug in ("berd", "meboard", "pytch", "twoie", "hotseat", "vertical-ai", "askhole", "vertical-engine"):
            self.assertIn(f'href="/wormholes/{slug}"'.encode(), response.data)
        self.assertIn(b"Move on signal", response.data)
        self.assertIn(b"Signal \xe2\x86\x92 next move", response.data)
        self.assertIn(b"data-ring=\"glass\"", response.data)
        self.assertIn(b"Action only", response.data)
        self.assertIn(b"hides info at 35%, review at 70%, and action at 92%", response.data)
        self.assertIn(b"/api/control-room", self.client.get("/static/control-room.js").data)
        api = self.client.get("/api/control-room")
        self.assertEqual(api.status_code, 200)
        data = api.get_json()
        self.assertIn("pytch", data["services"])
        self.assertIn("scrying_mode", data)
        self.assertEqual(api.headers["Cache-Control"], "no-store")

    def test_dashboard_uses_real_summary_metrics_without_seasonal_garnish(self):
        token = self.csrf_token("/intake")
        self.client.post("/leads", data={"_csrf_token": token, "name": "Measured Lead", "city": "Town"})
        response = self.client.get("/intake")
        self.assertIn(b"Lead records", response.data)
        self.assertIn(b"Evidence items", response.data)
        self.assertIn(b"Local evidence workbench", response.data)
        self.assertNotIn(b"Halloween", response.data)
        self.assertIn(b"<span class=\"metric-value\">1</span>", response.data)
        self.assertIn(b'data-scroll-depth="0"', response.data)
        self.assertIn(b"<span class=\"metric-value\">1</span><span class=\"metric-label\">Evidence items", response.data)
        self.assertIn(b"Berdical", response.data)

    def test_askhole_scenario_is_csrf_gated_bounded_and_unverified(self):
        self.assertEqual(self.client.post("/tools/askhole/scenario", data={"vertical":"plumber"}).status_code, 400)
        token = self.csrf_token("/wormholes/askhole")
        result = self.client.post("/tools/askhole/scenario", headers={"X-CSRF-Token":token}, data={
            "vertical":"plumber", "missed_calls":"10", "recovery_rate":"0.25",
        })
        self.assertEqual(result.status_code, 200)
        data = result.get_json()
        self.assertEqual(data["scenario_context_not_forecast"], 450)
        self.assertEqual(data["trust"], "unverified_legacy_context")
        self.assertEqual(self.client.post("/tools/askhole/scenario", headers={"X-CSRF-Token":token}, data={
            "vertical":"plumber", "missed_calls":"10001", "recovery_rate":"0.25",
        }).status_code, 400)

    def test_health_is_local_only_and_delivery_disabled(self):
        result = self.client.get("/health").get_json()
        self.assertEqual(result, {"status": "ok", "mode": "local-only", "delivery": "disabled"})
        response = self.client.get("/health")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("connect-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_pytch_wormhole_clickthrough_and_staging_leave_source_read_only(self):
        from app import PYTCH_DB_PATH
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "pytch.sqlite3"
            db = sqlite3.connect(source)
            db.executescript("""
                CREATE TABLE campaigns(id INTEGER PRIMARY KEY, wrapper_name TEXT, target_persona TEXT, status TEXT, emails_sent INTEGER, replies INTEGER, demos_booked INTEGER, deals_closed INTEGER, revenue INTEGER);
                CREATE TABLE leads(id INTEGER PRIMARY KEY, company TEXT, contact_name TEXT, email TEXT, source TEXT, industry TEXT);
                CREATE TABLE deals(id INTEGER PRIMARY KEY, lead_id INTEGER);
                CREATE TABLE outreach(id INTEGER PRIMARY KEY, lead_id INTEGER, campaign TEXT, subject TEXT, body TEXT, sent_at TEXT, replied INTEGER DEFAULT 0);
                INSERT INTO campaigns VALUES(1,'test','Persona','active',0,0,0,0,0);
                INSERT INTO leads VALUES(1,'Local Plumbing','Test Contact','private@example.test','manual','plumber');
                INSERT INTO outreach VALUES(7,1,'test','Source subject','Unsent source text',NULL,0);
            """)
            db.commit(); db.close()
            original = webapp.PYTCH_DB_PATH
            webapp.PYTCH_DB_PATH = source
            self.addCleanup(setattr, webapp, "PYTCH_DB_PATH", original)
            page = self.client.get("/wormholes/pytch")
            self.assertEqual(page.status_code, 200)
            token_match = re.search(rb'name="_csrf_token" value="([^"]+)"', page.data)
            self.assertIsNotNone(token_match)
            token = token_match.group(1).decode()
            self.assertIn(b"PYTCH #7", page.data)
            self.assertIn(b"Stage for review", page.data)
            staged = self.client.post("/pytch/7/stage", headers={"X-CSRF-Token": token})
            self.assertEqual(staged.status_code, 200)
            payload = staged.get_json()
            lead_id = payload["lead_id"]
            draft_id = int(payload["redirect"].rsplit("/", 1)[1])
            draft = self.client.get(payload["redirect"])
            self.assertEqual(draft.status_code, 200)
            self.assertIn(b"Unsent source text", draft.data)
            self.assertIn(b"SOURCE LOCK", draft.data)
            self.assertIn(b"Source-body SHA-256", draft.data)
            self.assertIn(b"name=\"body\"", draft.data)
            self.assertIn(b"starts as the exact Pytch source", draft.data)
            bad_recipient = self.client.post(f"/drafts/{draft_id}/review", data={
                "_csrf_token": token, "reviewer": "User", "notes": "Reviewed.", "recipient": "wrong@example.test",
            })
            self.assertEqual(bad_recipient.status_code, 302)
            saved_draft = webapp._find_draft(draft_id)
            self.assertEqual(saved_draft["status"], "draft")
            reviewed = self.client.post(f"/drafts/{draft_id}/review", data={
                "_csrf_token": token, "reviewer": "User", "notes": "Source and exact text checked.", "recipient": "private@example.test",
            })
            self.assertEqual(reviewed.status_code, 302)
            self.assertEqual(webapp._find_draft(draft_id)["status"], "reviewed")
            refused = self.client.post(f"/drafts/{draft_id}/approve", data={
                "_csrf_token": token, "confirm": "yes",
            })
            self.assertEqual(refused.status_code, 302)
            permitted = self.client.post(f"/drafts/{draft_id}/approve", data={
                "_csrf_token": token, "confirm": "yes", "confirm_recipient": "yes",
            })
            self.assertEqual(permitted.status_code, 302)
            self.assertEqual(self.client.get(f"/drafts/{draft_id}/export").status_code, 200)
            repeated = self.client.post("/pytch/7/stage", headers={"X-CSRF-Token": token}).get_json()
            self.assertEqual(repeated["lead_id"], lead_id)
            db = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
            self.assertEqual(db.execute("SELECT sent_at FROM outreach WHERE id=7").fetchone()[0], None)
            self.assertEqual(db.execute("SELECT email FROM leads WHERE id=1").fetchone()[0], "private@example.test")
            db.close()
            self.assertNotIn("private@example.test", str(payload))

    def test_posts_without_csrf_are_rejected(self):
        response = self.client.post("/leads", data={"name": "Example"})
        self.assertEqual(response.status_code, 400)

    def test_browser_lead_to_draft_to_review_to_manual_export(self):
        token = self.csrf_token("/intake")
        response = self.client.post(
            "/leads", data={"_csrf_token": token, "name": "Example Plumbing", "vertical": "plumber"}
        )
        self.assertEqual(response.status_code, 302)
        home = self.client.get("/control-room")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Move on signal", home.data)
        intake = self.client.get("/intake")
        self.assertIn(b"Example Plumbing", intake.data)
        self.assertIn(b"Berdical AI", home.data)
        self.assertIn(b"name=\"theme-color\"", home.data)
        self.assertIn(b"control-room.css", home.data)
        response = self.client.post("/leads/1/drafts", data={"_csrf_token": token})
        self.assertEqual(response.status_code, 302)
        draft_page = self.client.get("/drafts/1")
        self.assertEqual(draft_page.status_code, 200)
        self.assertIn(b"No delivery exists", draft_page.data)
        denied = self.client.get("/drafts/1/export")
        self.assertEqual(denied.status_code, 302)
        self.client.post("/drafts/1/review", data={
            "_csrf_token": token, "reviewer": "User", "notes": "Checked claims and recipient.",
        })
        self.client.post("/drafts/1/approve", data={"_csrf_token": token, "confirm": "yes"})
        exported = self.client.get("/drafts/1/export")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment; filename=\"draft-1.txt\"", exported.headers["Content-Disposition"])
        self.assertIn(b"Example Plumbing", exported.data)

    def test_lead_detail_shows_exactly_three_type3_potentials(self):
        token = self.csrf_token("/intake")
        self.client.post("/leads", data={"_csrf_token": token, "name": "Hidden Egg Lead"})
        response = self.client.get("/leads/1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b"class=\"type3-idea\""), 3)
        self.assertIn(b"<details class=\"type3-shell\">", response.data)
        self.assertIn(b"aria-label=\"Reveal the Type III force multiplier\"", response.data)
        self.assertIn(b"TYPE III FORCE MULTIPLIER", response.data)
        self.assertIn(b"exploratory\342\200\224not scored", response.data)
        self.assertIn(b"class=\"breadcrumb\"", response.data)

    def test_missing_approval_confirmation_does_not_approve(self):
        token = self.csrf_token("/intake")
        self.client.post("/leads", data={"_csrf_token": token, "name": "Example"})
        self.client.post("/leads/1/drafts", data={"_csrf_token": token})
        self.client.post("/drafts/1/review", data={
            "_csrf_token": token, "reviewer": "User", "notes": "Checked.",
        })
        self.client.post("/drafts/1/approve", data={"_csrf_token": token})
        self.assertEqual(self.client.get("/drafts/1/export").status_code, 302)


if __name__ == "__main__":
    unittest.main()
