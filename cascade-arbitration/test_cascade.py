"""
Tests for whorl.core.cascade.

Fully offline and deterministic: arbitration is a pure function of
CascadeRequest + HostProfile, so no network, clock or probe is involved
(AGENTS.md §6). Every HostProfile is constructed in-test.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cascade import (  # noqa: E402
    LOCAL_MAX_INPUT_TOKENS,
    LOCAL_MAX_OUTPUT_TOKENS,
    CascadeRequest,
    HostProfile,
    TaskShape,
    Tier,
    arbitrate,
    arbitrate_batch,
    estimate_local_seconds,
    measured_n200_profile,
)


def good_host(**kw) -> HostProfile:
    base = dict(
        name="test-host",
        total_ram_mb=8192,
        available_ram_mb=4096,
        cpu_cores=8,
        has_gpu=False,
        local_tok_per_s=30.0,
        local_load_s=2.0,
        local_model_installed=True,
        local_model_mb=500,
    )
    base.update(kw)
    return HostProfile(**base)


class TestLocalEligibility(unittest.TestCase):
    def test_short_shapes_are_local(self):
        for shape in (TaskShape.CLASSIFY, TaskShape.ROUTE, TaskShape.EXTRACT,
                      TaskShape.DEDUP, TaskShape.SUMMARIZE_SHORT):
            with self.subTest(shape=shape):
                d = arbitrate(CascadeRequest(shape=shape, input_tokens=100), good_host())
                self.assertTrue(d.eligible)
                self.assertEqual(d.tier, Tier.LOCAL)

    def test_open_ended_shapes_escalate(self):
        for shape in (TaskShape.GENERATE, TaskShape.REASON, TaskShape.CODE_WRITE):
            with self.subTest(shape=shape):
                d = arbitrate(CascadeRequest(shape=shape, input_tokens=100), good_host())
                self.assertFalse(d.eligible)
                self.assertEqual(d.tier, Tier.CLOUD)
                self.assertTrue(any("not local-eligible" in r for r in d.reasons))

    def test_output_budget_ceiling(self):
        ok = arbitrate(CascadeRequest(TaskShape.CLASSIFY, expected_output_tokens=64), good_host())
        self.assertTrue(ok.eligible)
        over = arbitrate(
            CascadeRequest(TaskShape.CLASSIFY, expected_output_tokens=LOCAL_MAX_OUTPUT_TOKENS + 1),
            good_host(),
        )
        self.assertFalse(over.eligible)
        self.assertTrue(any("exceeds local ceiling" in r for r in over.reasons))

    def test_input_ceiling(self):
        over = arbitrate(
            CascadeRequest(TaskShape.CLASSIFY, input_tokens=LOCAL_MAX_INPUT_TOKENS + 1),
            good_host(),
        )
        self.assertFalse(over.eligible)
        self.assertTrue(any("input" in r for r in over.reasons))

    def test_unknown_output_budget_assumes_ceiling_not_permissive(self):
        """Absent expected_output must not be read as 'anything goes'."""
        d = arbitrate(CascadeRequest(TaskShape.CLASSIFY, expected_output_tokens=None), good_host())
        self.assertTrue(d.eligible)  # defaults to the ceiling, not above it
        self.assertIsNotNone(d.estimated_local_s)


class TestHostGating(unittest.TestCase):
    def test_no_model_installed_is_not_usable(self):
        p = good_host(local_model_installed=False)
        self.assertFalse(p.local_usable)
        d = arbitrate(CascadeRequest(TaskShape.CLASSIFY), p)
        self.assertFalse(d.eligible)
        self.assertTrue(any("cannot run a resident local model" in r for r in d.reasons))

    def test_ram_starved_host_is_not_usable(self):
        """Cores are not the constraint; resident bytes are."""
        p = good_host(available_ram_mb=300, cpu_cores=16, local_model_mb=500)
        self.assertFalse(p.local_usable)

    def test_unmeasured_model_size_fails_closed(self):
        """No resident measurement => we cannot claim it fits, so we do not."""
        p = good_host(local_model_mb=0)
        self.assertFalse(p.local_usable)

    def test_gemma_2b_would_not_have_been_eligible(self):
        """The same arithmetic that rejected gemma:2b on this host."""
        p = measured_n200_profile()
        gemma = HostProfile(**{**p.__dict__, "local_model_mb": 1600})
        self.assertFalse(gemma.local_usable)

    def test_gpu_overrides_ram_ceiling(self):
        p = good_host(available_ram_mb=300, has_gpu=True)
        self.assertTrue(p.local_usable)

    def test_zero_cores_is_not_usable(self):
        self.assertFalse(good_host(cpu_cores=0).local_usable)

    def test_n200_profile_is_local_usable(self):
        """The documented box runs the 1B model, so it must be usable."""
        self.assertTrue(measured_n200_profile().local_usable)

    def test_n200_classify_is_local(self):
        d = arbitrate(CascadeRequest(TaskShape.CLASSIFY, input_tokens=200), measured_n200_profile())
        self.assertTrue(d.eligible)
        self.assertEqual(d.tier, Tier.LOCAL)


class TestEstimation(unittest.TestCase):
    def test_estimate_includes_cold_load(self):
        p = good_host(local_tok_per_s=10.0, local_load_s=5.0)
        est = estimate_local_seconds(CascadeRequest(TaskShape.CLASSIFY, expected_output_tokens=100), p)
        self.assertEqual(est, 15.0)  # 5s load + 100/10

    def test_estimate_is_none_without_throughput(self):
        p = good_host(local_tok_per_s=0.0)
        self.assertIsNone(estimate_local_seconds(CascadeRequest(TaskShape.CLASSIFY), p))

    def test_slow_host_reports_a_long_estimate(self):
        d = arbitrate(
            CascadeRequest(TaskShape.CLASSIFY, expected_output_tokens=200),
            measured_n200_profile(),
        )
        # 200 tok at 4.12 tok/s plus a 20.6s load -- this is why the ceiling exists.
        self.assertGreater(d.estimated_local_s, 60.0)


class TestDeterminismAndContract(unittest.TestCase):
    def test_arbitrate_is_pure(self):
        req = CascadeRequest(shape=TaskShape.EXTRACT, input_tokens=300, note="stable")
        host = good_host()
        first = arbitrate(req, host).to_dict()
        for _ in range(5):
            self.assertEqual(arbitrate(req, host).to_dict(), first)

    def test_batch_preserves_order_and_length(self):
        reqs = [CascadeRequest(s, input_tokens=10) for s in TaskShape]
        out = arbitrate_batch(reqs, good_host())
        self.assertEqual(len(out), len(reqs))
        self.assertTrue(out[0].eligible)                       # CLASSIFY
        self.assertFalse(out[-1].eligible)                     # CODE_WRITE

    def test_every_escalation_is_explained(self):
        """A decision that cannot be justified after the fact is not actionable."""
        reqs = [CascadeRequest(s, input_tokens=99999) for s in TaskShape]
        for d in arbitrate_batch(reqs, good_host()):
            self.assertFalse(d.eligible)
            self.assertTrue(d.reasons, f"unexplained escalation: {d}")

    def test_decision_serialises(self):
        d = arbitrate(CascadeRequest(TaskShape.ROUTE), good_host()).to_dict()
        self.assertEqual(sorted(d), ["eligible", "estimated_local_s", "reasons", "tier"])
        self.assertIn(d["tier"], ("local", "cloud"))

    def test_request_is_hashable_value(self):
        """Frozen dataclass -> safe to use as a dict key for caching decisions."""
        d = {CascadeRequest(TaskShape.CLASSIFY, input_tokens=5): "cached"}
        self.assertIn(CascadeRequest(TaskShape.CLASSIFY, input_tokens=5), d)


if __name__ == "__main__":
    unittest.main()
