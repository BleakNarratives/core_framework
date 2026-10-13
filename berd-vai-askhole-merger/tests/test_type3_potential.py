from __future__ import annotations

import unittest

from type3_potential import get_type3_potentials


class Type3PotentialTests(unittest.TestCase):
    def test_returns_exactly_three_named_exploratory_use_cases(self):
        ideas = get_type3_potentials({"name": "Example Plumbing"}, [])
        self.assertEqual(len(ideas), 3)
        self.assertEqual(
            {idea["id"] for idea in ideas},
            {"intake-leak-map", "review-to-intake", "reusable-vertical-playbook"},
        )
        self.assertTrue(all(idea["status"] == "exploratory—not scored" for idea in ideas))
        self.assertTrue(all(idea["external_action"] == "disabled" for idea in ideas))

    def test_unverified_claim_does_not_change_potential_or_become_personalized(self):
        lead = {"name": "Acme", "vertical": "dentist", "city": "Town"}
        evidence = [{"claim": "They lose $9000 monthly", "trust": "unverified"}]
        first = get_type3_potentials(lead, evidence)
        second = get_type3_potentials({"name": "Different Business"}, [])
        self.assertEqual(first, second)
        rendered = " ".join(str(idea) for idea in first)
        self.assertNotIn("Acme", rendered)
        self.assertNotIn("$9000", rendered)

    def test_rejects_bad_input_shapes(self):
        with self.assertRaises(TypeError):
            get_type3_potentials("not a lead", [])
        with self.assertRaises(TypeError):
            get_type3_potentials({}, {})


if __name__ == "__main__":
    unittest.main()
