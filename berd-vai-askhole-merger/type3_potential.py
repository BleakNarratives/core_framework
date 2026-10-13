"""Type III force-multiplier ideas for cross-using this workbench's assets.

These are brainstorming prompts, not scores, recommendations, or claims about a
lead. They never initiate an external action and intentionally require human
verification before any customer-facing use.
"""
from __future__ import annotations

from typing import Any


POTENTIALS = (
    {
        "id": "intake-leak-map",
        "title": "Intake Leak Map",
        "combination": "Vertical AI lead evidence + AskHole's vertical frame + Berd's hostile review",
        "potential": "Turn verified operating evidence into a short list of intake questions, while keeping facts separate from hypotheses.",
        "first_test": "For one lead, manually verify a concrete intake or response issue; draft questions only, then have Hostile Reviewer challenge every factual claim.",
        "gate": "Do not infer missed calls, lost revenue, or an intake problem from a rating or business category.",
    },
    {
        "id": "review-to-intake",
        "title": "Review Signal → Intake Question",
        "combination": "Dated, sourced review evidence + a vertical-specific question + compliance review",
        "potential": "Translate a verified public service theme into a neutral question the business can answer, rather than an accusation or fabricated personalization.",
        "first_test": "Manually add one current, policy-compliant review with its source and date; ask whether a related intake process is worth discussing.",
        "gate": "Review counts and star ratings are not review themes. The workbench does not scrape reviews.",
    },
    {
        "id": "reusable-vertical-playbook",
        "title": "Reusable Vertical Playbook",
        "combination": "Verified evidence across leads + provenance-labeled economics + a Berd skill reviewed by a second persona",
        "potential": "After repeated patterns are confirmed, turn a redacted, human-approved workflow into reusable vertical guidance instead of reinventing each draft.",
        "first_test": "Collect three independently sourced, human-verified workflow observations; redact business identifiers and compare them before proposing a reusable skill.",
        "gate": "The current app does not deduplicate or anonymize records. Do not pool unverified notes or personal data.",
    },
)


def get_type3_potentials(lead: dict[str, Any], evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return exactly three conceptual, non-scored use cases for the project.

    The supplied lead/evidence establish the UI context only. Potential text is
    intentionally not personalized from unverified lead claims.
    """
    if not isinstance(lead, dict) or not isinstance(evidence, list):
        raise TypeError("lead must be a mapping and evidence must be a list")
    return [dict(item, status="exploratory—not scored", external_action="disabled") for item in POTENTIALS]
