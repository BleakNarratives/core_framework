# Buffy Assessment — Roadmap Tasks & Gemini Co-Architecture Review

**Author:** Buffy (Codebuff / Freebuff agent, DeepSeek V4.1 Flash)
**Session:** 2026-10-02
**Scope:** `core_framework/` pointer layer, Code City backend, Vertical AI adapter
**Method:** read the actual files, ran the existing suite, added tests, and ran one
live localhost WebSocket integration probe. No network services, no API credits,
no canonical source trees modified.

> This document records what the roadmap and the Gemini session record *propose*
> versus what the code on disk actually does. Claims below are tied to commands
> that were run in this session; anything unverified is labelled as such.

---

## 1. Verdict

| Proposal (ROADMAP / QRD / Gemini citation) | Verdict | Evidence |
|---|---|---|
| Asymmetric medium-agnostic scoring engine | **Works** — implemented + tested | `tests/test_scoring_engine.py` (8 tests) |
| Cross-medium verification bounty (+100) / early-predictor bonus (+25) | **Works** — implemented + tested | `test_cross_medium_bounty_and_early_predictor` |
| False-positive penalty (−20) | **Works** — implemented + tested | `test_false_positive_penalty` |
| Signal decay / novelty weighting | **Works** — implemented + tested | `test_novelty_decays_over_time` |
| Dual-stream exporters (3D JSON + CSV alpha) | **Works** — implemented + verified end-to-end | `tests/test_exporters.py`; `core_framework/output/` written |
| Unified `.venv` / venv resolution | **Works** — resolves real venv (websockets 17.0.1) | `resolve_venv_site_packages("websockets")` |
| Non-blocking / daemon-safe launcher | **Works** — `--detach` | `tests/test_launcher.py` |
| WebSocket broadcast of market twin | **Works** — verified against real backend | integration probe: `RECEIVED market_twin; buildings=1` |
| Live ingestion (network-gated) | **Wired, live call UNVERIFIED** | `adapters/live_sources.py`; parser tested offline |
| Backend starts under bare sandbox interpreter | **Fixed & verified** | starts on port 8767 with no `PYTHONPATH` |
| Pending-signal TTL | **Fixed & tested** | `test_pending_signal_expires_after_ttl` |
| Frontend `renderMarketTwin` viewport | **Not re-verified this session** | see §3.5 |

---

## 2. What works (verified)

### 2.1 Asymmetric scoring engine
`ScoutLeaderboard.record_finding()` now implements the agreed formula:

```
Points = Base Value × Difficulty Multiplier × Confidence × Novelty
```

| Medium | Base | Multiplier | Tier |
|---|---|---|---|
| `filings` / `regulatory` (Gemini CLI) | 50 | 3.5× | deep |
| `news` / `social` (Vibe CLI) | 10 | 1.0× | fast |
| `general` (unclassified) | 25 | 1.5× | general |

Medium is taken from `finding["medium"]` when present, otherwise inferred from
the agent id (`gemini*` → filings, `vibe*` → news).

**Design correction made this session:** deduplication was originally global
(`ticker:type:severity`), which silently suppressed the *legitimate* cross-medium
confirmation — Gemini's filing carried the same fingerprint as Vibe's early
signal and scored 0. Dedup is now **agent-scoped**
(`agent_id::ticker:type:severity`), so one looping agent cannot farm points while
two different agents reporting one signal still score. Legacy list-format
leaderboard files still load and still suppress.

Novelty recovers linearly to full value over 24 h; exact repeats inside a 5 min
window score 0.

### 2.2 Dual-stream commercial exporters
`ScoutVehicle.export_alpha_streams()` writes:
- `output/market_twin.json` — Stream A: 3D spatial payload + scene + leaderboard snapshot
- `output/alpha_stream.csv` — Stream B: per-finding distress intelligence

Verified output (standalone runner, this session):

```
timestamp,agent_id,ticker,scout_type,severity,confidence,medium,points,signals
...,Gemini-Core-Partner,TSLA,distress,CRITICAL,0.92,filings,161,Debt covenants breach
...,Gemini-Core-Partner,NVDA,competitive,WARNING,0.78,filings,136,Custom ASIC displacement
```

### 2.3 Venv resolution & daemon hardening
- `shared/config.py` gains `VENV_CANDIDATES`, `resolve_venv_site_packages()`,
  `inject_venv_paths()`, `OUTPUT_DIR`, `LOG_DIR`, `LEADERBOARD_PATH`.
- `launchers/unified.py` gains `--detach` (own session, stdin closed, logs to
  `logs/<system>.log`, returns immediately with PIDs) and `--arg` forwarding.
  The old `sys.argv[2:]` pass-through bug is gone.

### 2.4 WebSocket transport
`scout_vehicle.py` previously opened a **raw TCP socket** and wrote JSON. The
backend is a `websockets` server, so that could never deliver a market twin.
It now uses a real WebSocket client and degrades gracefully when the server is
down. Verified against the live backend on an isolated port.

---

## 3. What will not work (or is unverified)

### 3.1 Live ingestion is wired but the live call is unverified
`adapters/live_sources.py` now implements network-gated live sources that speak
the same `TrendSource` contract as the offline path, including a SEC EDGAR
full-text source. `allow_network` defaults to **False**, so tests/CI/sandboxes
cannot make live calls by accident. The EDGAR **parser is tested offline**; the
HTTP request itself was **never executed** in this environment and is marked
UNVERIFIED. There is still no code that shells out to Gemini/Vibe CLI; the
delegation model remains an integration contract. Live sources also need
`SEC_USER_AGENT` set.

### 3.2 ~~The backend cannot start under the bare sandbox interpreter~~ — FIXED
`server.py` used to `import websockets` before its venv fallback ran, making the
fallback dead code. The import is now moved after a pre-import `sys.path` probe,
and the duplicate unreachable `await asyncio.Future()` was removed. Verified:
`PORT=8767 python3 server.py` starts on the bare interpreter (no `PYTHONPATH`)
and the port accepts connections.

### 3.3 ~~Pending signals never expire~~ — FIXED
`pending_signals` now carry a TTL (`PENDING_SIGNAL_TTL_SECONDS`, default 3 days),
pruned on load and on every `record_finding`. Covered by
`test_pending_signal_expires_after_ttl`.

### 3.4 `--detach` is fire-and-forget
There is no supervisor: no health check, no restart, no PID file. Detaching
avoids fd hangs; it does not make the systems production-managed.

### 3.5 Frontend viewport not re-verified
The QRD claims `renderMarketTwin` is wired into `rampage-refactor/index.html`.
This session did not open that file. Treat the claim as **stale until checked**.

### 3.6 Real LLM pipeline calls not exercised
`router.ModelTier` and the boardroom/simulator/genetics imports succeed
(`_REAL_IMPORTS = True`), but `run_market_pipeline()` was not executed here
because it would make live model calls. Import-level verification only.

### 3.7 Cosmetic: duplicate unreachable line in `server.py`
`main()` ends with `await asyncio.Future()` twice; the second is unreachable.
Left untouched (canonical tree), noted for whoever owns that file.

---

## 4. Commands actually run

```bash
# baseline + after changes
cd ~/core_framework && python3 -m pytest tests/ -q        # 27 passed

# syntax
python3 -m py_compile <each changed file>                 # all OK

# standalone runner (writes output/, broadcast fails gracefully with no server)
timeout 30 python3 bin/scout_vehicle.py ws://127.0.0.1:59999   # exit=0, 2 rows exported

# verified venv resolution
python3 -c "... resolve_venv_site_packages('websockets') ..."  # passive_income_swarm-env, websockets 17.0.1

# localhost-only integration probe (server started on 8766, killed afterwards)
PORT=8766 python3 server.py & ... websockets.connect(...)      # RECEIVED market_twin; buildings=1
```

---

## 5. Files changed this session

| File | Change |
|---|---|
| `core_framework/shared/config.py` | venv resolution, output/log/leaderboard paths |
| `core_framework/launchers/unified.py` | `--detach`, `--arg`, argv fix, venv injection |
| `core_framework/bin/scout_vehicle.py` | asymmetric scoring, exporters, agent-scoped dedup, WebSocket transport |
| `core_framework/adapters/market_twin.py` | removed dead duplicate `add_axe_scout_finding`, added `Dict` import |
| `core_framework/tests/test_scoring_engine.py` | new — 8 deterministic scoring tests |
| `core_framework/tests/test_exporters.py` | new — exporter tests |
| `core_framework/tests/test_launcher.py` | new — launcher/daemon tests |
| `core_framework/tests/test_config.py` | venv resolution tests |
| `core_framework/.gitignore` | new — ignore caches, logs, exports |

## 6. Track 2 — Free-cloud adaptive scouting (added after the Gemini blueprint)

The Gemini co-architecture blueprint was received after §1–§5 were written. Its
detailed assessment lives in `CLOUD_ADAPTIVE_BLUEPRINT.md`; the local foundation
built this session:

| File | Change |
|---|---|
| `core_framework/shared/adaptive_memory.py` | new — pheromone memory (reward/decay/epsilon-greedy plan), stdlib only |
| `core_framework/tests/test_adaptive_memory.py` | new — 8 deterministic tests |
| `core_framework/bin/scout_vehicle.py` | added optional `plan_adaptive_watchlist()` / `record_adaptive_yields()` / `run_ingested_patrol()` hooks |
| `core_framework/adapters/ingest_adapter.py` | new — offline ingestion binding `tools/ingest/trend_scraper.py` to findings |
| `core_framework/tests/test_ingest_adapter.py` | new — network-free E2E loop tests |
| `core_framework/.github/workflows/scout_cron.yml` | new — dispatch-first Actions template |
| `core_framework/CLOUD_ADAPTIVE_BLUEPRINT.md` | new — what works / what won't |
| `core_framework/DESIGN_INTENT_ASSESSMENT.md` | new — TempleOS-intent gap analysis + tool inventory |

Two blueprint items that will **not** work as written: ephemeral runner storage
means adaptive state is lost every run (persist it, or the "learning" loop just
forgets), and the loop has no live ingestion yet, so cloud cron would export
near-empty streams until an ingestion adapter exists.

The "no live ingestion" gap is now closed **offline**: `ingest_adapter.py` binds the
pre-existing `tools/ingest/trend_scraper.py` scaffold, and
`ScoutVehicle.run_ingested_patrol()` runs the whole adapt → patrol → score →
export loop with no network. Live sources remain stubbed by design.

`Code-City-Apocalypse/backend/server.py` (canonical) was fixed this session for
the `websockets` import order, and its duplicate unreachable `await` removed.
Final test run: `51 passed`.
