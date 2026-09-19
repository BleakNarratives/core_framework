"""Where the Thoth agent bus writes its events.

`thoth_orchestrator/agent_bus.py` derives its state directory from `ROOTBASE_DIR`.
That default used to be a hardcoded `/home/bleaknarratives/RootBase`, so redirecting
`$HOME` did **not** contain the bus: on 2026-09-19 `tests/test_sovereign_bridges.py`
emitted one event straight into the real `~/RootBase/logs/shared/agent_events.jsonl`
before anyone noticed.

The durable part of that fix has to live here, because there is no commit that could
carry it: `git ls-files thoth_orchestrator` is empty — the whole directory is ignored
by the root `.gitignore`. So these tests pin the behaviour instead, and they skip
rather than fail on a checkout where `agent_bus` is not importable.

Three things are asserted: the default lands under `$HOME` and actually emits there,
an explicit `ROOTBASE_DIR` still wins, and on this machine the resolved path is
byte-identical to the one the old hardcoded default produced — portability without
behaviour change.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_DEFAULT = "/home/bleaknarratives/RootBase/logs/shared/agent_events.jsonl"

# The bus is reached the way the real code reaches it: importing a sibling from
# `thoth_orchestrator/motherbrain.py` puts that directory on sys.path, which is what
# makes a top-level `import agent_bus` resolve at all.
HARNESS = r'''
import json, os
from pathlib import Path

try:
    from thoth_orchestrator.motherbrain import MotherBrain  # noqa: F401
except Exception:
    pass

out = {"home": os.environ["HOME"]}
try:
    import agent_bus
except Exception as exc:
    out["import_error"] = "%s: %s" % (type(exc).__name__, exc)
    print(json.dumps(out))
    raise SystemExit(0)

bus = Path(agent_bus.BUS_FILE)
out["bus_file"] = str(bus)
out["rootbase_dir"] = str(agent_bus.ROOTBASE_DIR)

if os.environ.get("BUS_PROBE_EMIT") == "1":
    try:
        event = agent_bus.emit_event(
            "molt.test.bus.location", {"probe": True}, source="bus-location-test"
        )
        out["emitted_event_id"] = event.get("event_id") if isinstance(event, dict) else str(event)
    except Exception as exc:
        out["emit_error"] = "%s: %s" % (type(exc).__name__, exc)
    out["bus_exists"] = bus.exists()
    out["bus_lines"] = len(bus.read_text(encoding="utf-8").splitlines()) if bus.exists() else 0

print(json.dumps(out))
'''


def _run(home: Path, emit: bool = False, env_extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(ROOT)
    env.pop("ROOTBASE_DIR", None)
    env.pop("ROOTBASE_BUS_DIR", None)
    env.pop("ROOTBASE_EVENT_FILE", None)
    env["BUS_PROBE_EMIT"] = "1" if emit else "0"
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-c", HARNESS],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"harness printed no JSON:\n{proc.stdout}\n{proc.stderr}")


class ThothBusLocationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._home = tempfile.TemporaryDirectory()
        cls.home = Path(cls._home.name)
        probe = _run(cls.home)
        if probe.get("import_error"):
            raise unittest.SkipTest(
                f"agent_bus is not importable here: {probe['import_error']}"
            )

    @classmethod
    def tearDownClass(cls):
        cls._home.cleanup()

    def test_default_bus_file_lands_under_the_redirected_home(self):
        probe = _run(self.home, emit=True)
        self.assertNotIn("emit_error", probe, probe.get("emit_error"))
        self.assertTrue(
            probe["bus_file"].startswith(str(self.home)),
            f"the bus escaped the redirected HOME: {probe['bus_file']}",
        )
        self.assertTrue(probe.get("bus_exists"), "no bus file was created")
        self.assertGreaterEqual(probe.get("bus_lines", 0), 1)

    def test_emitting_from_a_redirected_home_leaves_the_real_bus_alone(self):
        # This is the exact regression that started this: the line count of the live
        # bus must not move because a contained run emitted.
        real_bus = Path(OLD_DEFAULT)
        before = (
            len(real_bus.read_text(encoding="utf-8").splitlines())
            if real_bus.exists()
            else None
        )
        _run(self.home, emit=True)
        after = (
            len(real_bus.read_text(encoding="utf-8").splitlines())
            if real_bus.exists()
            else None
        )
        self.assertEqual(before, after, "the live bus changed during a contained run")

    def test_an_explicit_rootbase_dir_still_wins(self):
        pinned = self.home / "Elsewhere"
        probe = _run(self.home, env_extra={"ROOTBASE_DIR": str(pinned)})
        self.assertEqual(probe["rootbase_dir"], str(pinned))
        self.assertTrue(probe["bus_file"].startswith(str(pinned)))

    def test_an_explicit_event_file_still_wins(self):
        pinned = self.home / "pinned.jsonl"
        probe = _run(self.home, env_extra={"ROOTBASE_EVENT_FILE": str(pinned)})
        self.assertEqual(probe["bus_file"], str(pinned))

    def test_the_resolved_path_matches_what_this_machine_used_before(self):
        # Behaviour preservation: with a normal HOME the path is the same string the
        # hardcoded default produced, so anything reading the existing bus stays put.
        real_home = Path(os.path.expanduser("~"))
        probe = _run(real_home)
        self.assertEqual(
            probe["bus_file"],
            str(real_home / "RootBase" / "logs" / "shared" / "agent_events.jsonl"),
        )
        # And the literal itself, where that layout exists (this machine's history).
        if Path(OLD_DEFAULT).exists():
            self.assertEqual(probe["bus_file"], OLD_DEFAULT)


if __name__ == "__main__":
    unittest.main()
