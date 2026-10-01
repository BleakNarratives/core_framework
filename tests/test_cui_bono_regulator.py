"""Offline tests for the Cui Bono Regulator.

The regulator is pure, so these are deterministic: no network, no git, no
filesystem. Observed state (dirty tree, tests touched) is passed in explicitly,
exactly as a caller would.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.guard import cui_bono_regulator as cbr
from tools.guard.cui_bono_regulator import (
    ALLOW,
    BLOCK,
    REDIRECT,
    CuiBonoVerdict,
    evaluate,
    evaluate_pre_execution,
)


class TestCuiBonoRegulator(unittest.TestCase):
    def test_irreversible_low_utility_is_blocked(self):
        v = evaluate({"command": "git reset --hard HEAD~3", "uncommitted_state": True})
        self.assertEqual(v.verdict, BLOCK)
        self.assertFalse(v.allowed)
        self.assertIsNotNone(v.redirect_action)
        self.assertIn("hard reset", " ".join(v.reasoning))

    def test_forced_delete_without_goal_is_blocked(self):
        v = evaluate("rm -rf src/")
        self.assertEqual(v.verdict, BLOCK)
        self.assertIsInstance(v, CuiBonoVerdict)

    def test_risky_but_goal_serving_is_redirected(self):
        v = evaluate({"command": "git push origin main --force", "goal": "publish the gate"})
        self.assertEqual(v.verdict, REDIRECT)
        self.assertEqual(v.redirect_action, "git push --force-with-lease")

    def test_read_only_command_is_allowed(self):
        v = evaluate({"command": "git status --short", "goal": "check tree state"})
        self.assertEqual(v.verdict, ALLOW)
        self.assertTrue(v.allowed)
        self.assertIsNone(v.redirect_action)

    def test_running_tests_is_allowed(self):
        # Running the suite must not be penalised — only *changing* covered
        # behaviour is risky.
        v = evaluate({"command": "python -m pytest tests/ -q", "goal": "confirm green"})
        self.assertEqual(v.verdict, ALLOW)

    def test_modifying_covered_behaviour_is_redirected(self):
        v = evaluate({"command": "rewrite tests/test_core.py assertions",
                      "goal": "fix a flake"}, touches_tests=True)
        self.assertIn(v.verdict, (REDIRECT, BLOCK))

    def test_drift_language_is_redirected_to_restate_goal(self):
        v = evaluate("refactor everything while we're at it")
        self.assertEqual(v.verdict, REDIRECT)
        self.assertIn("restate", v.redirect_action or "")

    def test_human_approval_reduces_risk_below_block(self):
        blocked = evaluate({"command": "git clean -fd", "uncommitted_state": True})
        approved = evaluate({"command": "git clean -fd", "uncommitted_state": True,
                             "goal": "reset the scratch tree", "human_approval": True})
        self.assertLess(approved.risk, blocked.risk)
        self.assertNotEqual(approved.verdict, BLOCK)

    def test_verdict_contract_shape(self):
        d = evaluate({"command": "ls", "goal": "look"}).to_dict()
        self.assertEqual(set(d),
                         {"verdict", "reasoning", "redirect_action", "utility", "risk"})
        self.assertIsInstance(d["reasoning"], list)
        self.assertLessEqual(d["utility"], 1.0)
        self.assertLessEqual(d["risk"], 1.0)

    def test_bad_payload_type_is_rejected(self):
        with self.assertRaises(TypeError):
            evaluate(123)

    # ── pre-execution composition with Tribunal ──────────────────

    def test_pre_execution_composes_tribunal_block(self):
        tf = {"should_block": True, "risk_level": "critical",
              "issues": [{"message": "DANGER: rm -rf /"}]}
        with patch.object(cbr, "_tribunal_preflight", return_value=tf):
            v = evaluate_pre_execution({"command": "do the thing", "goal": "ship"})
        self.assertEqual(v.verdict, BLOCK)
        self.assertIn("tribunal", " ".join(v.reasoning).lower())

    def test_pre_execution_downgrades_on_elevated_tribunal_risk(self):
        tf = {"should_block": False, "risk_level": "high",
              "issues": [{"message": "WARNING: force push"}]}
        with patch.object(cbr, "_tribunal_preflight", return_value=tf):
            v = evaluate_pre_execution({"command": "git status", "goal": "check"})
        self.assertEqual(v.verdict, REDIRECT)

    def test_pre_execution_falls_back_when_tribunal_absent(self):
        with patch.object(cbr, "_tribunal_preflight", return_value=None):
            v = evaluate_pre_execution({"command": "git status", "goal": "check"})
        self.assertEqual(v.verdict, ALLOW)


if __name__ == "__main__":
    unittest.main()
