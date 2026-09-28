from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from projects.agents.sim.tideglass import (
    MarketObservation,
    ProbabilityRange,
    Stakeholder,
    load_scenario,
    simulate_market_response,
)


def sample_stakeholders() -> list[Stakeholder]:
    return [
        Stakeholder(
            "early adopters",
            ProbabilityRange(0.5, 0.7, 0.9),
            ProbabilityRange(0.2, 0.4, 0.6),
            ProbabilityRange(0.0, 0.1, 0.2),
        ),
        Stakeholder(
            "incumbents",
            ProbabilityRange(0.1, 0.2, 0.4),
            ProbabilityRange(0.6, 0.8, 1.0),
            ProbabilityRange(0.1, 0.3, 0.5),
        ),
    ]


class TideglassSimulationTests(unittest.TestCase):
    def test_same_seed_and_inputs_produce_same_report(self):
        first = simulate_market_response("launch a pilot", sample_stakeholders(), seed=42)
        second = simulate_market_response("launch a pilot", sample_stakeholders(), seed=42)
        self.assertEqual(first.to_dict(), second.to_dict())

    def test_report_is_json_serializable_and_records_assumptions(self):
        report = simulate_market_response("launch a pilot", sample_stakeholders(), runs=25)
        encoded = json.dumps(report.to_dict())
        self.assertIn('"calibration": "uncalibrated"', encoded)
        self.assertEqual(report.to_dict()["runs"], 25)
        self.assertIn("adoption", report.metrics)
        self.assertLessEqual(report.metrics["adoption"].p10, report.metrics["adoption"].median)
        self.assertLessEqual(report.metrics["adoption"].median, report.metrics["adoption"].p90)

    def test_evidence_is_retained_but_does_not_change_simulated_result(self):
        stakeholders = sample_stakeholders()
        baseline = simulate_market_response("launch a pilot", stakeholders, seed=5, runs=50)
        observation = MarketObservation(
            source="local fixture",
            observed_at="2026-09-27T00:00:00Z",
            metric="pilot signups",
            value=9000,
            unit="people",
            verified=False,
        )
        with_observation = simulate_market_response(
            "launch a pilot", stakeholders, observations=[observation], seed=5, runs=50
        )
        self.assertEqual(baseline.metrics, with_observation.metrics)
        self.assertEqual(with_observation.to_dict()["observations"][0]["source"], "local fixture")
        self.assertNotIn("local fixture", str(with_observation.to_dict()["assumptions"]))

    def test_degenerate_probabilities_have_exact_expected_shares(self):
        stakeholders = [
            Stakeholder(
                "certain adopter",
                ProbabilityRange(1, 1, 1),
                ProbabilityRange(0, 0, 0),
                ProbabilityRange(0, 0, 0),
            ),
            Stakeholder(
                "certain non-adopter",
                ProbabilityRange(0, 0, 0),
                ProbabilityRange(1, 1, 1),
                ProbabilityRange(0, 0, 0),
            ),
        ]
        report = simulate_market_response("announce", stakeholders, runs=3)
        self.assertEqual(report.metrics["adoption"].median, 0.5)
        self.assertEqual(report.metrics["competitor_response"].median, 0.5)
        self.assertEqual(report.metrics["regulatory_pushback"].median, 0.0)

    def test_invalid_probability_ranges_are_rejected(self):
        for values in ((-0.1, 0.2, 0.3), (0.2, 1.1, 1.2), (0.5, 0.4, 0.8)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ProbabilityRange(*values)

    def test_invalid_simulation_inputs_are_rejected(self):
        stakeholders = sample_stakeholders()
        for kwargs in ({"runs": 0}, {"runs": True}, {"runs": 100_001}, {"seed": 1.5}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                simulate_market_response("launch", stakeholders, **kwargs)
        with self.assertRaises(ValueError):
            simulate_market_response(" ", stakeholders)
        with self.assertRaises(ValueError):
            simulate_market_response("launch", [])
        with self.assertRaises(ValueError):
            simulate_market_response("launch", [stakeholders[0], stakeholders[0]])

    def test_observation_cannot_be_self_verified(self):
        with self.assertRaisesRegex(ValueError, "cannot assert"):
            MarketObservation(
                "fixture", "2026-09-27", claim="Observed something", verified=True
            )

    def test_observation_requires_provenance_and_finite_value(self):
        with self.assertRaises(ValueError):
            MarketObservation("", "2026-09-27", metric="signups", value=12)
        with self.assertRaises(ValueError):
            MarketObservation("fixture", "2026-09-27", metric="signups", value=float("nan"))
        with self.assertRaises(ValueError):
            MarketObservation("fixture", "2026-09-27", metric="signups", value=True)
        with self.assertRaises(ValueError):
            MarketObservation(
                "fixture", "2026-09-27", metric="signups", value=12,
                content_sha256="not-a-digest",
            )
        with self.assertRaises(ValueError):
            MarketObservation("fixture", "2026-09-27")


class TideglassScenarioFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "scenario.json"

    def _write_scenario(self, **overrides):
        payload = {
            "action": "launch a pilot",
            "stakeholders": [item.to_dict() for item in sample_stakeholders()],
            "observations": [
                {
                    "source": "fixture",
                    "observed_at": "2026-09-27T00:00:00Z",
                    "claim": "Two early customers asked about the pilot.",
                    "metric": "pilot signups",
                    "value": 4,
                    "unit": "people",
                }
            ],
        }
        payload.update(overrides)
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_loads_valid_scenario_and_provenance(self):
        self._write_scenario()
        action, stakeholders, observations = load_scenario(self.path)
        self.assertEqual(action, "launch a pilot")
        self.assertEqual(len(stakeholders), 2)
        self.assertEqual(observations[0].source, "fixture")
        self.assertEqual(observations[0].claim, "Two early customers asked about the pilot.")
        self.assertFalse(observations[0].verified)

    def test_rejects_malformed_and_unknown_scenario_fields(self):
        self.path.write_text("{bad json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid scenario JSON"):
            load_scenario(self.path)
        self._write_scenario(unexpected=True)
        with self.assertRaisesRegex(ValueError, "unknown fields: unexpected"):
            load_scenario(self.path)
        self._write_scenario(stakeholders=[{"name": "misspecified"}])
        with self.assertRaisesRegex(ValueError, "missing fields"):
            load_scenario(self.path)

    def test_duplicate_keys_and_self_verified_evidence_are_rejected(self):
        self.path.write_text(
            '{"action":"first","action":"second","stakeholders":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            load_scenario(self.path)

        self._write_scenario(
            observations=[{
                "source": "fixture",
                "observed_at": "2026-09-27T00:00:00Z",
                "claim": "Claim from an untrusted scout",
                "verified": True,
            }]
        )
        with self.assertRaisesRegex(ValueError, "cannot be self-asserted"):
            load_scenario(self.path)

    def test_rejects_oversized_scenario_file(self):
        from projects.agents.sim.tideglass import MAX_SCENARIO_BYTES

        self.path.write_bytes(b" " * (MAX_SCENARIO_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            load_scenario(self.path)

    def test_cli_emits_json_and_returns_nonzero_for_bad_scenario(self):
        self._write_scenario()
        command = [
            sys.executable,
            "-m",
            "projects.agents.sim.tideglass",
            str(self.path),
            "--runs",
            "12",
            "--seed",
            "9",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["runs"], 12)
        self.assertEqual(output["seed"], 9)
        self.assertEqual(output["observations"][0]["source"], "fixture")

        self.path.write_text("not json", encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid scenario JSON", result.stderr)


if __name__ == "__main__":
    unittest.main()
