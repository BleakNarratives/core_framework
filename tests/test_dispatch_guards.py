"""Dispatch-guard tests: DuplicateCallGuard, SingleCheckRule, bus dedupe
wiring, and the loom context-slice cap.

These guards were salvaged from an external proposal (see
docs/DISPATCH_GUARDS_SPEC.md). The proposal's own dedupe middleware swallowed
tool calls silently; the repo invariants these tests enforce instead are:

1. Nothing is suppressed silently — every flagged/blocked verdict lands in an
   audit log, and a blocked bus send is recorded in the bus log.
2. Detection is bounded — the window expires and tracked signatures are capped.
3. The single-check rule is digest-scoped: a changed subject re-opens the check.
4. Worker dispatch payloads are bounded; truncation is recorded, not hidden.
5. With no guard configured, dispatch behavior is unchanged.

Offline and temp-dir isolated: WHORL_HOME points at a temp directory before any
`src.` import (mirroring tests/test_molt_triad.py), and every audit path is
explicit. No network, no live bus.

`src.` / `whorl` imports happen lazily inside setUp, never at module level:
unittest discover loads every test module before running any test, and a
module-level `import whorl.*` binds the top-level `whorl` namespace before
tests/test_judo_stego.py gets its own `Whorl/` sys.path entry in, breaking its
import (measured: 425-test suite run, 1 error, before this deferral).
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Contain the Whorl bus for this module (see tests/test_molt_triad.py):
# whorl.core.config resolves the directory at import time, so this must be set
# before any `src.` import below. setdefault keeps an explicit WHORL_HOME.
_WHORL_TMP = tempfile.TemporaryDirectory(prefix="dispatch-guards-whorl-")
os.environ.setdefault("WHORL_HOME", _WHORL_TMP.name)


class _FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _audit_events(path: str):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


class TestDuplicateCallGuard(unittest.TestCase):
    def setUp(self):
        from src.skill.governor import DuplicateCallGuard
        self.Guard = DuplicateCallGuard
        self.tmp = tempfile.mkdtemp()
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.clock = _FakeClock()

    def _guard(self, **kw):
        kw.setdefault("audit_path", self.audit)
        kw.setdefault("clock", self.clock)
        return self.Guard(**kw)

    def test_first_call_is_allowed_and_not_audited(self):
        g = self._guard()
        v = g.check("sig-a")
        self.assertEqual(v["action"], "allow")
        self.assertFalse(v["duplicate"])
        self.assertEqual(_audit_events(self.audit), [])

    def test_repeat_is_flagged_by_default_and_audited(self):
        g = self._guard()  # default action_on_loop="flag"
        g.check("sig-a")
        v = g.check("sig-a")
        self.assertTrue(v["duplicate"])
        self.assertEqual(v["action"], "flag")
        self.assertEqual(v["count"], 2)
        events = _audit_events(self.audit)
        self.assertEqual([e["event"] for e in events], ["duplicate_call_flagged"])

    def test_flag_mode_never_blocks_even_far_beyond_tolerance(self):
        g = self._guard(max_duplicates=0)
        for _ in range(5):
            v = g.check("sig-a")
        self.assertEqual(v["action"], "flag")
        self.assertTrue(v["exceeded"])

    def test_block_mode_blocks_only_after_tolerance(self):
        g = self._guard(action_on_loop="block")
        self.assertEqual(g.check("sig-a")["action"], "allow")
        self.assertEqual(g.check("sig-a")["action"], "flag")   # within tolerance
        v = g.check("sig-a")                                    # beyond tolerance
        self.assertEqual(v["action"], "block")
        self.assertTrue(v["exceeded"])
        events = [e["event"] for e in _audit_events(self.audit)]
        self.assertIn("duplicate_call_blocked", events)

    def test_window_expiry_resets_the_count(self):
        g = self._guard(window_s=30)
        g.check("sig-a")
        self.clock.advance(31)
        v = g.check("sig-a")
        self.assertEqual(v["action"], "allow")
        self.assertEqual(v["count"], 1)

    def test_distinct_signatures_are_independent(self):
        g = self._guard()
        g.check("sig-a")
        v = g.check("sig-b")
        self.assertEqual(v["action"], "allow")
        # a repeat of sig-a is still the second occurrence of sig-a
        self.assertEqual(g.check("sig-a")["count"], 2)

    def test_tracked_signatures_are_capped(self):
        g = self._guard()
        for i in range(g.MAX_SIGNATURES + 50):
            g.check(f"sig-{i}")
        self.assertLessEqual(g.tracked_signatures(), g.MAX_SIGNATURES)

    def test_bad_parameters_rejected(self):
        with self.assertRaises(ValueError):
            self.Guard(action_on_loop="silently_swallow")
        with self.assertRaises(ValueError):
            self.Guard(window_s=0)
        with self.assertRaises(ValueError):
            self.Guard(max_duplicates=-1)


class TestSingleCheckRule(unittest.TestCase):
    def setUp(self):
        from src.skill.governor import SingleCheckRule
        self.tmp = tempfile.mkdtemp()
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self.clock = _FakeClock()
        self.rule = SingleCheckRule(audit_path=self.audit, clock=self.clock)

    def test_first_check_runs(self):
        v = self.rule.should_run("pytest", "digest-1")
        self.assertTrue(v["run"])
        self.assertEqual(v["reason"], "first_check")

    def test_identical_recheck_is_flagged_not_run(self):
        self.rule.should_run("pytest", "digest-1")
        v = self.rule.should_run("pytest", "digest-1")
        self.assertFalse(v["run"])
        self.assertEqual(v["reason"], "identical_check_on_identical_state")
        self.assertEqual([e["event"] for e in _audit_events(self.audit)],
                         ["recheck_flagged"])

    def test_changed_subject_reopens_the_check(self):
        self.rule.should_run("pytest", "digest-1")
        v = self.rule.should_run("pytest", "digest-2")
        self.assertTrue(v["run"])
        self.assertEqual(v["reason"], "subject_changed")

    def test_ttl_elapsed_reopens_the_check(self):
        self.rule.should_run("pytest", "digest-1")
        self.clock.advance(self.rule.ttl_s + 1)
        v = self.rule.should_run("pytest", "digest-1")
        self.assertTrue(v["run"])
        self.assertEqual(v["reason"], "ttl_elapsed")

    def test_unscoped_checks_are_still_bounded_to_one(self):
        self.assertTrue(self.rule.should_run("pytest")["run"])
        self.assertFalse(self.rule.should_run("pytest")["run"])

    def test_record_result_is_audited(self):
        self.rule.record_result("pytest", "digest-1", result="OK 12 tests")
        events = _audit_events(self.audit)
        self.assertEqual(events[0]["event"], "verification_check")
        self.assertEqual(events[0]["result"], "OK 12 tests")


class _RecordingBus:
    def __init__(self):
        self.dispatched = []

    def send_molt_hydrate(self, skill, hydrated, oomf_level=3, recipients=None):
        pass

    def dispatch_task(self, recipient, task_id, prompt, **kwargs):
        self.dispatched.append({"recipient": recipient, "task_id": task_id,
                                "prompt": prompt, **kwargs})


class _StubSkillManager:
    def hydrate(self, skill, oomf_level=3, max_chars=6000):
        return f"hydrated:{skill}"


class TestBusDedupeIntegration(unittest.TestCase):
    """The guard wired into WhorlBusDispatcher, exercised on the filesystem
    fallback so inbox delivery can be counted exactly."""

    def setUp(self):
        import src.skill.whorl_bus as whorl_bus_module
        self.wb = whorl_bus_module
        self.tmp = tempfile.mkdtemp()
        self._old_home = os.environ.get("WHORL_HOME")
        os.environ["WHORL_HOME"] = self.tmp
        self.audit = os.path.join(self.tmp, "audit.jsonl")
        self._patches = [
            mock.patch.object(self.wb, "_HAS_WHORL_BUS", False),
            mock.patch.object(self.wb, "_whorl_bus", None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        if self._old_home is None:
            os.environ.pop("WHORL_HOME", None)
        else:
            os.environ["WHORL_HOME"] = self._old_home

    def _bus(self, guard=None):
        bus = self.wb.WhorlBusDispatcher(agent_name="tester", auto_register=False,
                                         dedupe_guard=guard)
        bus.ensure_recipient("worker")
        return bus

    def _inbox_count(self):
        inbox = Path(self.tmp) / "bus" / "inbox" / "worker"
        return len(list(inbox.glob("*.json"))) if inbox.exists() else 0

    def _send_three(self, bus):
        outs = []
        for _ in range(3):
            outs.append(bus.send("worker", "task.dispatch",
                                 {"task_id": "T1", "prompt": "do the thing"}))
        return outs

    def test_no_guard_delivers_all_three(self):
        outs = self._send_three(self._bus())
        self.assertEqual(self._inbox_count(), 3)
        self.assertFalse(any(o.get("dedup_blocked") for o in outs))

    def test_flag_guard_still_delivers_but_audits(self):
        from src.skill.governor import DuplicateCallGuard
        guard = DuplicateCallGuard(action_on_loop="flag", audit_path=self.audit)
        self._send_three(self._bus(guard))
        self.assertEqual(self._inbox_count(), 3)  # flagged, not dropped
        flagged = [e for e in _audit_events(self.audit)
                   if e["event"] == "duplicate_call_flagged"]
        self.assertGreaterEqual(len(flagged), 2)

    def test_block_guard_delivers_two_and_audits_the_drop(self):
        from src.skill.governor import DuplicateCallGuard
        guard = DuplicateCallGuard(action_on_loop="block", audit_path=self.audit)
        outs = self._send_three(self._bus(guard))
        self.assertEqual(self._inbox_count(), 2)  # third was blocked
        self.assertTrue(outs[-1]["dedup_blocked"])
        self.assertTrue(outs[-1]["dedup"]["exceeded"])
        # Both audit trails record it: guard audit + bus log.
        blocked = [e for e in _audit_events(self.audit)
                   if e["event"] == "duplicate_call_blocked"]
        self.assertEqual(len(blocked), 1)
        bus_log = Path(self.tmp) / "bus" / "log" / "bus.jsonl"
        events = [json.loads(l)["event"] for l in bus_log.read_text().splitlines() if l.strip()]
        self.assertIn("message_dedup_blocked", events)

    def test_distinct_payloads_are_not_duplicates(self):
        from src.skill.governor import DuplicateCallGuard
        guard = DuplicateCallGuard(action_on_loop="block", audit_path=self.audit)
        bus = self._bus(guard)
        bus.send("worker", "task.dispatch", {"task_id": "T1", "prompt": "one"})
        bus.send("worker", "task.dispatch", {"task_id": "T2", "prompt": "two"})
        self.assertEqual(self._inbox_count(), 2)


class TestLoomSliceCap(unittest.TestCase):
    def setUp(self):
        import src.skill.loom_weaver as loom_module
        from src.skill.loom_weaver import LoomThreadWeaver
        self.loom = loom_module
        self.Weaver = LoomThreadWeaver
        self.tmp = tempfile.mkdtemp()
        self._loom_dir_patch = mock.patch.object(
            self.loom, "LOOM_DIR", Path(self.tmp) / "loom")
        self._skill_patch = mock.patch(
            "src.skill.skill_manager.SkillManager", _StubSkillManager)
        self._loom_dir_patch.start()
        self._skill_patch.start()

    def tearDown(self):
        self._skill_patch.stop()
        self._loom_dir_patch.stop()

    def test_long_prompt_is_sliced_and_truncation_recorded(self):
        bus = _RecordingBus()
        weaver = self.Weaver(bus=bus, snapshotter=object(),
                             context_slice_limit=100)
        rec = weaver.weave(steps=[{"skill": "s", "prompt": "x" * 500}])
        self.assertEqual(len(bus.dispatched[0]["prompt"]), 100)
        trunc = rec["traces"][0]["prompt_truncated"]
        self.assertEqual(trunc["original_chars"], 500)
        self.assertEqual(trunc["dispatched_chars"], 100)

    def test_short_prompt_passes_untouched(self):
        bus = _RecordingBus()
        weaver = self.Weaver(bus=bus, snapshotter=object(),
                             context_slice_limit=100)
        rec = weaver.weave(steps=[{"skill": "s", "prompt": "short"}])
        self.assertEqual(bus.dispatched[0]["prompt"], "short")
        self.assertNotIn("prompt_truncated", rec["traces"][0])

    def test_default_limit_matches_spec(self):
        weaver = self.Weaver(bus=_RecordingBus(), snapshotter=object())
        self.assertEqual(weaver.context_slice_limit, 32000)
        self.assertEqual(self.Weaver.CONTEXT_SLICE_LIMIT, 32000)


if __name__ == "__main__":
    unittest.main()
