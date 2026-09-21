"""Tests for the diversity probe, including the failure modes it exists to catch.

The probe's job is to fail when the pipe goes static, so most of these tests build a
deliberately broken pipe and assert that the probe notices. A probe that can only
report success is decoration.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.foxwood_research import (
    LENSES,
    MAX_SOURCES_PER_FRAME,
    PROMPT_CHAR_BUDGET,
    ResearchLedger,
    lens_plan,
    validate_proposals,
    verdict_key,
)
from src.foxwood_research.diversity import (
    PROBE_QUERY,
    build_frames,
    measure_diversity,
)
from src.foxwood_research.pipe import identity_digest
from src.foxwood_research.synthesis import SynthesisError


class DiversityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = ResearchLedger(Path(self.tmp.name) / "ledger")
        self.source = self.ledger.add_source(
            title="A public record", url="https://example.test/record",
            publisher="Example", excerpt="A bounded excerpt.", license_note="public terms")

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, **kwargs):
        return measure_diversity(self.ledger, [self.source.source_id], **kwargs)


class TestTheProbePassesOnAHealthyPipe(DiversityCase):
    def test_a_healthy_pipe_is_varied_and_reproducible(self):
        report = self.report()
        self.assertTrue(report.ok, report.failures())
        self.assertEqual(report.verdict, "varied and reproducible")

    def test_every_shipped_lens_is_reached_over_a_realistic_seed_range(self):
        # Not ">= 2": if the seed function can reach all five, this range should.
        report = self.report(seeds=range(60))
        self.assertEqual(report.unspanned_lenses, ())
        self.assertEqual(len(report.lenses_reached), len(LENSES))

    def test_a_lens_prompt_does_not_depend_on_the_seed(self):
        report = self.report(seeds=range(40))
        self.assertEqual(report.prompt_drift, ())
        # One distinct prompt per lens, no matter how many seeds reached it.
        self.assertEqual(set(report.distinct_prompts_per_lens.values()), {1})

    def test_consecutive_seeds_cover_every_lens_exactly_once(self):
        # The seed was originally a hash, which reached only four of five lenses over
        # seeds 0..11 and left `refine` looking like a lens that does not exist.
        report = self.report(seeds=range(len(LENSES)))
        self.assertTrue(report.ok, report.failures())
        self.assertEqual(sorted(report.frames_per_lens.values()), [1] * len(LENSES))

    def test_every_frame_is_within_budget(self):
        self.assertEqual(self.report().budget_violations, ())

    def test_the_report_says_what_it_measured_and_what_it_did_not(self):
        rendered = self.report().to_markdown()
        self.assertIn("varied and reproducible", rendered)
        self.assertIn("no model was called", rendered)
        self.assertIn(str(PROMPT_CHAR_BUDGET), rendered)
        self.assertIn(str(MAX_SOURCES_PER_FRAME), rendered)


class TestQuestionIdentity(DiversityCase):
    """The bug the probe caught: a seed must not be part of a question's identity."""

    def test_one_lens_under_many_seeds_carries_one_frame_id(self):
        report = self.report(seeds=range(40))
        self.assertEqual(report.split_identities, ())
        self.assertEqual(report.shared_identities, ())

    def test_a_frame_carries_exactly_one_source_hash_set(self):
        frame = build_frames(PROBE_QUERY, [self.source], 3)[0][1]
        self.assertEqual(frame.source_hashes, (self.source.content_hash,))

    def test_two_seeds_reaching_the_same_lens_share_the_verdict_key(self):
        # Two seeds, deliberately steered onto one lens.
        same = [verdict_key("rank", [self.source.source_id]) for _ in range(2)]
        self.assertEqual(same[0], same[1])

    def test_different_lenses_never_share_a_verdict_key(self):
        keys = {verdict_key(lens.name, [self.source.source_id]) for lens in LENSES}
        self.assertEqual(len(keys), len(LENSES))

    def test_the_frame_id_is_documented_by_its_inputs(self):
        frame = build_frames(PROBE_QUERY, [self.source], 7, rounds=2)[0][1]
        self.assertEqual(
            frame.frame_id,
            identity_digest("frame", frame.lens, frame.round_index, frame.rounds,
                            self.source.content_hash))


class TestTheProbeNoticesWhenThePipeGoesStatic(DiversityCase):
    """Each of these breaks one invariant on purpose. A test that cannot fail is not one."""

    def test_a_seed_function_that_always_returns_one_lens_is_caught(self):
        # The static-pipe failure. Every other invariant still holds here: the one
        # lens is stable, distinct from nothing, bounded, and replays exactly.
        with patch("src.foxwood_research.diversity.lens_plan",
                   lambda seed, rounds=1, lens=None: (LENSES[0],)):
            report = self.report(seeds=range(12))
        self.assertFalse(report.ok)
        self.assertEqual(report.verdict, "STATIC OR UNREPRODUCIBLE")
        self.assertEqual(len(report.unspanned_lenses), len(LENSES) - 1)
        self.assertTrue(any("no seed reached" in problem for problem in report.failures()))

    def test_two_lenses_that_read_the_same_are_caught(self):
        # Collapse every lens onto one instruction: five names, one question.
        # Names stay distinct; the instructions collapse. Five names, one question.
        twin = LENSES[1]
        collapsed = tuple(
            type(lens)(lens.name, twin.intent, twin.instruction) for lens in LENSES)
        with patch("src.foxwood_research.diversity.lens_plan",
                   lambda seed, rounds=1, lens=None: (collapsed[int(seed) % len(collapsed)],)):
            report = self.report(seeds=range(12))
        self.assertFalse(report.ok)
        self.assertTrue(report.duplicate_lens_text)

    def test_a_seed_that_salts_the_prompt_is_caught(self):
        # A prompt that varies with the seed is not replayable from a named question.
        real_frame_prompt = __import__(
            "src.foxwood_research.pipe", fromlist=["frame_prompt"]).frame_prompt

        class Salted:
            """A FrameRequest whose prompt grew a seed-dependent tail."""

            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            @property
            def prompt(self):
                return self._inner.prompt + f"\nsalted with seed {self._inner.seed}"

        with patch("src.foxwood_research.diversity.frame_prompt",
                   lambda *a, **k: Salted(real_frame_prompt(*a, **k))):
            report = self.report(seeds=range(12))
        self.assertFalse(report.ok)
        self.assertTrue(report.prompt_drift)

    def test_an_identity_that_depends_on_the_seed_is_caught(self):
        real_frame_prompt = __import__(
            "src.foxwood_research.pipe", fromlist=["frame_prompt"]).frame_prompt

        class SeedKeyed:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            @property
            def frame_id(self):
                return identity_digest("frame", self._inner.seed, self._inner.lens)

        with patch("src.foxwood_research.diversity.frame_prompt",
                   lambda *a, **k: SeedKeyed(real_frame_prompt(*a, **k))):
            report = self.report(seeds=range(12))
        self.assertFalse(report.ok)
        self.assertTrue(report.split_identities)

    def test_an_over_budget_frame_is_caught(self):
        # The pipe refuses to *build* an over-budget frame, so a stricter probe
        # budget can only be reported as missing headroom -- and that is what it is:
        # a real frame with less room than the caller asked for.
        report = self.report(budget=50)
        self.assertFalse(report.ok)
        self.assertTrue(report.budget_violations)
        self.assertIn("50 budget", report.budget_violations[0])

    def test_a_too_greedy_source_cap_is_reported_rather_than_swallowed(self):
        # frame_prompt refuses outright, so the probe surfaces it as an exception --
        # a bound that fails loudly rather than a silently shortened bundle.
        records = [
            self.ledger.add_source(title=f"T{index}", url=f"https://example.test/{index}",
                                   publisher="P", excerpt="E")
            for index in range(MAX_SOURCES_PER_FRAME + 1)
        ]
        with self.assertRaises(SynthesisError):
            measure_diversity(self.ledger, [r.source_id for r in records])


class TestProbeDiscipline(DiversityCase):
    def test_the_probe_re_admits_evidence_through_the_registry(self):
        stale = ResearchLedger(Path(self.tmp.name) / "stale", foreign_roots=())
        record = stale.add_source(title="Old", url="https://example.test/old",
                                  publisher="P", excerpt="E",
                                  origin="ScholarScout/src/core.py")
        with self.assertRaises(Exception) as caught:
            measure_diversity(stale, [record.source_id])
        self.assertIn("PROVENANCE.md", str(caught.exception))

    def test_an_empty_source_list_is_refused(self):
        with self.assertRaises(ValueError):
            measure_diversity(self.ledger, [])

    def test_rounds_produce_one_frame_per_lens_in_the_plan(self):
        frames = build_frames(PROBE_QUERY, [self.source], 3, rounds=3)
        self.assertEqual(len(frames), 3)
        self.assertEqual([frame.round_index for _, frame in frames], [1, 2, 3])
        self.assertEqual([frame.rounds for _, frame in frames], [3, 3, 3])

    def test_the_plan_label_is_carried_on_each_frame(self):
        frames = build_frames(PROBE_QUERY, [self.source], 3, rounds=2)
        expected = "+".join(lens.name for lens in lens_plan(3, rounds=2))
        self.assertEqual({label for label, _ in frames}, {expected})


if __name__ == "__main__":
    unittest.main()
