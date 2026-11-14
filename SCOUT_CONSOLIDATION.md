# Scout consolidation: decision and safe next steps

## Decision

Use `core_framework` as the sole runtime for scouting. Keep `ChronoScouts` and `Kronos-Scouts` as read-only reference/archive repositories until their unique content is deliberately migrated. Do not delete or rewrite either repository as part of this first pass.

## Evidence from the current trees

- `core_framework` already has the most substantial implementation: normalized ingestion adapters, an SEC live-source adapter, a scoring/export vehicle, adaptive query memory, tests, and a dispatch-first Actions workflow.
- `ChronoScouts` and `Kronos-Scouts` share the same distress-monitoring purpose and near-identical fixture/harness layout. Their harnesses are not equivalent to the core runtime: they initialize SQLite and load fixtures, but do not provide the core scoring/evaluation loop. ChronoScouts also has a generated HTML artifact and decay script; Kronos-Scouts has an AxeScout adapter and sample digest. Preserve these as candidate assets rather than assuming they are disposable.
- `core_framework/adapters/axe_scout_spec.py` and `Kronos-Scouts/adapters/axe_scout_spec.py` have the same Git blob SHA, so that adapter is already byte-identical across those repos.
- `Vigil` is a broader agent SDK with integrity/audit and self-modification areas. Treat it as a possible verification boundary, not a financial-scout runtime dependency.

## Consolidation boundary

1. Keep ingestion, normalization, scoring, evaluation, reports, and scheduled orchestration in `core_framework`.
2. Port only demonstrably unique value from ChronoScouts/Kronos-Scouts: report presentation, domain-specific schema/adapter improvements, or useful labeled fixtures. Keep source attribution and provenance with every imported item.
3. Remove checked-in generated databases and bytecode from any future active runtime; generate them at run time and ignore them.
4. Add archive notices/pointers to the prototype repositories only after the canonical runtime has equivalent, tested behavior. Do not delete repository history.

## Automation: safe first stage

The existing `.github/workflows/scout_cron.yml` correctly remains dispatch-first. It currently invokes the demo path unless given ingestion arguments; a schedule that repeatedly scores the demo would create misleading activity, not learning. Do not enable a cron until a real, bounded source-to-report path and durable state are present.

Before enabling an unattended run, make it:

- ingest actual source items with rate limits, a clear user-agent, and explicit source attribution;
- persist run IDs, source evidence, predictions, and later adjudicated outcomes somewhere that survives ephemeral Actions runners;
- avoid treating leaderboard points, signal volume, or model confidence as predictive accuracy;
- evaluate with time-separated labeled outcomes and report precision, recall, false-positive rate, and calibration;
- upload reports as artifacts first; notify externally only behind an explicit secret and opt-in;
- propose rule/model changes as a PR after benchmark checks—never let the cron silently edit or deploy its own code.

## Revenue test

Do not market unvalidated distress predictions as reliable investment advice. A small pilot for traceable monitoring briefs is a more testable first offer: a narrow customer group, cited public sources, explicit uncertainty, a sample deliverable, and a willingness-to-pay test before building more infrastructure.

## Immediate next engineering milestones

1. Add regression tests for fixture ingestion through `core_framework` and report export.
2. Add a stable event/run ledger and a small labeled evaluation fixture; compute metrics from outcomes, not internal scores.
3. Migrate only one unique Chrono/Kronos asset at a time, retaining provenance and tests.
4. Run scheduled fixture-only CI as a smoke test; keep live ingestion manual until rate limits, persistence, and evaluation are verified.
