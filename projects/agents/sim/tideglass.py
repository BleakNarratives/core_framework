"""Tideglass: a small, offline market-response scenario simulator.

The model samples explicitly supplied stakeholder assumptions. It does not fit
historical data, fetch market data, or turn observations into assumptions.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODEL_VERSION = "assumption-driven-monte-carlo-v1"
MAX_RUNS = 100_000
MAX_STAKEHOLDERS = 100
MAX_OBSERVATIONS = 1_000
MAX_SCENARIO_BYTES = 1_000_000
MAX_SAMPLED_OUTCOMES = 10_000_000


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class ProbabilityRange:
    """Low, most-likely, and high assumed probabilities, each in [0, 1]."""

    low: float
    likely: float
    high: float

    def __post_init__(self) -> None:
        values = (self.low, self.likely, self.high)
        if any(
            not _is_finite_number(value) or not 0 <= value <= 1
            for value in values
        ):
            raise ValueError("probabilities must be finite numbers between 0 and 1")
        if not self.low <= self.likely <= self.high:
            raise ValueError("probabilities must satisfy low <= likely <= high")

    def sample(self, rng: random.Random) -> float:
        """Draw one triangular sample, with the mode at ``likely``."""
        return rng.triangular(self.low, self.high, self.likely)

    def to_dict(self) -> dict[str, float]:
        return {"low": self.low, "likely": self.likely, "high": self.high}


@dataclass(frozen=True)
class Stakeholder:
    """A stakeholder archetype and its assumed response likelihoods."""

    name: str
    adoption: ProbabilityRange
    competitor_response: ProbabilityRange
    regulatory_pushback: ProbabilityRange

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("stakeholder name must be a non-blank string")
        if not all(
            isinstance(value, ProbabilityRange)
            for value in (self.adoption, self.competitor_response, self.regulatory_pushback)
        ):
            raise ValueError("stakeholder response assumptions must be ProbabilityRange values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adoption": self.adoption.to_dict(),
            "competitor_response": self.competitor_response.to_dict(),
            "regulatory_pushback": self.regulatory_pushback.to_dict(),
        }


@dataclass(frozen=True)
class MarketObservation:
    """A sourced observation attached for context, never used as an assumption.

    A supplied content digest is provenance metadata only. Tideglass cannot
    verify it without the source bytes and does not infer source authenticity.
    """

    source: str
    observed_at: str
    metric: str = ""
    value: float | None = None
    unit: str = ""
    verified: bool = False
    content_sha256: str = ""
    claim: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("observation source is required")
        if not isinstance(self.observed_at, str) or not self.observed_at.strip():
            raise ValueError("observation observed_at is required")
        if not isinstance(self.claim, str) or len(self.claim) > 4_000:
            raise ValueError("observation claim must be a string of at most 4000 characters")
        if not isinstance(self.metric, str) or len(self.metric) > 128:
            raise ValueError("observation metric must be a string of at most 128 characters")
        if len(self.source) > 2_000 or len(self.observed_at) > 64:
            raise ValueError("observation source or observed_at exceeds its size limit")
        if not self.claim.strip() and not self.metric.strip():
            raise ValueError("observation requires a claim or a numeric metric")
        has_metric = bool(self.metric.strip())
        has_value = self.value is not None
        if has_metric != has_value:
            raise ValueError("observation metric and value must be supplied together")
        if has_value and not _is_finite_number(self.value):
            raise ValueError("observation value must be a finite number")
        if not isinstance(self.unit, str) or len(self.unit) > 32:
            raise ValueError("observation unit must be a string of at most 32 characters")
        if self.verified is not False:
            raise ValueError("Tideglass cannot assert that an observation is verified")
        if not isinstance(self.content_sha256, str) or (
            self.content_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256)
        ):
            raise ValueError("content_sha256 must be a 64-character lowercase SHA-256 hex digest")

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "source": self.source,
            "observed_at": self.observed_at,
            "claim": self.claim,
            "unit": self.unit,
            "verified": self.verified,
        }
        if self.metric:
            payload["metric"] = self.metric
            payload["value"] = self.value
        if self.content_sha256:
            payload["content_sha256"] = self.content_sha256
        return payload


@dataclass(frozen=True)
class MetricSummary:
    """Distribution summary of a simulated stakeholder-archetype share."""

    mean: float
    p10: float
    median: float
    p90: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "p10": self.p10,
            "median": self.median,
            "p90": self.p90,
        }


@dataclass(frozen=True)
class SimulationReport:
    action: str
    seed: int
    runs: int
    stakeholders: tuple[Stakeholder, ...]
    observations: tuple[MarketObservation, ...]
    metrics: dict[str, MetricSummary]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report with assumptions and evidence split."""
        return {
            "model": MODEL_VERSION,
            "calibration": "uncalibrated",
            "action": self.action,
            "seed": self.seed,
            "runs": self.runs,
            "assumptions": {
                "stakeholders": [item.to_dict() for item in self.stakeholders],
                "independence": "all outcome events are sampled independently across archetypes and metrics",
            },
            "observations": [item.to_dict() for item in self.observations],
            "metrics": {name: summary.to_dict() for name, summary in self.metrics.items()},
            "caveat": (
                "Conditional scenario outputs, not empirical forecasts. No historical "
                "data is fitted; attached observations do not affect the simulation."
            ),
        }


def _percentile(sorted_values: list[float], fraction: float) -> float:
    position = (len(sorted_values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _summarize(values: list[float]) -> MetricSummary:
    ordered = sorted(values)
    return MetricSummary(
        mean=sum(ordered) / len(ordered),
        p10=_percentile(ordered, 0.10),
        median=_percentile(ordered, 0.50),
        p90=_percentile(ordered, 0.90),
    )


def simulate_market_response(
    action: str,
    stakeholders: list[Stakeholder] | tuple[Stakeholder, ...],
    *,
    observations: list[MarketObservation] | tuple[MarketObservation, ...] = (),
    runs: int = 1_000,
    seed: int = 17,
) -> SimulationReport:
    """Run reproducible Monte Carlo scenarios from explicit assumptions.

    Each stakeholder is one archetype. For every run, the simulator samples
    adoption, competitor response, and regulatory pushback independently for
    each archetype, then reports the share of archetypes with each response.
    Observations are retained in the report for provenance, but are not fitted
    or used to alter scenario probabilities.
    """
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-blank string")
    if not isinstance(stakeholders, (list, tuple)):
        raise ValueError("stakeholders must be a list or tuple")
    if not isinstance(observations, (list, tuple)):
        raise ValueError("observations must be a list or tuple")
    if not stakeholders:
        raise ValueError("at least one stakeholder is required")
    if len(stakeholders) > MAX_STAKEHOLDERS:
        raise ValueError(f"at most {MAX_STAKEHOLDERS} stakeholders are supported")
    if len(observations) > MAX_OBSERVATIONS:
        raise ValueError(f"at most {MAX_OBSERVATIONS} observations are supported")
    if not all(isinstance(item, Stakeholder) for item in stakeholders):
        raise ValueError("stakeholders must contain only Stakeholder values")
    if len({item.name for item in stakeholders}) != len(stakeholders):
        raise ValueError("stakeholder names must be unique")
    if not all(isinstance(item, MarketObservation) for item in observations):
        raise ValueError("observations must contain only MarketObservation values")
    if isinstance(runs, bool) or not isinstance(runs, int) or not 1 <= runs <= MAX_RUNS:
        raise ValueError(f"runs must be an integer between 1 and {MAX_RUNS}")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    sampled_outcomes = runs * len(stakeholders) * 3
    if sampled_outcomes > MAX_SAMPLED_OUTCOMES:
        raise ValueError(
            f"runs and stakeholders exceed the {MAX_SAMPLED_OUTCOMES} outcome sample limit"
        )

    rng = random.Random(seed)
    responses = {"adoption": [], "competitor_response": [], "regulatory_pushback": []}
    count = len(stakeholders)

    for _ in range(runs):
        outcome_counts = {name: 0 for name in responses}
        for stakeholder in stakeholders:
            for metric, likelihood in (
                ("adoption", stakeholder.adoption),
                ("competitor_response", stakeholder.competitor_response),
                ("regulatory_pushback", stakeholder.regulatory_pushback),
            ):
                if rng.random() < likelihood.sample(rng):
                    outcome_counts[metric] += 1
        for metric in responses:
            responses[metric].append(outcome_counts[metric] / count)

    return SimulationReport(
        action=action.strip(),
        seed=seed,
        runs=runs,
        stakeholders=tuple(stakeholders),
        observations=tuple(observations),
        metrics={name: _summarize(values) for name, values in responses.items()},
    )


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _object_fields(
    value: Any, required: set[str], optional: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise ValueError(f"{label} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
    return value


def _parse_probability_range(value: Any, label: str) -> ProbabilityRange:
    fields = _object_fields(value, {"low", "likely", "high"}, set(), label)
    try:
        return ProbabilityRange(fields["low"], fields["likely"], fields["high"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: {exc}") from exc


def _parse_stakeholder(value: Any, index: int) -> Stakeholder:
    label = f"stakeholders[{index}]"
    fields = _object_fields(
        value,
        {"name", "adoption", "competitor_response", "regulatory_pushback"},
        set(),
        label,
    )
    if not isinstance(fields["name"], str):
        raise ValueError(f"{label}.name must be a string")
    return Stakeholder(
        name=fields["name"],
        adoption=_parse_probability_range(fields["adoption"], f"{label}.adoption"),
        competitor_response=_parse_probability_range(
            fields["competitor_response"], f"{label}.competitor_response"
        ),
        regulatory_pushback=_parse_probability_range(
            fields["regulatory_pushback"], f"{label}.regulatory_pushback"
        ),
    )


def _parse_observation(value: Any, index: int) -> MarketObservation:
    label = f"observations[{index}]"
    fields = _object_fields(
        value,
        {"source", "observed_at"},
        {"claim", "metric", "value", "unit", "verified", "content_sha256"},
        label,
    )
    if fields.get("verified", False) is not False:
        raise ValueError(f"{label}.verified cannot be self-asserted by a scenario file")
    return MarketObservation(
        source=fields["source"],
        observed_at=fields["observed_at"],
        metric=fields.get("metric", ""),
        value=fields.get("value"),
        unit=fields.get("unit", ""),
        verified=False,
        content_sha256=fields.get("content_sha256", ""),
        claim=fields.get("claim", ""),
    )


def load_scenario(path: str | Path) -> tuple[str, list[Stakeholder], list[MarketObservation]]:
    """Load and strictly validate an offline JSON scenario file.

    File size and field names are bounded to avoid accidentally treating large
    or misspelled Scout output as a valid model specification.
    """
    scenario_path = Path(path)
    with scenario_path.open("rb") as scenario_file:
        raw = scenario_file.read(MAX_SCENARIO_BYTES + 1)
    if len(raw) > MAX_SCENARIO_BYTES:
        raise ValueError(f"scenario exceeds {MAX_SCENARIO_BYTES} bytes")
    try:
        payload = json.loads(
            raw,
            object_pairs_hook=_unique_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"invalid scenario JSON: {exc}") from exc

    fields = _object_fields(
        payload, {"action", "stakeholders"}, {"observations"}, "scenario"
    )
    if not isinstance(fields["action"], str) or not fields["action"].strip():
        raise ValueError("scenario.action must be a non-blank string")
    if not isinstance(fields["stakeholders"], list):
        raise ValueError("scenario.stakeholders must be an array")
    raw_observations = fields.get("observations", [])
    if not isinstance(raw_observations, list):
        raise ValueError("scenario.observations must be an array")

    if not fields["stakeholders"]:
        raise ValueError("scenario.stakeholders must contain at least one stakeholder")
    if len(fields["stakeholders"]) > MAX_STAKEHOLDERS:
        raise ValueError(f"at most {MAX_STAKEHOLDERS} stakeholders are supported")
    if len(raw_observations) > MAX_OBSERVATIONS:
        raise ValueError(f"at most {MAX_OBSERVATIONS} observations are supported")

    stakeholders = [
        _parse_stakeholder(item, index) for index, item in enumerate(fields["stakeholders"])
    ]
    observations = [
        _parse_observation(item, index) for index, item in enumerate(raw_observations)
    ]
    if len({item.name for item in stakeholders}) != len(stakeholders):
        raise ValueError("stakeholder names must be unique")
    return fields["action"].strip(), stakeholders, observations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an offline Tideglass market-response scenario"
    )
    parser.add_argument("scenario", help="path to a JSON scenario file")
    parser.add_argument("--runs", type=int, default=1_000, help=f"simulation count (1-{MAX_RUNS})")
    parser.add_argument("--seed", type=int, default=17, help="reproducible random seed")
    args = parser.parse_args(argv)

    try:
        action, stakeholders, observations = load_scenario(args.scenario)
        report = simulate_market_response(
            action,
            stakeholders,
            observations=observations,
            runs=args.runs,
            seed=args.seed,
        )
    except (OSError, ValueError) as exc:
        print(f"tideglass: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
