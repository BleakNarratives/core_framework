from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import workbench


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "private" / "test.sqlite3"

    def test_lead_and_evidence_are_persisted_as_unverified_with_digest(self):
        lead_id = workbench.add_lead(self.db, {
            "name": "Example Plumbing", "vertical": "plumber", "city": "Example City",
            "website": "https://example.test", "rating": "4.2", "review_count": "12",
            "notes": "User-supplied note", "source": "operator spreadsheet",
        })
        record = workbench.get_lead(self.db, lead_id)
        self.assertEqual(record["lead"]["name"], "Example Plumbing")
        self.assertEqual({item["trust"] for item in record["evidence"]}, {"unverified"})
        self.assertTrue(all(len(item["sha256"]) == 64 for item in record["evidence"]))
        self.assertTrue(Path(self.db).exists())
        self.assertEqual(os.stat(self.db).st_mode & 0o777, 0o600)

    def test_summary_counts_are_uncapped_local_database_counts(self):
        first = workbench.add_lead(self.db, {"name": "Example One", "city": "A"})
        workbench.add_lead(self.db, {"name": "Example Two", "website": "https://example.test"})
        workbench.create_draft(self.db, first)
        counts = workbench.summary_counts(self.db)
        self.assertEqual(counts, {"lead_records": 2, "unverified_evidence": 2, "drafts": 1})

    def test_rejects_unsafe_url_and_controls(self):
        for url in ("javascript:alert(1)", "https://user:password@example.test", "file:///etc/passwd"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                workbench.add_lead(self.db, {"name": "Example", "website": url})
        with self.assertRaises(ValueError):
            workbench.add_lead(self.db, {"name": "bad\x00name"})

    def test_csv_import_requires_supported_headers_and_is_bounded(self):
        ids = workbench.import_csv(
            self.db,
            "name,vertical,city,notes\nExample Plumbing,plumber,Example City,Owner-provided note\n",
        )
        self.assertEqual(len(ids), 1)
        self.assertEqual(workbench.get_lead(self.db, ids[0])["lead"]["source"], "CSV import (user-provided)")
        with self.assertRaisesRegex(ValueError, "unsupported CSV columns"):
            workbench.import_csv(self.db, "name,password\nExample,secret\n")
        with self.assertRaisesRegex(ValueError, "requires a name"):
            workbench.import_csv(self.db, "business\nExample\n")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            workbench.import_csv(self.db, b"name\n\xff")

    def test_draft_never_claims_business_has_a_known_loss(self):
        lead_id = workbench.add_lead(self.db, {"name": "Example Dental", "vertical": "dentist"})
        draft_id = workbench.create_draft(self.db, lead_id)
        draft = workbench.get_draft(self.db, draft_id)
        self.assertEqual(draft["status"], "draft")
        self.assertIn("I don’t know whether intake", draft["body"])
        self.assertNotIn("$1,200", draft["body"])
        self.assertIn("missed_call_cost", draft["economics_snapshot"])
        self.assertFalse(any("email" in key or "send" in key for key in draft))

    def test_review_then_approval_required_for_export(self):
        lead_id = workbench.add_lead(self.db, {"name": "Example Dental", "vertical": "dentist"})
        draft_id = workbench.create_draft(self.db, lead_id)
        with self.assertRaisesRegex(ValueError, "not approved"):
            workbench.export_draft(self.db, draft_id)
        with self.assertRaisesRegex(ValueError, "reviewed before"):
            workbench.approve_manual_export(self.db, draft_id)
        workbench.review_draft(self.db, draft_id, "Reviewer", "Checked this exact text and evidence.")
        workbench.approve_manual_export(self.db, draft_id)
        exported = workbench.export_draft(self.db, draft_id)
        self.assertIn("Example Dental", exported)
        self.assertIn("If this isn’t relevant", exported)
        self.assertTrue(any(event["event"] == "draft.approved_for_manual_export" for event in workbench.list_audit_events(self.db)))

    def test_review_update_revokes_approval_and_approved_draft_cannot_change_review(self):
        lead_id = workbench.add_lead(self.db, {"name": "Example", "vertical": "plumber"})
        draft_id = workbench.create_draft(self.db, lead_id)
        workbench.review_draft(self.db, draft_id, "Reviewer", "Reviewed.")
        workbench.approve_manual_export(self.db, draft_id)
        with self.assertRaisesRegex(ValueError, "immutable"):
            workbench.review_draft(self.db, draft_id, "Reviewer", "Try editing after approval")
        self.assertTrue(workbench.export_draft(self.db, draft_id))

    def test_limits_and_audit_events(self):
        with self.assertRaisesRegex(ValueError, "characters"):
            workbench.add_lead(self.db, {"name": "x" * 201})
        workbench.add_lead(self.db, {"name": "Example"})
        self.assertIn("lead.created", [event["event"] for event in workbench.list_audit_events(self.db)])


if __name__ == "__main__":
    unittest.main()
