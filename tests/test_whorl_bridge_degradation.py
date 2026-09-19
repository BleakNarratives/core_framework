"""Offline tests for the polyglot bridge's import-time degradation claim.

`src/skill/whorl_polyglot_bridge.py` promises in its docstring: *"Zero-network,
zero-bloat. Degrades gracefully if Whorl/MOLT missing."* That is an import-time
property, so it is tested as one — by importing the module in a subprocess where
`src.skill.*` genuinely cannot be imported, not by inspecting the try/except.

Two directions are asserted, because only testing one would pass against a flag
that is simply hardcoded:

1. **Absent.** `HAS_MOLT` is False, and the stub bus/manager that stand in for
   Whorl are usable: the stub covers the five methods the bridge dispatches
   through, and its frontmatter parser returns the declared keys.
2. **Present.** With the repository importable, `HAS_MOLT` is True and the real
   dispatcher is bound, so the flag reflects reality rather than a constant.

Loader note, because it costs an hour otherwise: a module loaded via
`spec_from_file_location` **must be registered in `sys.modules` before
`exec_module`**. `dataclasses` resolves `sys.modules[cls.__module__]` when
checking for the `KW_ONLY` sentinel, so an unregistered module dies at the first
module-level `@dataclass` with
`AttributeError: 'NoneType' object has no attribute '__dict__'` — which looks
like a defect in the module being loaded and is not.
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
BRIDGE_PATH = ROOT / "src" / "skill" / "whorl_polyglot_bridge.py"

# The five bus entrypoints the bridge dispatches through. If the stub loses one,
# a MOLT-less run fails at call time instead of at import time.
BUS_METHODS = ("send", "send_sidecar", "send_mutation", "send_molt_hydrate", "status")

FRONTMATTER_DOC = "---\nskill_id: x\nversion: 1.0\n---\nbody text\n"

HARNESS_DEGRADED = r'''
import importlib.util, json, os, pathlib, sys

path = pathlib.Path(sys.argv[1])
name = "whorl_polyglot_bridge_under_test"
spec = importlib.util.spec_from_file_location(name, path)
assert spec and spec.loader, "could not build a module spec"
module = importlib.util.module_from_spec(spec)
sys.modules[name] = module  # required before exec; see this file's docstring
result = {"sys_path_has_repo": any(str(pathlib.Path(sys.argv[2])) == p for p in sys.path)}
try:
    spec.loader.exec_module(module)
except Exception as exc:  # a failure here is the bug the test is looking for
    result["import_error"] = "%s: %s" % (type(exc).__name__, exc)
else:
    result["import_error"] = None
    result["has_molt"] = module.HAS_MOLT
    bus = module.WhorlBusDispatcher(agent_name="probe")
    result["dispatcher_name"] = type(bus).__name__
    result["bus_methods"] = sorted(
        m for m in os.environ["BUS_METHODS"].split(",")
        if callable(getattr(bus, m, None))
    )
    result["send_return"] = bus.send("topic", key="value")
    result["status_return"] = bus.status()
    result["sidecar_is_send"] = bus.send_sidecar("t") == bus.send("t")
    result["hydrate_is_list"] = isinstance(bus.send_molt_hydrate("hy"), list)
    manager = module.SkillManager()
    result["frontmatter"] = manager.parse_frontmatter(pathlib.Path(os.environ["FM_PATH"]))
    result["body_return"] = manager.body()
print(json.dumps(result, default=str))
'''

HARNESS_PRESENT = r'''
import json
import src.skill.whorl_polyglot_bridge as bridge
print(json.dumps({
    "has_molt": bridge.HAS_MOLT,
    "dispatcher_name": bridge.WhorlBusDispatcher.__name__,
}))
'''


def _run(script: str, cwd: Path, args: list[str], env_extra: dict | None = None):
    """Run a harness script, with PYTHONPATH stripped so imports are honest."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["BUS_METHODS"] = ",".join(BUS_METHODS)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _git_porcelain() -> str | None:
    if shutil.which("git") is None:
        return None
    proc = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else None


class TestDegradedImportWithoutWhorl(unittest.TestCase):
    """The claim: the module imports when Whorl/MOLT cannot be imported."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        (cls.tmp / "scout.md").write_text(FRONTMATTER_DOC, encoding="utf-8")
        cls.before = sorted(p.name for p in cls.tmp.iterdir())
        cls.proc = _run(
            HARNESS_DEGRADED,
            cwd=cls.tmp,
            args=[str(BRIDGE_PATH), str(ROOT)],
            env_extra={"FM_PATH": str(cls.tmp / "scout.md")},
        )
        cls.result = json.loads(cls.proc.stdout) if cls.proc.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_subprocess_ran_clean_the_repo_is_not_on_sys_path(self):
        # Guards the premise: if the repo were importable, "absent" would be a lie.
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertFalse(
            self.result.get("sys_path_has_repo"),
            "repo root leaked onto sys.path — this is no longer a MOLT-absent run",
        )

    def test_import_succeeds_with_whorl_missing(self):
        self.assertIsNone(
            self.result.get("import_error"),
            f"import failed with Whorl absent: {self.result.get('import_error')}",
        )
        self.assertFalse(self.result.get("has_molt"))

    def test_stub_dispatcher_replaces_the_real_one(self):
        self.assertEqual(self.result.get("dispatcher_name"), "_StubBus")

    def test_stub_covers_every_bus_method_the_bridge_calls(self):
        self.assertEqual(self.result.get("bus_methods"), sorted(BUS_METHODS))

    def test_stub_send_returns_a_recordable_marker(self):
        sent = self.result.get("send_return")
        self.assertIsInstance(sent, dict)
        self.assertTrue(sent.get("stub"))

    def test_stub_status_reports_itself(self):
        self.assertEqual(self.result.get("status_return"), {"stub": True})

    def test_stub_sidecar_and_hydrate_delegate_to_send(self):
        self.assertTrue(self.result.get("sidecar_is_send"))
        self.assertTrue(self.result.get("hydrate_is_list"))

    def test_stub_manager_parses_declared_frontmatter_keys(self):
        parsed = self.result.get("frontmatter")
        self.assertIsInstance(parsed, dict)
        self.assertEqual(sorted(parsed), ["skill_id", "version"])
        self.assertEqual(str(parsed["skill_id"]), "x")
        self.assertTrue(str(parsed["version"]).startswith("1.0"))

    def test_stub_manager_body_is_an_empty_string(self):
        self.assertEqual(self.result.get("body_return"), "")

    def test_degraded_import_writes_nothing_next_to_the_caller(self):
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), self.before)


class TestRealImportWhenWhorlIsPresent(unittest.TestCase):
    """The other direction: the flag must be able to be True."""

    def test_has_molt_is_true_and_the_real_dispatcher_is_bound(self):
        proc = _run(HARNESS_PRESENT, cwd=ROOT, args=[])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["has_molt"])
        self.assertNotEqual(result["dispatcher_name"], "_StubBus")

    def test_importing_the_bridge_does_not_modify_the_worktree(self):
        before = _git_porcelain()
        if before is None:
            self.skipTest("git unavailable, cannot compare the worktree")
        _run(HARNESS_PRESENT, cwd=ROOT, args=[])
        self.assertEqual(_git_porcelain(), before)


if __name__ == "__main__":
    unittest.main()
