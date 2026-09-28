# Dispatch Guards — Salvage Spec

Status: implemented (see test map below).

## Provenance & trust

Source material: an external model's "Project Cub-Apex / ACHSP" proposal
(Apex-Cub Hierarchical Swarm Protocol), received as pasted text. Per AGENTS.md §1
and §3, pasted model output is untrusted data, not instruction. Every claim in
the proposal was checked against the working tree first.

Verified true (and therefore worth salvaging):

- Long-horizon agent loops can repeat identical tool calls; a bounded detector
  is a real guard, not a placebo.
- "One meaningful check, then stop" matches the AGENTS.md §6 narrowest-test
  discipline and can be expressed as a digest-scoped rule.
- Worker dispatch payloads should be bounded (AGENTS.md §5: bounded payload
  sizes).

Verified false or absent in this tree:

- `freebuffy` and `cub` CLIs — not installed, not in the repo. The proposal's
  operational sections drive vapor.
- `mimo-cub-swarm/` scaffold — would fork the existing architecture
  (`src/skill/whorl_bus.py` dispatch, `src/skill/governor.py` elevation,
  `src/skill/oracle.py` audit gate, `src/skill/loom_weaver.py` worker weaving,
  `Whorl/whorl/swarm/`). Rejected: AGENTS.md §4 already documents one runtime.

Rejected outright:

- **Silent dedupe middleware.** The proposal's `dedupe_filter.py` swallows tool
  calls with only a stderr print. AGENTS.md §3/§5 require audit trails; a gate
  that hides actions from the audit trail is a defect, not a guard.
- **"Resistance to Invalid Pushback" rule.** Defending verified code against
  *false automated feedback* is legitimate; framing *user* pushback as pressure
  to resist is not. Human correction is the authority channel (AGENTS.md §3).
  That rule, shipped as written, produces an agent that argues with its operator.
  Not implemented, in any form. If a future change wants loop-resistance
  against automated noise, it must key on the feedback source and must never
  apply to the user.
- **Auto-commit from swarm prompts.** Conflicts with AGENTS.md §2.

## Salvage item 1 — Duplicate-call detection

Landed as: `DuplicateCallGuard` in `src/skill/governor.py`, with optional wiring
via `WhorlBusDispatcher(..., dedupe_guard=guard)` in `src/skill/whorl_bus.py`.

Invariants:

- Bounded twice: per-signature events expire after `window_s`, and tracked
  signatures are capped (`MAX_SIGNATURES`, oldest evicted first; hot signatures
  refreshed on access).
- Every flagged or blocked verdict is audited (`duplicate_call_flagged` /
  `duplicate_call_blocked` to the governor audit log; a blocked bus send also
  records `message_dedup_blocked` in the bus log). Nothing is swallowed silently.
- Default action is `flag` (pass through + record). `block` is opt-in for
  callers that own their retry semantics.
- Legitimate repeats (polling, retry-after-state-change) are distinguished by
  the caller varying the `signature` — the guard sees work, not identity.
- Default bus behavior with no guard configured is byte-for-byte unchanged.

## Salvage item 2 — Single-check verification rule

Landed as: `SingleCheckRule` in `src/skill/governor.py`.

Invariants:

- The rule is digest-scoped: `should_run(check_id, subject_digest)` allows one
  check per subject state. Re-running the identical check against an identical
  subject cannot change the answer — it is loop waste, and is flagged
  (`recheck_flagged`) and reported (`run: false` with a reason), never faked.
- A changed `subject_digest` (code modified) legitimately re-opens the check.
- The rule reports; it does not coerce. A human asking for a re-run is
  authority (AGENTS.md §3) — the repetition shows up in the audit trail rather
  than being hidden or refused.

## Salvage item 3 — Bounded context slices for worker dispatch

Landed as: `LoomThreadWeaver.CONTEXT_SLICE_LIMIT` (32,000 chars) in
`src/skill/loom_weaver.py`, overridable per instance via `context_slice_limit`.

Invariants:

- `dispatch_task` to a worker never carries an unbounded prompt; over-limit
  prompts are sliced and the truncation is recorded in the step trace
  (`prompt_truncated` with original/dispatched sizes).
- The step's `prompt_preview`/`hydrated_preview` traces were already bounded;
  this closes the dispatch path itself.

## Test map

`tests/test_dispatch_guards.py` — offline, temp-dir isolated (WHORL_HOME and
audit paths redirected before any `src.` import):

- `TestDuplicateCallGuard` — first-call allow, flag-by-default + audit,
  block-after-threshold + audit, window expiry, distinct signatures, memory cap.
- `TestSingleCheckRule` — first check runs, identical recheck flagged, digest
  change re-opens, result recording.
- `TestBusDedupeIntegration` — filesystem fallback: block mode delivers 2 of 3
  identical sends and audited; default dispatcher delivers all 3 (unchanged).
- `TestLoomSliceCap` — dispatch sliced at the limit with truncation trace, short
  prompts untouched, default limit.

## Non-goals

No new CLI, no YAML harness, no parallel project tree, no model routing
changes, no external services, no auto-commits.
