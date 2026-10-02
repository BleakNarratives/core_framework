# Free-Cloud Adaptive Scouting Blueprint — Assessment

**Source:** Gemini 3.6 Flash ↔ Bleak Narratives co-architecture session (ChromeOS)
**Assessed by:** Buffy (Codebuff / Freebuff), 2026-10-02
**Method:** read the blueprint against the code on disk, built the local
network-free foundation, and checked the managed-service options through the
Gravity Index. No cloud accounts were created; no network services were called.

---

## 1. TL;DR

The blueprint's *shape* is sound and the local half is now real code. Two things
in it will **not** work as written, and both are easy to miss:

1. **Ephemeral runners break the "learning" loop.** GitHub Actions storage does
   not persist between runs, so the pheromone/leaderboard JSON vanishes every
   schedule unless it is committed back, uploaded and re-downloaded, or mirrored
   to a database. A "self-adapting" loop that forgets each run is just a cron job.
2. **There is still no ingestion.** Nothing in `core_framework/` actually calls
   Gemini/Vibe CLI or fetches SEC/news data. A cloud cron would fire on schedule
   and export near-empty streams. Cloud compute is the *last* mile, not the first.

Everything else — the scoring engine, the exporters, the adaptive memory, and
GitHub Actions as a trigger — works and is covered by tests.

---

## 2. What will work

| Blueprint piece | Status | Notes |
|---|---|---|
| Adaptive query memory (observe/mutate/reward/decay) | **Built** | `shared/adaptive_memory.py`, 8 tests |
| Epsilon-greedy explore/exploit | **Built + tested** | `plan()` with configurable `exploration_rate` |
| Leaderboard / alpha exports as run artifacts | **Works** | `output/market_twin.json`, `output/alpha_stream.csv` |
| GitHub Actions cron as trigger | **Works, with caveats** | `core_framework/.github/workflows/scout_cron.yml` (dispatch-first) |
| Telegram / Discord / REST webhook outreach | **Works** | Template step is secret-guarded and non-fatal |
| Managed DB for cross-run persistence | **Optional add-on** | See §4 |

The adaptive memory is pure stdlib, no network, deterministic under an injected
clock — so it runs identically on a Chromebook, in Actions, or on Modal.

## 3. What will not work (as written)

### 3.1 Ephemeral storage kills persistence
GitHub-hosted runners are destroyed after each job. `scout_leaderboard.json` and
the adaptive memory file live in the checkout and are lost unless something
durable holds them. Options, cheapest first:

- Commit the memory file back to the repo (works, but noisy history and a race
  if runs overlap).
- Upload as an artifact and download it at the start of the next run (clunky,
  retention-limited).
- Mirror `AdaptiveQueryMemory.to_dict()` into a managed DB (correct answer).

### 3.2 Ingestion: offline done, live unverified
The delegation model (Gemini = filings, Vibe = news) was a contract, not a
pipeline. This session closed the **offline** half (`adapters/ingest_adapter.py`
reusing `trend_scraper`) and wired **network-gated live sources**
(`adapters/live_sources.py`, incl. SEC EDGAR). The EDGAR parser is tested
offline; the live HTTP call was never executed here and is UNVERIFIED. Live runs
need network egress plus `SEC_USER_AGENT`. There is still no Gemini/Vibe CLI
execution path.

### 3.3 Free-tier claims are conditional and drift
"$0/month" holds *only* if every limit is respected and stays free. Treat each
number below as a claim to verify at signup, not a guarantee:

- **GitHub Actions:** free minutes are generous but scheduled workflows are
  auto-disabled after ~60 days of repository inactivity and must be re-enabled.
- **Modal:** the "free monthly credits" figure is an allowance, not a promise;
  confirm current terms before depending on it.
- **Object storage:** Cloudflare R2 has a free tier; AWS S3 does not. Do not
  assume S3 is free.
- **Managed DBs:** Gravity's tracked recommendation for this workload is a
  forever-free managed DB (see §4); vendor free-tier sizes change over time.

### 3.4 Exporting "alpha" to public artifacts leaks the edge
Uploading `alpha_stream.csv` as a public artifact (or committing it) publishes
the product you intend to sell. Keep alpha output private or push it only to a
webhook/DB the buyer subscribes to.

### 3.5 Security boundary
Webhook payloads and any fetched documents remain untrusted input per the repo
contract. Never let a cron job turn fetched content into executed instructions,
and never commit secrets — use repository/Actions secrets only.

---

## 4. Managed-service option (via Gravity Index)

The runtime need is "a database that survives between ephemeral runs, with an
optional vector story for memory." Gravity's recommendation for this stack:

- **MongoDB Atlas** — forever-free M0 cluster (512 MB, shared compute, no credit
  card), with built-in Vector Search, which can hold both the leaderboard and the
  adaptive memory in one managed service. Env var: `MONGODB_URI`.
- **Alternative:** **Tiger Cloud** — free Postgres (2 services, up to 750 MB
  each, no credit card) with `pgvector`, if a relational model is preferred.

No account was created and no credentials were requested in this session. To
adopt either, a `MONGODB_URI` (or Postgres DSN) in GitHub Actions secrets is the
only wiring change; `AdaptiveQueryMemory.to_dict()` is already the export shape.

For the purely local / $0 path, JSON-on-disk is sufficient and is what is
implemented today.

---

## 5. Built this session (the new track)

| Artifact | Purpose |
|---|---|
| `shared/adaptive_memory.py` | Pheromone memory: record -> reward -> decay -> plan (stdlib only) |
| `tests/test_adaptive_memory.py` | 8 deterministic tests (reward, decay, exploration, mutation, persistence, integration) |
| `adapters/ingest_adapter.py` | Offline ingestion: binds `tools/ingest/trend_scraper.py` to AxeScout findings |
| `adapters/live_sources.py` | Network-gated live sources (SEC EDGAR); parser tested offline |
| `tests/test_ingest_adapter.py` | 6 tests incl. a full network-free adapt → patrol → score → export loop |
| `tests/test_live_sources.py` | 5 tests: offline parser + network gating (never calls out) |
| `ScoutVehicle.run_ingested_patrol()` / `plan_adaptive_watchlist()` / `record_adaptive_yields()` | Optional hooks; no behavior change unless attached |
| `.github/workflows/scout_cron.yml` | Dispatch-first workflow template; schedule commented until live ingestion exists |
| `.gitignore` | Ignores `output/`, `logs/`, leaderboard, caches |

### Verified
- `cd ~/core_framework && python3 -m pytest tests/ -q` → **47 passed**
- Offline loop verified: local JSON → findings → scoring → `market_twin.json`
  + `alpha_stream.csv`, with adaptive memory learning the query yield.
- Backend starts under the bare interpreter (port open) after the import-order fix;
  pending signals now expire.

### Next smallest verified actions
1. Persist adaptive memory between runs (commit-back or Atlas/Tiger).
2. ~~Build a mock ingestion adapter~~ — done offline via `trend_scraper` reuse.
3. Verify one live source end-to-end (needs network + `SEC_USER_AGENT`) before
   any sales demo — the code path exists but has never made a real request.
