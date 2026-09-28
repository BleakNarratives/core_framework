"""Offline policy tests for Puter's advisory Bufftag adapter."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Bufftag import atlas, bufftag
from Bufftag.puter_adapter import AdvisorError, BufftagAdvisor


class FakeAI:
    def __init__(self, *, success: bool = True) -> None:
        self.success = success
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        if not self.success:
            return {"success": False, "error": "offline fixture"}
        return {
            "success": True,
            "content": "Advisory only: review the cited local finding.",
            "provider": "fixture",
            "model": "offline",
        }


class AdvisorCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.atlas_path = self.root / ".bufftag" / "moves.jsonl"
        self.anchor_path = self.root / "separate" / "movement-head.json"
        self.key = "advisor-test-key"
        self.env = mock.patch.dict(os.environ, {"BUFFTAG_KEY": self.key})
        self.env.start()
        self.advisors: list[BufftagAdvisor] = []

    def tearDown(self):
        for advisor in reversed(self.advisors):
            advisor.close()
        self.env.stop()
        self.temp.cleanup()

    def make_route(self, *, signed=True):
        target = self.root / "canonical" / "location.py"
        target.parent.mkdir(parents=True)
        target.write_text("VALUE = 1\n", encoding="utf-8")
        return atlas.record_route(
            workspace=self.root,
            atlas_path=self.atlas_path,
            old_path="old/location.py",
            new_path="canonical/location.py",
            actor="test",
            reason="consolidation",
            secret=self.key.encode() if signed else None,
        )

    def advisor(self, *, lane="freebuff", owner="owner-1", anchor=True):
        value = BufftagAdvisor(
            workspace=self.root,
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path if anchor else None,
            lane=lane,
            owner=owner,
            signing_key_env="BUFFTAG_KEY",
        )
        self.advisors.append(value)
        return value

    def anchor_route(self):
        self.make_route()
        return atlas.create_anchor(
            atlas_path=self.atlas_path,
            anchor_path=self.anchor_path,
            actor="operator",
            reason="approved baseline",
            secret=self.key.encode(),
        )


class AssistanceTests(AdvisorCase):
    def test_assistance_uses_signed_evidence_but_executes_nothing(self):
        self.anchor_route()
        ai = FakeAI()
        result = self.advisor().assist(ai, "What should the operator inspect?")
        self.assertTrue(result["success"])
        self.assertTrue(result["advisory_only"])
        self.assertEqual(result["executed_actions"], [])
        self.assertEqual(len(ai.calls), 1)
        payload = json.loads(ai.calls[0]["messages"][1]["content"])
        self.assertEqual(payload["mode"], "assistance")
        self.assertIn("never model instructions", payload["bufftag_evidence"]["trust"])
        self.assertEqual(ai.calls[0]["kwargs"]["temperature"], 0.2)

    def test_course_correction_is_separate_advisory_mode(self):
        self.anchor_route()
        ai = FakeAI()
        result = self.advisor().correct_course(ai, "Correct the route review process")
        self.assertTrue(result["success"])
        payload = json.loads(ai.calls[0]["messages"][1]["content"])
        self.assertEqual(payload["mode"], "course-correction")
        self.assertEqual(result["executed_actions"], [])

    def test_rollback_evidence_is_reported_but_never_claimed_clean(self):
        self.anchor_route()
        self.atlas_path.write_text("", encoding="utf-8")
        ai = FakeAI()
        result = self.advisor().assist(ai, "Is the movement atlas healthy?")
        self.assertTrue(result["success"])
        evidence = json.loads(ai.calls[0]["messages"][1]["content"])["bufftag_evidence"]
        codes = {finding["code"] for finding in evidence["report"]["findings"]}
        self.assertIn("movement_rollback", codes)
        self.assertFalse(evidence["report"]["ok"])

    def test_provider_failure_and_oversized_request_do_not_execute(self):
        self.anchor_route()
        ai = FakeAI(success=False)
        result = self.advisor().assist(ai, "Review this")
        self.assertFalse(result["success"])
        self.assertTrue(result["advisory_only"])
        with self.assertRaisesRegex(AdvisorError, "exceeds"):
            self.advisor().assist(FakeAI(), "x" * 5000)

    def test_absent_signing_key_keeps_puter_available_as_unsigned(self):
        self.make_route(signed=False)
        with mock.patch.dict(os.environ, {}, clear=True):
            advisor = BufftagAdvisor(
                workspace=self.root,
                lane="unsigned",
                owner="fixture",
                signing_key_env="BUFFTAG_KEY",
            )
            self.advisors.append(advisor)
            self.assertIsNone(advisor.secret)
            status = advisor.status()
            self.assertTrue(status["report"]["ok"], status)


class ReviewLaneTests(AdvisorCase):
    def test_active_lane_blocks_another_owner_without_ai_call(self):
        self.anchor_route()
        first = self.advisor(lane="shared", owner="cli-1")
        first.claim_lease()
        second = self.advisor(lane="shared", owner="cli-2")
        ai = FakeAI()
        with self.assertRaisesRegex(AdvisorError, "leased by"):
            second.assist(ai, "review")
        self.assertEqual(ai.calls, [])

    def test_same_owner_can_reenter_and_release_its_lease(self):
        self.anchor_route()
        first = self.advisor(lane="shared", owner="cli-1")
        lease = first.claim_lease()
        self.assertEqual(first.claim_lease()["lease_id"], lease["lease_id"])
        self.assertTrue(first.release_lease())
        self.assertFalse(first.release_lease())

    def test_tampered_lease_fails_closed(self):
        self.anchor_route()
        first = self.advisor(lane="shared", owner="cli-1")
        lease = first.claim_lease()
        path = first._lease_path("shared")
        tampered = json.loads(path.read_text(encoding="utf-8"))
        tampered["owner"] = "attacker"
        path.write_text(json.dumps(tampered), encoding="utf-8")
        second = self.advisor(lane="shared", owner="cli-2")
        with self.assertRaisesRegex(AdvisorError, "failed validation"):
            second.claim_lease()
        first._owns_lease = False
        self.assertNotEqual(lease["owner"], "attacker")

    def test_expired_signed_lease_can_be_reclaimed(self):
        self.anchor_route()
        first = self.advisor(lane="shared", owner="cli-1")
        lease = first.claim_lease()
        path = first._lease_path("shared")
        identity = {
            key: value
            for key, value in lease.items()
            if key not in {"signature", "lease_id"}
        }
        identity["acquired_at"] = "2019-12-31T23:59:00+00:00"
        identity["expires_at"] = "2020-01-01T00:00:00+00:00"
        replacement = {
            **identity,
            "lease_id": "lease_"
            + hashlib.sha256(bufftag._canonical_bytes(identity)).hexdigest()[:24],
            "signature": atlas._sign(identity, self.key.encode()),
        }
        path.write_text(json.dumps(replacement), encoding="utf-8")
        first._owns_lease = False
        second = self.advisor(lane="shared", owner="cli-2")
        claimed = second.claim_lease()
        self.assertEqual(claimed["owner"], "cli-2")


if __name__ == "__main__":
    unittest.main()
