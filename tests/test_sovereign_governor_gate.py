"""Governor-gate tests for the sovereign recursive engine.

`src/sovereign/recursive_engine.py` claims in its docstring:

    Security: Oracle + Governor gate every mutation. Governor --elevate required
    for write/exec/network. No clause in this loop bypasses that.

That is a trust-boundary claim, not a feature description — `AGENTS.md` §5 says a
capability declaration is not permission — so it is tested as one.

Two levels:

1. `_phase_execute`, the unit that decides. A write plan under a non-elevated
   governor must come back `blocked` with nothing applied, and must not reach the
   compile or test subprocesses at all. Not supplying a governor counts as
   non-elevated, not as permission: the engine resolves a real Governor, so the
   default outcome is deny.
2. `RecursiveEngine.cycle()`, the whole loop. Its default configuration must roll
   back, and everything it writes must land under `$HOME`, which these tests
   redirect to a temp directory. Nothing outside the repository is touched.

Why `subprocess.run` is mocked: phase 4 shells out to
`python3 -m unittest discover -s tests`. Run for real inside a test, that would
re-enter this suite and nest another copy of itself. The call count is asserted
instead, which is stronger evidence than watching it happen.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import src.skill.governor as governor_module
import src.sovereign.recursive_engine as engine

ROOT = Path(__file__).resolve().parents[1]
JOURNAL_SUFFIX = Path("logs") / "shared" / "recursive_engine" / "cycles.jsonl"


class _FakeRun:
    returncode = 0
    stdout = "Ran 181 tests\nOK"
    stderr = ""


class _FakeGovernor:
    """Mirrors `Governor.is_elevated(scope, session_id=None) -> bool`."""

    def __init__(self, elevated: bool) -> None:
        self.elevated = elevated

    def is_elevated(self, scope: str, session_id: str | None = None) -> bool:
        return bool(self.elevated)


class _InertBus:
    """Stand-in for the Whorl bus: the in-process cases must not write anywhere."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def send(self, *args, **kwargs):
        return {"inert": True}


def _execute(plan: dict, governor):
    """Run `_phase_execute` with every live side effect disabled.

    `_phase_execute` finishes by emitting a Thoth event and depositing on the Whorl
    bus. In its subprocess caller both are contained by ROOTBASE_* plus a redirected
    HOME; these cases run **in-process**, where the real `~/RootBase` and `~/.whorl`
    are reachable — which is how this file appended real `molt.recursive.execute`
    events before that was noticed. The emit and the bus dispatch are therefore
    patched out here; the subprocess cycle test is what covers them.
    """
    calls: list = []

    def fake_run(*args, **kwargs):
        calls.append(args[0] if args else None)
        return _FakeRun()

    import src.skill.whorl_bus as whorl_bus

    with mock.patch.object(engine.subprocess, "run", fake_run), mock.patch.object(
        engine, "emit_event", None
    ), mock.patch.object(whorl_bus, "WhorlBusDispatcher", _InertBus):
        result = engine._phase_execute(plan, bus=_InertBus(), governor=governor)
    return result, calls


class TestExecuteGateIsAPermissionCheck(unittest.TestCase):
    """A write plan must be gated on elevation, not on intent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.target = Path(self._tmp.name) / "target.py"
        self.original = "# original contents\nVALUE = 1\n"
        self.target.write_text(self.original, encoding="utf-8")
        self.write_plan = {
            "intent": "refactor something",
            "ops": [{"type": "edit", "file": str(self.target)}],
        }

    def test_write_plan_without_elevation_is_blocked(self):
        result, _ = _execute(self.write_plan, _FakeGovernor(elevated=False))
        self.assertEqual(result["governor_gate"], "blocked")
        self.assertEqual(result["applied"], [])
        self.assertIn("write", result["needs_elevation"])

    def test_blocked_gate_runs_no_subprocess_at_all(self):
        # The point of the gate: it returns before compiling or testing, so a
        # blocked plan cannot have any side effect at all.
        _, calls = _execute(self.write_plan, _FakeGovernor(elevated=False))
        self.assertEqual(calls, [])

    def test_elevation_still_does_not_rewrite_the_file(self):
        # Elevation changes what is *recorded*, not what is done: ops are staged
        # for a human, so the target file must stay byte-identical.
        result, _ = _execute(self.write_plan, _FakeGovernor(elevated=True))
        self.assertNotEqual(result.get("governor_gate"), "blocked")
        self.assertTrue(result["applied"], "an elevated plan should record its ops")
        for entry in result["applied"]:
            self.assertIn("staged", entry["status"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_unsupplied_governor_resolves_a_real_one_that_denies_by_default(self):
        # Passing governor=None is not "no Governor": the engine resolves a real
        # one, which is not elevated, so the default outcome is deny. Asserted
        # rather than assumed, because the opposite would be a silent bypass.
        result, _ = _execute(self.write_plan, None)
        self.assertEqual(result["governor_gate"], "blocked")
        self.assertEqual(result["applied"], [])
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_read_only_plan_needs_no_elevation(self):
        result, calls = _execute(
            {"intent": "look around", "ops": [{"type": "list_tree"}]},
            _FakeGovernor(elevated=False),
        )
        self.assertNotEqual(result.get("governor_gate"), "blocked")
        self.assertTrue(calls, "a read-only plan should proceed to compile/test")

    def test_unknown_op_types_are_recorded_not_executed(self):
        result, _ = _execute(
            {"intent": "mystery", "ops": [{"type": "summon_daemon"}]},
            _FakeGovernor(elevated=True),
        )
        self.assertEqual(result["applied"], [{"type": "summon_daemon", "status": "unknown_op"}])

    def test_fake_governor_matches_the_real_interface(self):
        # Keeps this file's fake honest: if Governor's signature moves, the gate
        # tests above would otherwise keep passing against a fiction.
        import inspect

        params = list(inspect.signature(governor_module.Governor.is_elevated).parameters)
        self.assertEqual(params[:2], ["self", "scope"])
        self.assertIsInstance(_FakeGovernor(True).is_elevated("write"), bool)
        self.assertFalse(_FakeGovernor(False).is_elevated("write"))


CYCLE_HARNESS = r'''
import json, os
from unittest import mock
import src.sovereign.recursive_engine as reg

calls = []
class FakeRun:
    returncode = 0
    stdout = "Ran 181 tests\nOK"
    stderr = ""

def fake_run(*a, **k):
    calls.append(a[0] if a else None)
    return FakeRun()

home = os.environ["HOME"]
with mock.patch.object(reg.subprocess, "run", fake_run):
    record = reg.RecursiveEngine(project_id="gate-test").cycle(
        goal="gate-test: reduce hydrate overhead", verbose=False)

files = sorted(
    os.path.relpath(os.path.join(d, f), home)
    for d, _, fs in os.walk(home) for f in fs
)
print(json.dumps({
    "home": home,
    "outcome": record.outcome,
    "gate": record.validate.get("gate"),
    "decision": record.validate.get("decision"),
    "violations": record.validate.get("violations"),
    "governor_gate": record.execute.get("governor_gate"),
    "applied": record.execute.get("applied"),
    "subprocess_calls": len(calls),
    "journal": str(reg.JOURNAL),
    "journal_lines": (
        len(reg.JOURNAL.read_text().strip().splitlines()) if reg.JOURNAL.exists() else 0
    ),
    "home_files": files[:12],
}, default=str))
'''


LIVE_BUS = Path.home() / "RootBase" / "logs" / "shared" / "agent_events.jsonl"


def _live_bus_lines() -> int | None:
    """Line count of the real bus, so a contained run can be proved not to touch it."""
    try:
        return len(LIVE_BUS.read_text(encoding="utf-8").splitlines())
    except OSError:
        return None


def _git_porcelain() -> str | None:
    if shutil.which("git") is None:
        return None
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else None


class TestCycleRollsBackByDefault(unittest.TestCase):
    """The whole loop, run with $HOME redirected so nothing leaves the repo."""

    @classmethod
    def setUpClass(cls):
        cls._home = tempfile.TemporaryDirectory()
        env = dict(os.environ)
        env["HOME"] = cls._home.name
        env["PYTHONPATH"] = str(ROOT)
        # A cycle emits to the Thoth bus, and the bus must not land in the real home.
        # The library default now follows $HOME (see tests/test_thoth_bus_location.py),
        # but these overrides keep this file contained even on a checkout where that
        # default is still the old hardcoded path -- which is how this file appended
        # real `molt.recursive.*` events to the live bus before it was noticed.
        env["ROOTBASE_DIR"] = str(Path(cls._home.name) / "RootBase")
        env["ROOTBASE_BUS_DIR"] = str(Path(cls._home.name) / "RootBase" / "logs" / "shared")
        # Same for the Whorl bus: `whorl.core.config` does not follow HOME.
        env["WHORL_HOME"] = str(Path(cls._home.name) / ".whorl")
        cls.live_bus_before = _live_bus_lines()
        cls.proc = subprocess.run(
            [sys.executable, "-c", CYCLE_HARNESS],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        cls.result = json.loads(cls.proc.stdout) if cls.proc.stdout.strip() else {}
        cls.live_bus_after = _live_bus_lines()

    @classmethod
    def tearDownClass(cls):
        cls._home.cleanup()

    def test_harness_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-2000:])

    def test_default_cycle_rolls_back(self):
        self.assertEqual(self.result.get("outcome"), "rolled_back")
        self.assertEqual(self.result.get("gate"), "HOLD")

    def test_the_reason_is_the_missing_governor_elevation(self):
        self.assertEqual(self.result.get("governor_gate"), "blocked")
        violations = self.result.get("violations") or []
        self.assertTrue(
            any("governor_blocked" in v for v in violations),
            f"expected a governor_blocked violation, got {violations}",
        )

    def test_nothing_was_applied_and_nothing_was_executed(self):
        self.assertEqual(self.result.get("applied"), [])
        self.assertEqual(self.result.get("subprocess_calls"), 0)

    def test_the_cycle_is_journalled_under_the_redirected_home(self):
        home = self.result.get("home", "")
        self.assertTrue(home and Path(home).is_dir())
        self.assertTrue(
            self.result.get("journal", "").startswith(home),
            "the journal escaped the redirected HOME",
        )
        self.assertEqual(self.result.get("journal_lines"), 1)
        self.assertTrue(
            any(f.endswith(str(JOURNAL_SUFFIX)) for f in self.result.get("home_files", [])),
            f"journal not found under HOME: {self.result.get('home_files')}",
        )

    def test_running_a_cycle_does_not_append_to_the_live_bus(self):
        self.assertEqual(
            self.live_bus_before,
            self.live_bus_after,
            f"the live bus moved during a contained run: {LIVE_BUS}",
        )

    def test_running_a_cycle_does_not_touch_the_worktree(self):
        before = _git_porcelain()
        if before is None:
            self.skipTest("git unavailable, cannot compare the worktree")
        self.assertEqual(before, _git_porcelain())


if __name__ == "__main__":
    unittest.main()
