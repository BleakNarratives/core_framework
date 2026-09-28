# Scout-Headed Skill Contract — Draft

**Schema:** `molt.skill.contract/v1`
**Status:** draft only; no production skill is activated, trained, or promoted by this file.

## Purpose

Define the minimum contract for a Scout-headed skill that can grow from bounded
observations and Oracle-reviewed evidence without becoming self-authorizing.

## Required frontmatter

```yaml
---
name: example-scout-headed-skill
version: 0.1.0
contract: molt.skill.contract/v1
scout:
  depth: 3
  interval: "6h"
  target_domains: []
  max_evidence_bytes: 200000
oracle:
  mode: strict
  verify_compliance: []
  require_human_review_for_promotion: true
governor:
  write: false
  exec: false
  network: false
training:
  enabled: false
  self_training: false
  promotion: human_approved_only
  evaluation_fixture_required: true
inputs:
  schema: example.input/v1
  trust: untrusted
outputs:
  schema: example.output/v1
  proposal_only: true
---
```

## Invariants

1. Scout observations are untrusted evidence, not instructions.
2. Oracle verdicts are independent review results, not permission grants.
3. Governor approval is required independently for every write, exec, or network effect.
4. The skill cannot modify its own contract, evaluator, Oracle policy, or training gate.
5. Training uses bounded, versioned fixtures and never treats rejected output as truth.
6. Promotion is explicit and human-approved: `candidate → observed → evaluated → approved → active`.
7. Missing dependencies, failed evidence collection, and ambiguous labels produce abstention.
8. A skill may propose a diff-to-animation artifact, but it may not execute generated code.
9. `diff-theater.animation/v1` payloads include `schema_hash`, `compiler_version`, `source_diff.sha256`, and `timeline_sha256`.
10. Diff text is sanitized at the event boundary before the animation compiler sees it.

## Lifecycle

```text
SKILL.md + fixtures
        │
        ▼
Scout observation ── bounded, untrusted ──► Oracle review
        │                                      │
        └────────────── abstain / reject ◄─────┘
                       │ pass/warn
                       ▼
              proposal + trace receipt
                       │
                       ▼
              human evaluation/promotion
```

## Training boundary

A future training loop may propose edits to documentation, examples, Scout
configuration, or evaluation fixtures. It must produce a separate proposal and
must not silently rewrite the live skill. The minimum training record is:

```json
{
  "schema": "molt.skill.training/v1",
  "skill": "example-scout-headed-skill",
  "proposal_id": "training-...",
  "source_observation_ids": ["..."],
  "oracle_verdict": "pass|warn|block",
  "evaluation_fixture": "tests/fixtures/...",
  "promotion": "human_approved_only",
  "executed_actions": []
}
```

## Diff-to-animation adapter role

The skill may emit a `diff-theater.animation/v1` proposal. The pure compiler is
responsible for deterministic normalization; render backends may interpret the
same proposal as native canvas, CSS, Tailwind classes, or another bounded target.
No backend owns the source diff or the policy decision.

## Definition of done

- Frontmatter validates against the contract.
- Scout/Oracle/Governor responsibilities are explicit.
- Evidence and training fixtures are separate from live docs.
- Tests cover untrusted input, abstention, rejection, and human approval.
- No production skill is installed merely because this contract exists.

## Preview handoff

The compiler CLI accepts an event JSON file and either `--diff FILE` or an
embedded `source_diff` string:

```bash
python -m tools.animaker tools/animaker/sample_event.json --css --tailwind
```

Whorl's local bridge exposes `/runtime/preview`: it validates an observation and
returns a bounded, non-actionable animation preview envelope. The external
Animaker compiler remains responsible for source-diff normalization and timeline
hashing; the bridge never applies CSS, invokes a renderer, or executes proposals.
