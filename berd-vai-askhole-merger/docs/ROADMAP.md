# Roadmap

## Phase 0 — Local outreach review control room (current)

- [x] State one job: move selected unsent Pytch items into a human-reviewed, manual-export-only local ledger.
- [x] Prove a click-through with disposable Pytch source SQLite, including no raw recipient copy and no source writes.
- [x] Keep project wormholes honest: live only where a read-only local data source is actually queried; other entries are labeled source/reference or handoff-only.
- [x] Implement the tested AIR action-only lens and TILT 35/70/92% signal thresholds without changing underlying project state.

- [x] Clean project root outside existing source trees.
- [x] Lead intake, SQLite state, provenance labels, deterministic draft, review states.
- [x] Local loopback UI and offline test suite.
- [x] Berd project/persona/skill briefs.
- [ ] Attach directory to Berd and confirm its project page opens (Berd-side write is a separate action).

## Phase 1 — Review loop

- Add duplicate detection and reversible lead merge.
- Add evidence/source URL and collected-at fields to import/export; allow a human to mark individual evidence as verified with reviewer and date.
- Add a draft diff and review form that invalidates approval if text/recipient changes.
- Add retention/delete controls and optional encrypted backup instructions.
- Acceptance: offline deterministic tests prove import, deduplication, evidence trust, review, approval invalidation, and deletion.

## Phase 2 — Optional local model

- Add a user-enabled Ollama adapter, default off, targeting only configured `127.0.0.1` endpoint.
- Use the deterministic economics/evidence context as citations; validate report sections and mark all generated statements unverified.
- Add model/time/token limits and a deterministic offline fake.
- Acceptance: no remote traffic in local mode; prompt injection in evidence cannot change system behavior; output has evidence pointers and review status.

## Phase 3 — Read-only lead research

- Select an official, policy-compliant source/API only after reviewing terms and costs.
- Use the project's explicit adapter boundary; provenance, consent/purpose, rate limits, and cached fixtures are mandatory.
- Acceptance: network is off by default; mocks cover failures/limits; no automatic collection of personal contact data.

## Phase 4 — Manual export and possible delivery

- Build CSV/clipboard export first.
- Only consider email or SMS after recipient validation, compliance review, explicit user opt-in, exact-content approval, idempotency, and credentials in a secret store.
- Acceptance: no sending occurs on draft/create/import; tests prove changed text or recipient revokes approval; live transport requires separate opt-in.

## Parked / excluded

- Automatic cold outreach and contact enrichment.
- Mixing Coach Bleak's case-analysis/psychological profiling features into business sales workflows.
- Running arbitrary local agents, shell tools, or “subagents” with broad filesystem/network access.
- Modifying or rebuilding Block's Berd application.
