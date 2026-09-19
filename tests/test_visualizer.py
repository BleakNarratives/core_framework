"""Offline tests for the boardroom status line.

`src/ui/visualizer.py` renders one line from `.boardroom_history.jsonl`, which it
reads **relative to the current working directory**. Every case below therefore
runs inside a temporary directory, and the repository root is asserted clean
afterwards, so a test that forgets to relocate itself fails instead of writing
into the checkout.

Two groups of behaviour are pinned:

1. The graceful paths: missing file, empty file, missing keys, missing payload.
2. The paths that currently **raise** rather than degrade (malformed JSON, a
   blank final line, a non-object entry, a non-object payload). These are pinned
   as they are, not "fixed" — changing them is a behaviour change that belongs in
   its own change. See `docs/AGENT_WORK_QUEUE.md`, item 2.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "ui" / "visualizer.py"
HISTORY_NAME = ".boardroom_history.jsonl"
LIVE_HISTORY = ROOT / HISTORY_NAME

WAITING = "[Boardroom: Waiting...]"
EMPTY = "[Boardroom: Empty]"


def _load_visualizer():
    spec = importlib.util.spec_from_file_location("ui_visualizer", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Loading must not render anything; rendering lives behind __name__.
    spec.loader.exec_module(module)
    return module


visualizer = _load_visualizer()


@contextmanager
def _history(contents: str | None):
    """Run the body in a temp cwd, optionally holding a history file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / HISTORY_NAME
        if contents is not None:
            path.write_text(contents, encoding="utf-8")
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            yield path
        finally:
            os.chdir(previous)


def _entry(persona=None, status=None, payload=None, **rest) -> str:
    """Build one JSONL line, omitting keys that must be absent."""
    record = dict(rest)
    if payload is not None:
        record["sanitized_payload"] = payload
    elif persona is not None or status is not None:
        inner = {}
        if persona is not None:
            inner["persona"] = persona
        if status is not None:
            inner["status"] = status
        record["sanitized_payload"] = inner
    return json.dumps(record) + "\n"


class TestBoardroomStatusRendering(unittest.TestCase):
    """Malformed-and-missing cases the renderer is expected to survive."""

    def test_missing_file_waits(self):
        with _history(None):
            self.assertEqual(visualizer.render_boardroom_status(), WAITING)

    def test_zero_byte_file_is_empty(self):
        with _history(""):
            self.assertEqual(visualizer.render_boardroom_status(), EMPTY)

    def test_single_entry_renders_persona_and_status(self):
        with _history(_entry(persona="Ada", status="APPROVED")):
            self.assertEqual(visualizer.render_boardroom_status(), "[Ada: APPROVED]")

    def test_last_entry_wins(self):
        # The renderer is a "current status" line, so only the final record counts.
        contents = _entry(persona="Ada", status="APPROVED") + _entry(
            persona="Grace", status="BLOCKED"
        )
        with _history(contents):
            self.assertEqual(visualizer.render_boardroom_status(), "[Grace: BLOCKED]")

    def test_missing_keys_fall_back_to_placeholders(self):
        with _history(_entry(payload={})):
            self.assertEqual(visualizer.render_boardroom_status(), "[Unknown: UNKNOWN]")

    def test_absent_payload_key_falls_back_to_placeholders(self):
        with _history(_entry(ended_at="2026-09-19T00:00:00Z")):
            self.assertEqual(visualizer.render_boardroom_status(), "[Unknown: UNKNOWN]")

    def test_persona_present_without_status(self):
        with _history(_entry(payload={"persona": "Ada"})):
            self.assertEqual(visualizer.render_boardroom_status(), "[Ada: UNKNOWN]")

    def test_status_present_without_persona(self):
        with _history(_entry(payload={"status": "APPROVED"})):
            self.assertEqual(visualizer.render_boardroom_status(), "[Unknown: APPROVED]")

    def test_non_string_values_are_interpolated_verbatim(self):
        # No coercion is applied; whatever JSON value is present is what prints.
        with _history(_entry(payload={"persona": 7, "status": True})):
            self.assertEqual(visualizer.render_boardroom_status(), "[7: True]")

    def test_non_ascii_persona_round_trips(self):
        with _history(_entry(persona="Ærün ✓", status="OK")):
            self.assertEqual(visualizer.render_boardroom_status(), "[Ærün ✓: OK]")


class TestBoardroomStatusRaises(unittest.TestCase):
    """Current raising behaviour, pinned so a change to it is deliberate."""

    def test_malformed_json_raises(self):
        with _history('{"sanitized_payload": {"persona": "Ada"\n'):
            with self.assertRaises(json.JSONDecodeError):
                visualizer.render_boardroom_status()

    def test_trailing_blank_line_raises(self):
        # readlines() yields "\n" for the blank tail, and json.loads("\n") fails.
        with _history(_entry(persona="Ada", status="OK") + "\n"):
            with self.assertRaises(json.JSONDecodeError):
                visualizer.render_boardroom_status()

    def test_top_level_array_raises_attribute_error(self):
        with _history(json.dumps([{"sanitized_payload": {}}]) + "\n"):
            with self.assertRaises(AttributeError):
                visualizer.render_boardroom_status()

    def test_null_payload_raises_attribute_error(self):
        with _history(json.dumps({"sanitized_payload": None}) + "\n"):
            with self.assertRaises(AttributeError):
                visualizer.render_boardroom_status()

    def test_string_payload_raises_attribute_error(self):
        with _history(json.dumps({"sanitized_payload": "Ada:OK"}) + "\n"):
            with self.assertRaises(AttributeError):
                visualizer.render_boardroom_status()


class TestBoardroomStatusIsolation(unittest.TestCase):
    """The renderer must stay a pure read of its own file."""

    def test_render_does_not_write_to_its_directory(self):
        with _history(_entry(persona="Ada", status="OK")) as path:
            before = sorted(p.name for p in path.parent.iterdir())
            visualizer.render_boardroom_status()
            after = sorted(p.name for p in path.parent.iterdir())
            self.assertEqual(before, after)

    def test_repo_root_history_is_never_created(self):
        # Not vacuous: it fails the moment a case above forgets to chdir into its
        # temp directory and renders against the checkout instead.
        self.assertFalse(
            LIVE_HISTORY.exists(),
            f"{LIVE_HISTORY} exists — a test rendered against the repository root",
        )

    def test_cli_prints_waiting_with_no_history(self):
        # Exercises the __main__ branch from the repository root, where no
        # .boardroom_history.jsonl exists, proving a fresh clone does not traceback.
        self.assertFalse(LIVE_HISTORY.exists())
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), WAITING)


if __name__ == "__main__":
    unittest.main()
