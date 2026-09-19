# Vertical AI Artifact and Secret Boundary Policy

**Scope:** `vertical_ai`, `vertical_local`, `vertical_radar`,
`vertical_radar_dupe`, `vertical_ai_engine`, and
`The-Werkz/Official-Vertical-AI-Boardroom`.

This policy is for organization and migration work. It does not authorize moving,
deleting, publishing, or rotating any credential.

## Boundary rules

1. **Source is code and configuration templates only.** Python, package metadata,
   tests, documentation, and redacted example data may move into a source
   destination.
2. **Generated artifacts stay out of source migrations.** Logs, reports, session
   JSON, HTML debriefs, CSV exports, databases, caches, model outputs, and runtime
   journals require separate retention decisions.
3. **Secrets never enter manifests or reports.** Record variable names and the
   external secret source, never values, key suffixes, vault contents, or `.env`
   bodies.
4. **Historical evidence is immutable by default.** Do not rewrite old manifests,
   logs, snapshots, or duplicate workspaces merely to make paths look current.
5. **Nested Git repositories remain separate boundaries** until their histories,
   owners, and tests have been explicitly mapped.
6. **Offline checks must not read secrets or contact services.** Missing optional
   packages are reported as skipped/blocked, not silently installed or replaced.

## Workspace dispositions

| Workspace | Source-safe material | Generated/runtime boundary | Secret boundary |
|---|---|---|---|
| `vertical_ai` | `scrape_google_reviews.py`, `automate_outreach.py`, tests, manifest, README | `businesses_without_websites.csv` and scraped HTML/results | external concierge vault; SMTP credentials must never be in CSV or tests |
| `vertical_local` | FastAPI code, debate engine, web source, manifest, tests | `data/`, service logs, PID files, local UI build output | `OPENAI_API_KEY`, `HF_API_KEY`; request payloads may contain user data |
| `vertical_radar` | `src/`, requirements, package markers, tests, manifest, docs | `src/data/report_*.txt`, search/scrape responses, caches | `GOOGLE_API_KEY`; `.env` is quarantined and never copied |
| `vertical_radar_dupe` | provenance notes and source comparison only until disposition | entire duplicate tree is historical evidence | `.env`-like files remain quarantined |
| `vertical_ai_engine` | modules, CLI, requirements, tests, manifest, redacted docs | processed documents, logs, rendered reports, model responses | `GEMINI_API_KEY`, `.env`, document contents, database credentials |
| Boardroom | `core/`, `tools/`, `bridges/`, `scouts/`, `shared/`, tests, versioned source, templates | `outputs/`, `logs/`, `data/ingest/`, `data/projects/`, Neo4j cargo, debriefs | `vault_loader`, provider pools, `.env*`, external vaults, integration tokens |

## Migration checklist

Before moving any workspace:

- [ ] Write destination ignore rules before copying source.
- [ ] Exclude `.env*`, vault files, key-shaped names, databases, logs, caches,
      generated reports, and model outputs.
- [ ] Preserve a source hash or path inventory for excluded artifacts without
      copying their contents into the report.
- [ ] Update executable references in the same logical change as source moves.
- [ ] Run offline syntax/import checks in a temporary directory.
- [ ] Run project tests with network and credential paths mocked.
- [ ] Review `git diff --check`, staged paths, and generated-file exclusions.
- [ ] Record rollback source and destination paths before declaring completion.

## Verification language

Reports use these states:

- **PASS:** deterministic check completed locally.
- **SKIP:** intentionally not run because it is live/network/credential dependent.
- **BLOCKED:** cannot run because a declared package or file is missing.
- **HISTORICAL:** evidence retained for provenance, not treated as executable source.

A workspace is not “production-ready” merely because its syntax passes.
