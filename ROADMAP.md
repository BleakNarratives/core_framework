# Freebuff Agent Handoff & Asymmetric Intel Roadmap

> **Update 2026-10-02 (Buffy):** Tasks 1–3 are **implemented and verified**.
> Test baseline moved from 11 → 27 passing (`python3 -m pytest tests/ -q`).
> The WebSocket transport was also corrected (the previous raw-TCP broadcast
> could not work against the `websockets` backend). See `BUFFY_ASSESSMENT.md`
> for the full evidence table, the backend venv blocker, and remaining gaps.

## Verified System Baseline

- **Backend Broadcast Verified (`PASS`):** `Code-City-Apocalypse/backend/server.py` correctly parses incoming `market_twin` payloads, unwraps `scene = data.get('data')`, and broadcasts spatial parameters to port 8765 without double-wrapping. Mock WebSocket unit test: `messages_sent=1`, `first_type=market_twin`, `PASS`.
- **Autonomous Scout Vehicle:** `core_framework/bin/scout_vehicle.py` executes patrol passes, scores findings via `ScoutLeaderboard`, and outputs valid 3D scene geometry through `MarketTwinTranslator.to_ws_payload()`.
- **Persistent Agent Skill:** `axescout-market-twin.skill` installed at `/home/bleaknarratives/axescout-market-twin.skill` (binary package).
- **Component Layout:** `core_framework/` contains no symlinks and no duplicated canonical source. All launchers are thin `runpy` pointers into existing trees:
  - `launchers/code_city.py` → `Code-City-Apocalypse/code_city_apocalypse.py`
  - `launchers/modmind.py` → `Code-City-Apocalypse/Code_City_Unified/modmind_unified/src/modmind_architect.py`
  - `launchers/vertical_ai.py` → `The-Werkz/Official-Vertical-AI-Boardroom/vertical_ai.py`
  - `launchers/unified.py` → coordinated subprocess launcher
- **Canonical Fix Applied:** `The-Werkz/Official-Vertical-AI-Boardroom/core/capability_slots.py` had an `IndentationError` on line 158 that blocked all real Vertical AI imports. Fixed. Real pipeline now importable: `core.boardroom`, `core.simulator`, `core.genetics`, `router`.

## Freebuff Task List

### 1. Daemon & Subshell Hardening
- Configure non-blocking launcher scripts for `server.py` so agents running in CLI sandboxes do not hang waiting for open stdout/stderr file descriptors.
- Standardize virtual environment imports (`.venv`) across all executable tools in `core_framework/launchers/` and `core_framework/bin/`.
- Preferred venv paths on this workspace:
  - `/home/bleaknarratives/passive_income_swarm-env/`
  - `/home/bleaknarratives/Skin-Deep/.venv/`
  - `/home/bleaknarratives/The-Werkz/EquiNex-Universal-Dashboard/.venv/`

### 2. Asymmetric Medium-Agnostic Scoring Engine (`ScoutLeaderboard` Upgrade)
File: `core_framework/bin/scout_vehicle.py`

Implement weighted scoring formula:
```
Points = Base Value * Difficulty Multiplier * Confidence * Novelty
```

| Source | Base Multiplier | Base Points |
|--------|----------------|-------------|
| Regulatory / SEC Filings (Gemini CLI filings) | `3.5x` | `50` |
| Real-time Social / News (Vibe CLI news) | `1.0x` | `10` |

Additional rules:
- **Cross-Medium Verification Bounties:** `+100 pts` when a deep filing agent confirms a high-speed news agent's early signal.
- **Signal Decay & Noise Penalties:** `-20 pts` for unverified false positives.
- **Novelty:** Track `seen_signals` fingerprints; already implemented. Weight by time-since-last-seen.

### 3. Commercial Data Exporters
Decouple `ScoutVehicle` output into dual streams:
- **3D Spatial Payloads** — consumed by `MarketTwinTranslator` → `broadcast_market_twin()` → browser viewport on port 8765.
- **CSV / JSON Alpha Streams** — distress intelligence export for PE / CISO buyers.

Suggested export paths:
- `/home/bleaknarratives/core_framework/output/market_twin.json`
- `/home/bleaknarratives/core_framework/output/alpha_stream.csv`

## Next Steps for Freebuff Agent (completed 2026-10-02)
1. ~~Task 1 (daemon hardening)~~ — **DONE.** `unified.py` gained `--detach`
   (own session, stdin closed, logs to `logs/<system>.log`, returns with PIDs)
   plus `--arg` forwarding; `shared/config.py` resolves venv site-packages.
2. ~~Task 2 (scoring engine)~~ — **DONE.** `ScoutLeaderboard.record_finding()`
   applies `Base × Multiplier × Confidence × Novelty`, cross-medium bounty
   (+100), early-predictor bonus (+25), false-positive penalty (−20), and
   agent-scoped deduplication.
3. ~~Task 3 (exporters)~~ — **DONE.** `ScoutVehicle.export_alpha_streams()`
   writes `output/market_twin.json` and `output/alpha_stream.csv`.

### Remaining (status after the 2026-10-02 follow-up)
4. ~~Backend venv blocker~~ — **FIXED.** The `websockets` import now happens after
   a pre-import `sys.path` probe; verified starting on the bare interpreter.
5. ~~TTL/expiry for `pending_signals`~~ — **FIXED** (3-day default, tested).
6. **Memory persistence across runs** — still open (see Track 2).
7. **Kernel decision** — choose GossipBus as the single bus; route producer →
   viewport through MOLT/Overseer (`DESIGN_INTENT_ASSESSMENT.md` §4/§6).

---

## Track 2 — Free-Cloud Adaptive Scouting (opened 2026-10-02)

Blueprint source: `CLOUD_ADAPTIVE_BLUEPRINT.md` (Gemini co-architecture +
Buffy assessment). Goal: an event-driven, self-adapting scout loop that can run
on free-tier infrastructure without keeping the Chromebook open.

### Done this session
- **One-shot entrypoint** — `domino.sh` (root wrapper) → `core_framework/bin/domino.sh`
  (canonical, modular): `all | preflight | serve | stop | patrol | broadcast |
  plan | status | skill`. Fires preflight → backend → ingest → score → translate
  → export → WebSocket broadcast → status, offline by default. Verified E2E on an
  isolated port (5 findings, 5 buildings, broadcast OK, artifacts written).
- `scout_vehicle` is now a CLI (`--ingest NAME=PATH`, `--live`, `--export`,
  `--plan`, `--broadcast`); `fixtures/` holds the offline demo findings.
- `shared/adaptive_memory.py` — pheromone memory (record → reward → exponential
  decay → epsilon-greedy `plan()`); stdlib only, no network.
- `tests/test_adaptive_memory.py` — 8 deterministic tests.
- `ScoutVehicle.plan_adaptive_watchlist()` / `record_adaptive_yields()` — optional
  hooks, no-op unless an `AdaptiveQueryMemory` is attached.
- `adapters/ingest_adapter.py` — offline ingestion: binds the existing
  `tools/ingest/trend_scraper.py` `LocalJsonSource` contract to AxeScout-shaped
  findings; `ScoutVehicle.run_ingested_patrol()` closes the loop offline.
- `tests/test_ingest_adapter.py` — 6 tests incl. full network-free E2E loop.
- `.github/workflows/scout_cron.yml` — dispatch-first Actions template; schedule
  commented until ingestion exists.
- **Leaderboard driver** — `./domino.sh leaderboard` runs the offline fixtures
  pass and prints the live leaderboard queue. Verified: 5 findings, +414 pts on
  a first run, 5 buildings / 4 monsters, artifacts in `output/`.
- **Duplicate consolidation** — `sprawl_scan.py --consolidate [--apply]`
  classifies identical families (`MIRROR` / `CONFIG` / `SNAPSHOT` / `REVIEW` /
  `SAFE`) and collapses **only** `SAFE` strays, backing each up to
  `~/.sprawl_backup/<stamp>/` first. Applied 3 strays; left 40 multi-project
  mirrors, 1 agent-config family, 3 workspace snapshots, and 2 cross-project
  families untouched.
- `DESIGN_INTENT_ASSESSMENT.md` — TempleOS-intent gap analysis + tool inventory.

### Next (ordered, smallest first)
1. ~~**Mock ingestion adapter**~~ — **DONE**, and it reuses the canonical
   `trend_scraper` scaffold rather than a parallel mock (see above).
2. **Memory persistence** — commit-back the memory file, or mirror
   `AdaptiveQueryMemory.to_dict()` into a managed DB (Gravity recommends a
   forever-free managed DB; see `CLOUD_ADAPTIVE_BLUEPRINT.md` §4).
3. **Live ingestion** — network-gated sources exist (`adapters/live_sources.py`,
   SEC EDGAR). Next: verify **one** source end-to-end with network +
   `SEC_USER_AGENT`, then add the Gemini/Vibe CLI path behind secrets. Do this
   before any demo; the parser is tested but no live request has been made.
4. **Outreach** — secret-guarded webhook step already templated; must never
   send unverified data and must not publish alpha to public artifacts.

### Hard constraints
- Ephemeral runners do not persist state between runs — a "learning" loop must
  persist memory or it forgets every run.
- Fetched/scout content is untrusted input; keep the Oracle/Governor boundary.
- No secrets in the tree; no alpha export to public artifacts.

## Session Boundary
This file is the handoff boundary. Files changed in this session:
- `core_framework/adapters/district_schema.py`
- `core_framework/adapters/market_twin.py`
- `core_framework/bin/scout_vehicle.py`
- `core_framework/launchers/code_city.py`
- `core_framework/launchers/modmind.py`
- `core_framework/launchers/unified.py`
- `core_framework/launchers/vertical_ai.py`
- `core_framework/launchers/market_twin.py`
- `core_framework/shared/config.py`
- `core_framework/tests/test_smoke.py`
- `core_framework/tests/test_config.py`
- `Code-City-Apocalypse/backend/server.py`
- `The-Werkz/Official-Vertical-AI-Boardroom/core/capability_slots.py` (canonical syntax fix)

Standing down for the session.

## Session Boundary — 2026-10-02 (Buffy / Freebuff)
Files changed in this later session:
- `core_framework/shared/config.py`
- `core_framework/launchers/unified.py`
- `core_framework/bin/scout_vehicle.py`
- `core_framework/adapters/market_twin.py`
- `core_framework/tests/test_config.py`
- `core_framework/tests/test_scoring_engine.py` (new)
- `core_framework/tests/test_exporters.py` (new)
- `core_framework/tests/test_launcher.py` (new)
- `core_framework/shared/adaptive_memory.py` (new — Track 2)
- `core_framework/tests/test_adaptive_memory.py` (new — Track 2)
- `core_framework/adapters/ingest_adapter.py` (new — Track 2)
- `core_framework/tests/test_ingest_adapter.py` (new — Track 2)
- `core_framework/tests/conftest.py` (new — pytest path bootstrap)
- `core_framework/.github/workflows/scout_cron.yml` (new — Track 2)
- `core_framework/.gitignore` (new)
- `core_framework/BUFFY_ASSESSMENT.md` (new)
- `core_framework/CLOUD_ADAPTIVE_BLUEPRINT.md` (new)
- `core_framework/DESIGN_INTENT_ASSESSMENT.md` (new)
- `core_framework/bin/domino.sh` (new — canonical one-shot orchestrator)
- `core_framework/fixtures/{sec_filings,news_feed}.json` (new — offline demo)
- `core_framework/tests/test_cli.py` (new)
- `core_framework/bin/sprawl_scan.py` (new — doc-sprawl map + triage planner)
- `core_framework/tests/test_sprawl_scan.py` (new)
- `~/SPRAWL_INDEX.md`, `~/SPRAWL_TRIAGE.md`, `~/SPRAWL_CONSOLIDATE.md` (generated at the repo root; gitignored, regenerable via `./domino.sh sprawl` / `--consolidate`)
- `tools/ingest/__init__.py` (new — package marker so the offline importer resolves)
- `~/domino.sh` (new — root wrapper; ignored by the home repo's `/*` rule)

No canonical *source* tree modified. 64/64 tests pass; WebSocket transport
verified against the live backend on an isolated localhost port.
