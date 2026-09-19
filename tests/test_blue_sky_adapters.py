from __future__ import annotations

import unittest

from projects.blue_sky_meeting.adapters import AdapterRequest, AdapterRegistry, BuiltinAdapter, default_registry
from projects.blue_sky_meeting.blue_sky import add_agent, run_rounds, set_brief


class BlueSkyAdapterTest(unittest.TestCase):
    def test_builtin_adapter_is_deterministic_and_reviewable(self):
        request = AdapterRequest("room", "draft a roadmap", "strategist", 1)
        first = BuiltinAdapter().contribute(request)
        second = BuiltinAdapter().contribute(request)
        self.assertEqual(first, second)
        self.assertFalse(first.provenance["external_execution"])
        self.assertTrue(first.requires_approval)

    def test_registry_only_enables_builtin_by_default(self):
        registry = default_registry()
        self.assertEqual(registry.names(), ["builtin"])
        with self.assertRaises(ValueError):
            registry.get("shell")

    def test_rounds_use_adapter_provenance(self):
        room = {"room_id": "room", "label": "Room", "brief": "draft a roadmap", "agents": [], "events": [], "artifacts": [], "updated_at": ""}
        add_agent(room, "strategist", "strategist", "builtin")
        set_brief(room, "draft a roadmap")
        rounds = run_rounds(room, 1)
        contribution = rounds[0]["contributions"][0]
        self.assertEqual(contribution["adapter"], "builtin")
        self.assertFalse(contribution["provenance"]["external_execution"])
        self.assertTrue(contribution["requires_approval"])

    def test_custom_registry_requires_explicit_wiring(self):
        registry = AdapterRegistry()
        registry.register(BuiltinAdapter())
        self.assertEqual(registry.names(), ["builtin"])


if __name__ == "__main__":
    unittest.main()
