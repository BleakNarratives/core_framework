"""
whorl.core.cascade
──────────────────
Cascade arbitration: decide *per request* whether local inference is eligible,
or the request must escalate to a cloud lane.

Why this exists
---------------
On a small host a local model is not a slower version of a cloud model, it is a
different tool. Measured on the 2.6GiB / 4-core N200 box documented in
docs/LOCAL_INFERENCE_LIMITS_20260926.md:

    llama3.2:1b  -> 4.12 gen tok/s, ~20-25s cold load, answers correctly
    gemma:2b     -> never completed in 300s; 109GB paged out, load avg 13

So the useful question is not "is local up?" (it always is) and not "is local
smarter?" (it is not). It is: *is this particular request one that a 4 tok/s
local model can still do well?*

That is true for classification, routing, extraction and dedup -- short outputs,
tolerant of imperfection, high volume, latency-tolerant in aggregate. It is
false for long-form generation and deep reasoning, where 4 tok/s means a
20-second answer and a wrong one is expensive.

This module therefore gates on *task shape and token budget*, never on
provider preference. That is the whole design: local gets the work it is
actually good at, and escalates the rest instead of thrashing.

Design constraints
------------------
- Pure and offline. No network, no clock, no randomness, no I/O. Every decision
  is a function of its arguments, so arbitration is testable and reproducible
  (AGENTS.md §6). A `HostProfile` carries measured facts; it is data, not a
  probe.
- Advisory, not authoritative. `CascadeDecision.eligible` is a *recommendation*
  to the caller. Nothing here grants or revokes a privilege: Governor remains
  the only authority on what a tier may actually reach (AGENTS.md §5). A
  capability declaration is not permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskShape(Enum):
    """What the caller wants the model to *do*, not which model it wants."""

    CLASSIFY = "classify"          # one label out of a small set
    ROUTE = "route"                # pick a lane / next step
    EXTRACT = "extract"            # pull fields out of given text
    DEDUP = "dedup"                # near-duplicate judgement
    SUMMARIZE_SHORT = "summarize_short"
    GENERATE = "generate"          # open-ended prose
    REASON = "reason"              # multi-step reasoning, chain-of-thought
    CODE_WRITE = "code_write"      # authoring or editing code


class Tier(Enum):
    LOCAL = "local"
    CLOUD = "cloud"


# Shapes a small local model can do acceptably. Everything else escalates.
# This is the load-bearing judgement of the whole module; the reason strings
# below are what make it auditable rather than magical.
LOCAL_ELIGIBLE_SHAPES = frozenset({
    TaskShape.CLASSIFY,
    TaskShape.ROUTE,
    TaskShape.EXTRACT,
    TaskShape.DEDUP,
    TaskShape.SUMMARIZE_SHORT,
})

# Worst-case output tokens a local model may be asked for. At the measured
# ~4 tok/s, 256 output tokens is already a ~60s response, which is the point at
# which the caller is better served by a cloud lane.
LOCAL_MAX_OUTPUT_TOKENS = 256

# Beyond this many input tokens the prompt prefill dominates on a shared core.
LOCAL_MAX_INPUT_TOKENS = 2048


@dataclass(frozen=True)
class HostProfile:
    """Measured facts about one host. Data, not a live probe.

    Defaults describe the documented 2.6GiB / 4-core N200 host. Override for a
    different box rather than assuming -- the whole point is that local
    eligibility is host-specific.
    """

    name: str = "unknown"
    total_ram_mb: int = 0
    available_ram_mb: int = 0
    cpu_cores: int = 0
    has_gpu: bool = False
    # Measured generation throughput for the resident local model, tok/s.
    local_tok_per_s: float = 0.0
    # Measured cold load time, seconds.
    local_load_s: float = 0.0
    local_model_installed: bool = False
    # Measured RESIDENT size of the local model in MB (llama-server RSS), NOT
    # its on-disk blob size. These differ a lot: llama3.2:1b is 1.3GB on disk
    # but measured 505MB resident, and it is the resident figure that decides
    # whether the box thrashes. Using disk size here got it wrong.
    local_model_mb: int = 0

    @property
    def local_usable(self) -> bool:
        """Can this host run a local model at all, as opposed to at what speed?

        Deliberately coarse. A host that cannot hold the model resident is not
        usably local no matter how many cores it has, and that is exactly the
        gemma:2b failure mode: cores were not the constraint, bytes were.
        """
        if not self.local_model_installed or self.cpu_cores <= 0:
            return False
        if self.has_gpu:
            return True
        if self.local_model_mb <= 0:
            # Size unmeasured: we cannot claim the model will stay resident,
            # so we do not claim it is usable. Fail closed, per AGENTS.md §5.
            return False
        return self.available_ram_mb >= self.local_model_mb


@dataclass(frozen=True)
class CascadeRequest:
    """One unit of work being routed."""

    shape: TaskShape
    input_tokens: int = 0
    # What the caller asked for. If the caller does not know, the local
    # ceiling applies -- never assume a big local output is wanted.
    expected_output_tokens: Optional[int] = None
    # A short human-readable note, carried into the decision for auditing.
    note: str = ""


@dataclass
class CascadeDecision:
    eligible: bool
    tier: Tier
    reasons: List[str] = field(default_factory=list)
    # Estimated local seconds, when a local decision was possible. Lets a
    # caller with a hard deadline escalate on its own terms.
    estimated_local_s: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible,
            "tier": self.tier.value,
            "reasons": list(self.reasons),
            "estimated_local_s": self.estimated_local_s,
        }


def estimate_local_seconds(request: CascadeRequest, profile: HostProfile) -> Optional[float]:
    """Rough wall-clock for a local attempt, or None if it cannot be estimated."""
    if profile.local_tok_per_s <= 0:
        return None
    out_tokens = (
        request.expected_output_tokens
        if request.expected_output_tokens is not None
        else LOCAL_MAX_OUTPUT_TOKENS
    )
    # Load is paid once per residency window; include it so a single short
    # call is not flattered by amortization the caller will not see.
    return round(profile.local_load_s + (out_tokens / profile.local_tok_per_s), 2)


def arbitrate(request: CascadeRequest, profile: HostProfile) -> CascadeDecision:
    """Decide whether `request` may run locally. Pure; no I/O.

    Escalation is always justified in `reasons` -- a decision that cannot be
    explained after the fact is not one to act on.
    """
    reasons: List[str] = []

    if not profile.local_usable:
        return CascadeDecision(
            eligible=False,
            tier=Tier.CLOUD,
            reasons=[f"host {profile.name!r} cannot run a resident local model"],
        )

    if request.shape not in LOCAL_ELIGIBLE_SHAPES:
        reasons.append(
            f"shape {request.shape.value!r} is not local-eligible; "
            f"open-ended output at measured throughput produces a slow and "
            f"unreliable answer"
        )

    budget = (
        request.expected_output_tokens
        if request.expected_output_tokens is not None
        else LOCAL_MAX_OUTPUT_TOKENS
    )
    if budget > LOCAL_MAX_OUTPUT_TOKENS:
        reasons.append(
            f"expected output {budget} tok exceeds local ceiling "
            f"{LOCAL_MAX_OUTPUT_TOKENS}"
        )

    if request.input_tokens > LOCAL_MAX_INPUT_TOKENS:
        reasons.append(
            f"input {request.input_tokens} tok exceeds local ceiling "
            f"{LOCAL_MAX_INPUT_TOKENS}"
        )

    est = estimate_local_seconds(request, profile)

    if reasons:
        return CascadeDecision(eligible=False, tier=Tier.CLOUD, reasons=reasons)

    return CascadeDecision(
        eligible=True,
        tier=Tier.LOCAL,
        reasons=[
            f"shape {request.shape.value!r} is local-eligible",
            f"within token ceilings (in {request.input_tokens} / out {budget})",
        ],
        estimated_local_s=est,
    )


def arbitrate_batch(
    requests: List[CascadeRequest], profile: HostProfile
) -> List[CascadeDecision]:
    """Arbitrate a batch, preserving order. Each request is decided alone."""
    return [arbitrate(r, profile) for r in requests]


def measured_n200_profile() -> HostProfile:
    """The documented 2.6GiB N200 host, for tests and docs.

    Values are the measurements recorded in
    docs/LOCAL_INFERENCE_LIMITS_20260926.md. `available_ram_mb` reflects the
    state with the agent stack resident, which is the state that actually
    matters -- it is why gemma:2b failed and llama3.2:1b worked.
    """
    return HostProfile(
        name="n200-2g",
        total_ram_mb=2662,
        available_ram_mb=740,
        cpu_cores=4,
        has_gpu=False,
        local_tok_per_s=4.12,
        local_load_s=20.6,
        local_model_installed=True,
        # Measured llama-server RSS with llama3.2:1b resident, not the 1.3GB
        # on-disk size. 740 >= 505 is why this box runs the 1B model; the same
        # arithmetic against gemma:2b's ~1.6GB is why it could not.
        local_model_mb=505,
    )
