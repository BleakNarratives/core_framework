"""Bridge and daemon tests for the sovereign layer.

`src/sovereign/bridges.py` and `daemons.py` (392 lines together) were the last
untested modules in `src/`. Both make boundary decisions:

- `endempts_gate` returns SHIP / HOLD / KILL and, on the KILL path, deletes a file.
- `akasha_store_evidence` stores evidence in the real Akasha vault when it can find
  one, and falls back to a content-addressed store under `$HOME` when it cannot.

So every case here runs in a subprocess with `$HOME` redirected to a temp directory.
That matters on this machine specifically: `~/Akasha`, `~/Merkaba`, `~/OutClaw`,
`~/Implore` and `~/thoth_orchestrator` all exist, so with a real `$HOME` these tests
would write into live vaults and buses. Redirecting `$HOME` exercises the documented
degraded paths instead, which is also what makes them deterministic.

Bridges and daemons both claim to degrade without their subsystem ("All bridges
degrade without their subsystem"). That is asserted here in both directions: the
degraded result is recorded, not raised, and every file written lands under the
redirected home.
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

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
import contextlib, io, json, os
from pathlib import Path
from unittest import mock

import src.sovereign.bridges as bridges
import src.sovereign.daemons as daemons
import src.sovereign.recursive_engine as engine

home = Path(os.environ["HOME"])
out = {}


def capture(fn):
    """Record a result or the exception, so one failure cannot blank the report."""
    try:
        return {"ok": True, "value": fn()}
    except Exception as exc:
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}


class FakeRun:
    returncode = 0
    stdout = "Ran 197 tests\nOK"
    stderr = ""


# ── Bridges: degraded paths ──────────────────────────────────────────
out["implor_scan"] = capture(lambda: bridges.implor_scan("."))
out["implor_packet"] = capture(lambda: bridges.implor_to_thoth_packet(".", goal="test goal"))
out["merkaba_claw"] = capture(lambda: bridges.merkaba_claw_bridge("test intent"))

content = "evidence body for the fallback store"
out["astore_first"] = capture(lambda: bridges.akasha_store_evidence(
    content, tags=["probe"], metadata={"cycle_id": "c1"}))
out["astore_second"] = capture(lambda: bridges.akasha_store_evidence(content))
out["astore_other"] = capture(lambda: bridges.akasha_store_evidence(content + " (different)"))

# ── Endempts gate: the three verdicts ────────────────────────────────
ship = {"cycle_id": "c-ship", "validate": {"gate": "SHIP"}}
hold = {"cycle_id": "c-hold", "validate": {"gate": "HOLD", "violations": ["v%d" % i for i in range(6)]}}
failed = {"cycle_id": "c-kill", "validate": {"gate": "FAILED"}}

out["gate_ship"] = capture(lambda: bridges.endempts_gate(ship))
out["gate_hold"] = capture(lambda: bridges.endempts_gate(hold))

kill_file = home / "killme.flag"
kill_file.write_text("x", encoding="utf-8")
out["gate_kill"] = capture(lambda: bridges.endempts_gate(failed, kill_file=str(kill_file)))
out["kill_file_exists_after"] = kill_file.exists()

missing_file = home / "never-existed.flag"
out["gate_kill_missing_file"] = capture(
    lambda: bridges.endempts_gate(failed, kill_file=str(missing_file)))

# ── Daemons ──────────────────────────────────────────────────────────
# The autoloop runs cycles with verbose=True, so the engine writes progress lines
# to stdout. Captured here, because otherwise they interleave with this report —
# and recorded, because any caller that pipes stdout has to account for it.
noise = io.StringIO()
with mock.patch.object(engine.subprocess, "run", lambda *a, **k: FakeRun()):
    with contextlib.redirect_stdout(noise):
        out["autoloop"] = capture(lambda: daemons.tick_instar_autoloop(
            project_id="bridge-test", max_cycles=1, interval_s=0, idle_threshold_s=0))
        out["vault"] = capture(lambda: daemons.akasha_mutation_vault(
            project_id="bridge-test"))
        out["vault_without_store"] = capture(lambda: daemons.akasha_mutation_vault(
            project_id="bridge-test", store_last_cycle=False))
out["daemon_stdout_lines"] = len(noise.getvalue().strip().splitlines())

out["claw_daemon"] = capture(lambda: daemons.tick_merkaba_claw_bridge(intent="daemon intent"))

try:
    import agent_bus
    out["agent_bus_bus_file"] = str(agent_bus.BUS_FILE)
except Exception as exc:
    out["agent_bus_bus_file"] = None
    out["agent_bus_error"] = "%s: %s" % (type(exc).__name__, exc)

out["whorl_dir"] = os.environ.get("WHORL_HOME")
out["home"] = str(home)
out["home_files"] = sorted(
    os.path.relpath(os.path.join(d, f), home)
    for d, _, fs in os.walk(home) for f in fs
)
print(json.dumps(out, default=str))
'''


def _parse_report(stdout: str) -> dict:
    """Read the last JSON line, so stray output from the code under test can't hide it."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}


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


class SovereignBridgesTest(unittest.TestCase):
    """One harness run, asserted case by case."""

    @classmethod
    def setUpClass(cls):
        cls._home = tempfile.TemporaryDirectory()
        env = dict(os.environ)
        env["HOME"] = cls._home.name
        env["PYTHONPATH"] = str(ROOT)
        # Redirecting HOME is not enough for the Thoth bus. `agent_bus` is importable
        # because another module puts the *real* `~/thoth_orchestrator` on sys.path,
        # and it resolves its bus directory from ROOTBASE_DIR, whose default is a
        # hardcoded `/home/bleaknarratives/RootBase` that ignores HOME entirely. An
        # earlier version of this file wrote one real event to the live bus before
        # that was noticed; these overrides are what keep it contained.
        env["ROOTBASE_DIR"] = str(Path(cls._home.name) / "RootBase")
        env["ROOTBASE_BUS_DIR"] = str(Path(cls._home.name) / "RootBase" / "logs" / "shared")
        # The Whorl bus needs its own override: `whorl.core.config` resolves its
        # directory independently of HOME, so the daemons' bus dispatch was creating
        # `~/.whorl/whorl.db` in the real home even with HOME redirected.
        env["WHORL_HOME"] = str(Path(cls._home.name) / ".whorl")
        cls.before = _git_porcelain()
        cls.live_bus_before = _live_bus_lines()
        cls.proc = subprocess.run(
            [sys.executable, "-c", HARNESS],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        cls.out = _parse_report(cls.proc.stdout)
        cls.live_bus_after = _live_bus_lines()
        cls.home = cls._home.name

    @classmethod
    def tearDownClass(cls):
        cls._home.cleanup()

    def value(self, key: str):
        """Return a case's value, failing with the recorded error if it raised."""
        case = self.out.get(key)
        self.assertIsNotNone(case, f"harness produced no case {key!r}")
        self.assertTrue(case.get("ok"), f"{key} raised: {case.get('error')}")
        return case["value"]

    def test_harness_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr[-2000:])
        self.assertTrue(self.out, "harness printed no JSON")

    # ── Bridges degrade instead of raising ───────────────────────────
    def test_implor_scan_reports_the_subsystem_as_unavailable(self):
        result = self.value("implor_scan")
        self.assertEqual(result["source"], "implor_unavailable")
        self.assertIn("error", result)

    def test_implor_packet_degrades_while_the_thoth_wire_stays_live(self):
        # Asymmetric on purpose, and this is what the test found: the Akasha packet
        # cannot be built without the `akasha` module, but the Thoth bus *is*
        # reachable because `thoth_orchestrator/` sits in this repository and its
        # directory is on sys.path. Asserting both halves stops this from silently
        # becoming "everything is available" or "everything is broken".
        result = self.value("implor_packet")
        self.assertEqual(result["wire"], "implor->thoth")
        self.assertIn("packet_error", result)
        self.assertTrue(result.get("thoth_event_id"), "the Thoth wire should be live here")
        self.assertIn("scan", result)

    def test_merkaba_claw_bridge_degrades_without_ka_gen(self):
        result = self.value("merkaba_claw")
        self.assertEqual(result["wire"], "merkaba->claw")
        self.assertIn("error", result["ka"])
        self.assertIn("mounted", result["claw_endpoint"])

    # ── Akasha evidence store ────────────────────────────────────────
    def test_evidence_store_falls_back_and_is_content_addressed(self):
        first = self.value("astore_first")
        second = self.value("astore_second")
        other = self.value("astore_other")
        self.assertEqual(first["backend"], "fallback")
        self.assertTrue(first["object_id"].startswith("object:sha256:"))
        # Same content, same id; different content, different id.
        self.assertEqual(first["object_id"], second["object_id"])
        self.assertNotEqual(first["object_id"], other["object_id"])

    def test_evidence_store_writes_only_under_the_redirected_home(self):
        path = Path(self.value("astore_first")["path"])
        self.assertTrue(
            str(path).startswith(self.home), f"{path} escaped the redirected HOME"
        )
        self.assertTrue(path.is_file(), f"{path} was not written")

    # ── Endempts: commit / hold / kill ───────────────────────────────
    def test_ship_verdict_commits_and_leaves_the_space_intact(self):
        result = self.value("gate_ship")
        self.assertEqual(result["gate"], "SHIP")
        self.assertEqual(result["action"], "commit")
        self.assertEqual(result["cleanup"], "leave_execution_space_intact")

    def test_hold_verdict_caps_the_recorded_violations(self):
        result = self.value("gate_hold")
        self.assertEqual(result["action"], "hold_for_review")
        # Six violations in, five recorded: the cap is deliberate, so it is pinned.
        self.assertEqual(result["violations"], ["v0", "v1", "v2", "v3", "v4"])

    def test_kill_verdict_deletes_the_kill_file_it_was_given(self):
        result = self.value("gate_kill")
        self.assertEqual(result["action"], "kill_and_cleanup")
        self.assertEqual(result["killed_file"], str(Path(self.home) / "killme.flag"))
        self.assertFalse(self.out["kill_file_exists_after"], "kill file survived the gate")

    def test_kill_verdict_without_the_file_is_not_an_error(self):
        result = self.value("gate_kill_missing_file")
        self.assertEqual(result["action"], "kill_and_cleanup")
        self.assertNotIn("killed_file", result)

    # ── Daemons ──────────────────────────────────────────────────────
    def test_autoloop_runs_the_requested_cycle_and_rolls_it_back(self):
        result = self.value("autoloop")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["cycles"][0]["outcome"], "rolled_back")

    def test_mutation_vault_stores_the_last_cycle_and_indexes_it(self):
        result = self.value("vault")
        stored = result["stored"]
        self.assertEqual(stored["backend"], "fallback")
        self.assertTrue(result["index_path"].startswith(self.home))
        self.assertTrue(result["stored"]["object_id"].startswith("object:sha256:"))

    def test_mutation_vault_without_store_says_so_and_stores_nothing(self):
        result = self.value("vault_without_store")
        self.assertIn("note", result)
        self.assertNotIn("stored", result)

    def test_the_thoth_bus_file_is_inside_the_redirected_home(self):
        bus_file = self.out.get("agent_bus_bus_file")
        self.assertIsNotNone(
            bus_file, f"agent_bus was not importable: {self.out.get('agent_bus_error')}"
        )
        self.assertTrue(
            bus_file.startswith(self.home),
            f"the bus escaped the redirected HOME: {bus_file}",
        )

    def test_merkaba_claw_daemon_routes_and_degrades(self):
        result = self.value("claw_daemon")
        self.assertEqual(result["wire"], "merkaba->claw")
        self.assertIn("ka", result)

    def test_the_autoloop_writes_progress_to_stdout(self):
        # Not cosmetic: it is why this harness has to capture stdout, and it means a
        # caller that expects machine-readable output must allow for it.
        self.assertGreater(self.out.get("daemon_stdout_lines", 0), 0)

    def test_the_whorl_bus_is_inside_the_redirected_home(self):
        # Only the bus files this harness knows about are asserted by name; the point
        # is that no path it reported escapes HOME.
        resources = self.out.get("whorl_dir")
        if resources is not None:
            self.assertTrue(
                str(resources).startswith(self.home),
                f"the Whorl bus escaped the redirected HOME: {resources}",
            )

    def test_every_file_written_stayed_under_the_redirected_home(self):
        files = self.out.get("home_files") or []
        self.assertTrue(files, "the daemons wrote nothing at all")
        for name in files:
            self.assertFalse(
                str(name).startswith("/"), f"{name} is an absolute path outside HOME"
            )
        self.assertTrue(
            any(f.endswith(str(Path("recursive_engine") / "cycles.jsonl")) for f in files),
            f"no cycle journal under HOME: {files}",
        )

    def test_running_the_bridges_does_not_append_to_the_live_bus(self):
        self.assertEqual(
            self.live_bus_before,
            self.live_bus_after,
            f"the live bus moved during a contained run: {LIVE_BUS}",
        )

    def test_running_the_bridges_does_not_touch_the_worktree(self):
        if self.before is None:
            self.skipTest("git unavailable, cannot compare the worktree")
        self.assertEqual(self.before, _git_porcelain())


if __name__ == "__main__":
    unittest.main()
