"""Diversity measurement for the Foxwood pipe.

WHAT THIS PROVES, AND WHAT IT DELIBERATELY DOES NOT
  The question here is narrow and checkable: *does the pipe ask different questions
  of the same evidence, reproducibly?* It measures framing, not prose, and it calls
  no model.

  That restraint is the point. A model call is not reproducible -- herald measured
  that `bin/ai` without a pinned model rotates gateway pools, so one prompt returns
  different text on different calls -- and an eval built on that measures pool
  selection rather than this code. Framing is what the pipe actually guarantees, so
  framing is what gets measured. If the frames vary and replay exactly, the only
  remaining variable is the model, which is the operator's choice.

THE INVARIANTS, EACH COMPUTED FROM FRAMES THAT WERE ACTUALLY BUILT
  1. REPRODUCIBLE    the same seed twice gives the same plan and the same frame IDs.
  2. LENS-STABLE     a lens's prompt does not depend on the seed. The seed chooses
                     the question; it does not salt it. A salt would make replay
                     depend on luck rather than on a named question.
  3. LENS-DISTINCT   different lenses give different prompts. Two lenses that read
                     the same are one lens with two names, which is how a "varied"
                     pipeline quietly becomes a single-question pipeline.
  4. QUESTION-KEYED  a lens has ONE frame ID across seeds, and two lenses never share
                     one. The seed is not part of a question's identity.
  5. LENS-SPAN       over a realistic seed range, the rotation reaches more than one
                     lens. A seed function that always answered 0 would satisfy every
                     other invariant here and still be perfectly static.
  6. BOUNDED         every frame fits the source cap and the prompt budget.

  Invariants 2, 3 and 4 are the ones that found real defects. The first draft keyed
  frame identity on the seed as well as the lens, so two seeds landing on one lens
  produced two identities for one question and the verdict ledger reported answered
  work as undone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .ledger import ResearchLedger, SourceRecord
from .pipe import (
    LENSES,
    MAX_SOURCES_PER_FRAME,
    PROMPT_CHAR_BUDGET,
    FrameRequest,
    frame_prompt,
    lens_plan,
    plan_label,
)
from .registry import RegistryGate

DEFAULT_SEED_RANGE = tuple(range(12))
PROBE_QUERY = "(diversity probe -- framing only, no model is called)"


@dataclass
class DiversityReport:
    """What the probe found, in the form a human checks."""

    seeds: Tuple[int, ...]
    frames_built: int
    lenses_reached: Tuple[str, ...]
    frames_per_lens: Dict[str, int]
    distinct_prompts_per_lens: Dict[str, int]
    unstable_seeds: Tuple[int, ...] = ()
    prompt_drift: Tuple[str, ...] = ()
    duplicate_lens_text: Tuple[str, ...] = ()
    split_identities: Tuple[str, ...] = ()
    shared_identities: Tuple[str, ...] = ()
    unspanned_lenses: Tuple[str, ...] = ()
    budget_violations: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """Every invariant held. A static or unreproducible pipe fails here."""
        return not (self.unstable_seeds or self.prompt_drift or self.duplicate_lens_text
                    or self.split_identities or self.shared_identities
                    or self.unspanned_lenses or self.budget_violations)

    @property
    def verdict(self) -> str:
        return "varied and reproducible" if self.ok else "STATIC OR UNREPRODUCIBLE"

    def failures(self) -> Tuple[str, ...]:
        lines: List[str] = []
        if self.unstable_seeds:
            lines.append(f"the same seed produced a different plan: {list(self.unstable_seeds)}")
        if self.prompt_drift:
            lines.append(f"a lens's prompt changed with the seed: {list(self.prompt_drift)}")
        if self.duplicate_lens_text:
            lines.append(f"two lenses produced identical prompts: {list(self.duplicate_lens_text)}")
        if self.split_identities:
            lines.append(f"one lens carried more than one frame ID: {list(self.split_identities)}")
        if self.shared_identities:
            lines.append(f"two lenses shared a frame ID: {list(self.shared_identities)}")
        if self.unspanned_lenses:
            lines.append(f"no seed reached: {list(self.unspanned_lenses)}")
        lines.extend(self.budget_violations)
        return tuple(lines)

    def to_markdown(self) -> str:
        span = f"{self.seeds[0]}..{self.seeds[-1]}" if self.seeds else "-"
        lines = [
            "# Foxwood pipe diversity",
            "",
            f"- Verdict: **{self.verdict}**",
            f"- Seeds probed: {len(self.seeds)} ({span})",
            f"- Frames built: {self.frames_built}",
            f"- Lenses reached: {len(self.lenses_reached)} of {len(LENSES)} "
            f"({', '.join(self.lenses_reached) or 'none'})",
            "- Frames per lens: "
            + (", ".join(f"{name}={count}" for name, count in sorted(self.frames_per_lens.items()))
               or "none"),
            "- Distinct prompts per lens (exactly one each is the contract): "
            + (", ".join(f"{name}={count}"
                         for name, count in sorted(self.distinct_prompts_per_lens.items()))
               or "none"),
            f"- Same seed replays exactly: {'yes' if not self.unstable_seeds else 'NO'}",
            f"- Bounds: {MAX_SOURCES_PER_FRAME} sources, {PROMPT_CHAR_BUDGET} chars",
        ]
        problems = self.failures()
        if problems:
            lines += ["", "## Failures"]
            lines += [f"- {problem}" for problem in problems]
        else:
            lines += ["", "Every invariant held: the same seed replays byte for byte, "
                          "different seeds reach different questions, and nothing "
                          "exceeded its bound."]
        lines += ["", "## Notes"]
        lines += [f"- {note}" for note in self.notes] or ["- (none)"]
        lines.append("")
        return "\n".join(lines)


def build_frames(
    query: str, sources: Sequence[SourceRecord], seed: int, rounds: int = 1,
) -> Tuple[Tuple[str, FrameRequest], ...]:
    """One seed's whole plan, framed: ((plan label, frame), ...).

    Always frames against the real budget, because that bound is the one the pipe
    enforces. A stricter bound passed to the probe is reported as reduced headroom
    rather than raising here -- the probe's job is to report, and it cannot report
    what it refused to build.
    """
    plan = lens_plan(seed, rounds, None)
    label = plan_label(plan)
    return tuple(
        (label, frame_prompt(lens, query, sources, seed=seed,
                             round_index=index, rounds=len(plan)))
        for index, lens in enumerate(plan, start=1)
    )


def measure_diversity(
    ledger: ResearchLedger,
    source_ids: Iterable[str],
    *,
    query: str = PROBE_QUERY,
    seeds: Iterable[int] = DEFAULT_SEED_RANGE,
    rounds: int = 1,
    registry: Optional[Any] = None,
    budget: int = PROMPT_CHAR_BUDGET,
) -> DiversityReport:
    """Probe the pipe's framing for variety and replayability. Calls no model.

    The evidence is re-admitted through the registry gate first, so a diversity
    report can never be produced over evidence the pipe would refuse to frame.
    """
    ids = list(dict.fromkeys(source_ids))
    if not ids:
        raise ValueError("at least one source is required")
    sources = [ledger.get_source(source_id) for source_id in ids]
    gate = registry if registry is not None else RegistryGate()
    for source in sources:
        gate.admit(source.origin, source.url)

    seed_list = tuple(int(seed) for seed in seeds)
    frames_per_lens: Dict[str, int] = {}
    prompt_seen: Dict[str, set] = {}
    identity_seen: Dict[str, set] = {}
    budget_violations: List[str] = []
    unstable: List[int] = []
    frames_built = 0

    for seed in seed_list:
        first = build_frames(query, sources, seed, rounds)
        repeat = build_frames(query, sources, seed, rounds)
        if tuple(frame.frame_id for _, frame in first) != \
                tuple(frame.frame_id for _, frame in repeat):
            unstable.append(seed)
        for _, frame in first:
            frames_built += 1
            over = frame.budget_reason(budget)
            if over:
                budget_violations.append(over)
            prompt_seen.setdefault(frame.lens, set()).add(frame.prompt)
            identity_seen.setdefault(frame.lens, set()).add(frame.frame_id)
            frames_per_lens[frame.lens] = frames_per_lens.get(frame.lens, 0) + 1

    prompt_drift = tuple(sorted(name for name, seen in prompt_seen.items() if len(seen) > 1))
    split_identities = tuple(sorted(name for name, seen in identity_seen.items() if len(seen) > 1))

    # Two lenses that produced the same prompt text, or the same frame ID.
    duplicate_text: List[str] = []
    shared_ids: List[str] = []
    names = sorted(prompt_seen)
    for index, left in enumerate(names):
        for right in names[index + 1:]:
            if prompt_seen[left] == prompt_seen[right] and left not in duplicate_text:
                duplicate_text.append(left)
            if identity_seen[left] == identity_seen[right] and f"{left}={right}" not in shared_ids:
                shared_ids.append(f"{left}={right}")

    reached = tuple(names)
    notes = [
        "no model was called: this measures the question, because the answer is the "
        "part that is not deterministic through a rotating gateway",
        "a seed is how a plan is chosen, never part of what a question is; that is "
        "why two seeds reaching one lens share a frame ID by design",
        f"{len(LENSES)} lenses ship, so a seed range reaching one of them is exactly "
        "the static-pipe failure this probe exists to catch",
    ]

    return DiversityReport(
        seeds=seed_list,
        frames_built=frames_built,
        lenses_reached=reached,
        frames_per_lens=frames_per_lens,
        distinct_prompts_per_lens={name: len(seen) for name, seen in prompt_seen.items()},
        unstable_seeds=tuple(unstable),
        prompt_drift=prompt_drift,
        duplicate_lens_text=tuple(duplicate_text),
        split_identities=split_identities,
        shared_identities=tuple(shared_ids),
        unspanned_lenses=tuple(lens.name for lens in LENSES if lens.name not in prompt_seen),
        budget_violations=tuple(budget_violations),
        notes=tuple(notes),
    )
