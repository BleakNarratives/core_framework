from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from projects.blue_sky_meeting.blue_sky import RoomStore, add_agent, export_markdown, run_rounds, set_brief


class BlueSkyMeetingTest(unittest.TestCase):
    def test_room_lifecycle_is_deterministic_and_local(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RoomStore(directory)
            room = store.create("launch-plan", "Launch Plan")
            add_agent(room, "strategist", "brand strategist", "builtin")
            set_brief(room, "Create a local-first collaboration console")
            rounds = run_rounds(room, 2)
            store.save(room)

            loaded = store.load("launch-plan")
            self.assertEqual(len(rounds), 2)
            self.assertEqual(len(loaded["agents"]), 1)
            self.assertEqual(len(loaded["artifacts"]), 1)
            self.assertTrue(loaded["artifacts"][0]["requires_human_approval"])
            self.assertEqual(len(loaded["events"]), 6)

            markdown = export_markdown(loaded)
            self.assertIn("# Launch Plan", markdown)
            self.assertIn("brand strategist proposal for round 1", markdown)
            self.assertFalse((Path(directory) / "launch-plan.md").exists())

    def test_exported_room_contains_no_external_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RoomStore(directory)
            room = store.create("safe", "Safe Room")
            add_agent(room, "cli", "script writer", "builtin")
            set_brief(room, "Draft a roadmap")
            run_rounds(room, 1)
            payload = json.dumps(room)
            self.assertNotIn("subprocess", payload)
            self.assertNotIn("api_key", payload)
            self.assertNotIn("send", payload)


if __name__ == "__main__":
    unittest.main()
