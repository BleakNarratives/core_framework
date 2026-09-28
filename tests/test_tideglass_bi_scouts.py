from __future__ import annotations

import unittest

from projects.agents.sim.bi_scouts import (
    MAX_FINDINGS_PER_SCOUT,
    ScoutFinding,
    ScoutTask,
    run_scouts,
)


TASK = ScoutTask(
    market_id="market-1",
    question="Will the event occur?",
    as_of="2026-09-27T12:00:00Z",
    action="Run a small pilot",
)


def finding(scout: str, **overrides) -> ScoutFinding:
    values = {
        "scout_name": scout,
        "claim": "A sourced qualitative finding.",
        "source": "https://example.test/source",
        "observed_at": "2026-09-27T11:30:00Z",
    }
    values.update(overrides)
    return ScoutFinding(**values)


class BIScoutCoordinatorTests(unittest.TestCase):
    def test_runs_specialists_and_preserves_unverified_findings(self):
        report = run_scouts(
            TASK,
            {
                "news_scout": lambda task: [finding("news_scout")],
                "market_structure": lambda task: [
                    finding("market_structure", confidence=0.6)
                ],
            },
        )
        payload = report.to_dict()
        self.assertEqual(payload["completed_scouts"], ["news_scout", "market_structure"])
        self.assertEqual(len(payload["findings"]), 2)
        self.assertTrue(all(item["verified"] is False for item in payload["findings"]))
        self.assertFalse(payload["forecast_generated"])
        self.assertEqual(payload["trust"], "unverified_evidence_only")
        self.assertEqual(len(payload["findings"][0]["content_sha256"]), 64)

    def test_one_scout_failure_does_not_hide_other_findings(self):
        def failed(task):
            raise RuntimeError("exception text is not exposed")

        report = run_scouts(
            TASK,
            {
                "broken": failed,
                "working": lambda task: [finding("working")],
            },
        )
        self.assertEqual(len(report.findings), 1)
        self.assertEqual(report.findings[0].scout_name, "working")
        self.assertEqual(report.failures[0].error_type, "RuntimeError")
        self.assertNotIn("exception text", str(report.to_dict()))

    def test_scout_identity_mismatch_and_future_finding_fail_that_scout(self):
        mismatch = run_scouts(TASK, {"named": lambda task: [finding("other")]})
        self.assertEqual(mismatch.findings, ())
        self.assertEqual(mismatch.failures[0].error_type, "ValueError")

        future = finding("future", observed_at="2026-09-27T12:01:00Z")
        report = run_scouts(TASK, {"future": lambda task: [future]})
        self.assertEqual(report.findings, ())
        self.assertEqual(report.failures[0].error_type, "ValueError")

    def test_finding_limit_is_enforced_without_unbounded_iteration(self):
        def too_many(task):
            for _ in range(MAX_FINDINGS_PER_SCOUT + 10_000):
                yield finding("flood")

        report = run_scouts(TASK, {"flood": too_many})
        self.assertEqual(report.findings, ())
        self.assertEqual(report.failures[0].error_type, "ValueError")

    def test_invalid_task_and_finding_provenance_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "market_id"):
            ScoutTask("", "question", "2026-09-27T12:00:00Z")
        with self.assertRaisesRegex(ValueError, "timezone"):
            ScoutTask("market", "question", "2026-09-27T12:00:00")
        with self.assertRaisesRegex(ValueError, "observed_at"):
            finding("scout", observed_at="not a date")
        with self.assertRaisesRegex(ValueError, "confidence"):
            finding("scout", confidence=1.5)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            finding("scout", content_sha256="fake")

    def test_scout_collection_limits_are_validated(self):
        with self.assertRaisesRegex(ValueError, "at most"):
            run_scouts(TASK, {f"scout-{i}": lambda task: [] for i in range(13)})
        with self.assertRaisesRegex(ValueError, "callable"):
            run_scouts(TASK, {"broken": None})


if __name__ == "__main__":
    unittest.main()
