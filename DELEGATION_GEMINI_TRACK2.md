# Track 2 Delegation: Free-Cloud Adaptive Scouting
## Gemini CLI Task Block — Scoring Engine & Prediction Quality

> **Final authority:** Kilo makes the final call on this plan. Adjust if you see a better split.
> **Do not edit:** `core_framework/adapters/live_sources.py` or `core_framework/bin/scout_vehicle.py`
> **Working directory:** `/home/bleaknarratives`
> **Branch:** `main` (home repo) / `main` (core_framework nested repo)

---

## Current Verified State (do not redo these)

| Component | Status |
|-----------|--------|
| `shared/adaptive_memory.py` — JSON-backed persistence | **DONE** — `_load()` / `save()` implemented, `test_persistence_roundtrip` passes |
| `shared/adaptive_memory.py` — pheromone decay + epsilon-greedy plan | **DONE** — 8 deterministic tests pass |
| `bin/scout_vehicle.py` — `ScoutVehicle.run_ingested_patrol()` | **DONE** — closes offline loop |
| `adapters/ingest_adapter.py` — `IngestAdapter` + `LocalJsonSource` binding | **DONE** — 6 tests pass |
| `adapters/ingest_adapter.py` — `MarketSignal` / `MarketSignalAdapter` / `load_market_signals()` | **DONE** — 4 new tests added, fixture at `core_framework/fixtures/market_signals.json` |
| `adapters/live_sources.py` — `SecEdgarFullTextSource` + `HttpJsonTrendSource` | **EXISTS** — network-gated, UNVERIFIED live. **Kilo owns this; do not touch.** |
| `tests/` — all 31 tests pass | **VERIFIED** |

---

## Your Mission: Prediction Quality & Scoring Engine Hardening

You own **scoring-engine review, prediction-quality improvements, and market-signal adapter integration**. You must not touch `live_sources.py` or `scout_vehicle.py` — those are Kilo’s files and edits there will cause merge conflicts.

### Task 1: Scoring Engine Review & Hardening

**File:** `core_framework/bin/scout_vehicle.py` (read-only reference)
**Test file you may edit:** `core_framework/tests/test_scoring_engine.py`

Review the `ScoutLeaderboard.record_finding()` method and its constants:

```python
MEDIUM_PROFILES = {
    "filings": {"base": 50, "multiplier": 3.5, "tier": "deep"},
    "regulatory": {"base": 50, "multiplier": 3.5, "tier": "deep"},
    "news": {"base": 10, "multiplier": 1.0, "tier": "fast"},
    "social": {"base": 10, "multiplier": 1.0, "tier": "fast"},
    "general": {"base": 25, "multiplier": 1.5, "tier": "general"},
}
CROSS_MEDIUM_BOUNTY = 100
EARLY_PREDICTOR_BONUS = 25
FALSE_POSITIVE_PENALTY = -20
```

Deliverables:
1. Identify any edge cases in `record_finding()` that could produce incorrect scores (e.g., division by zero, negative confidence, severity mismatches, agent-scoped deduplication bypasses).
2. Add **3–5 new deterministic tests** in `test_scoring_engine.py` using the existing `FakeClock` pattern. Cover:
   - Confidence clamped to `[0.0, 1.0]`
   - Severity mapping when `derive_severity()` sees a high score but non-CRITICAL keywords
   - Cross-medium bounty blocked when `pending_signals` has expired
   - False-positive penalty applied even when the same agent has seen the signal before
   - Agent-scoped deduplication: two different agents report the same signal and both score
3. Run `python3 -m pytest tests/test_scoring_engine.py -q` and confirm all pass.

**Do not modify** `bin/scout_vehicle.py` unless you find a genuine bug that must be fixed to make a new test pass. In that case, fix the bug and document it in your summary.

### Task 2: Market Signal Adapter Integration Review

**Files you may edit:**
- `core_framework/adapters/ingest_adapter.py` (read-only reference for MarketSignal classes)
- `core_framework/tests/test_ingest_adapter.py` (add tests)
- `core_framework/fixtures/market_signals.json` (do not modify existing entries; you may add new ones if needed)

Review the new `MarketSignalAdapter` and `load_market_signals()` path:

```python
class MarketSignalAdapter:
    def __init__(self, source_name: str = "market_signals", medium: str = "general")
    def finding_from_signal(self, signal: Any) -> Dict[str, Any]
    def findings_from_signals(self, signals: Iterable[Any]) -> List[Dict[str, Any]]
    def collect(self, signals: Iterable[Any], limit: int = 20) -> List[Dict[str, Any]]

def load_market_signals(path: str | Path) -> List[MarketSignal]
```

Deliverables:
1. Identify any gaps between `MarketSignal` fields and what `ScoutLeaderboard.record_finding()` expects. For example: does `MarketSignal.severity` always produce a valid `INFO`/`WARNING`/`CRITICAL`? Does `confidence` stay in `[0.0, 1.0]`? Does `finding_from_signal()` always return a dict with `ticker`, `scout_type`, `severity`, `signals`, `confidence`, `medium`, `source`?
2. Add **2–3 new tests** in `test_ingest_adapter.py` covering:
   - `MarketSignal` with missing/empty fields coerces to safe defaults
   - `MarketSignalAdapter.collect()` respects `limit`
   - `load_market_signals()` raises `TypeError` on malformed JSON (e.g., a dict instead of a list)
3. Run `python3 -m pytest tests/test_ingest_adapter.py -q` and confirm all pass.

**Do not modify** `bin/scout_vehicle.py` or `adapters/live_sources.py`.

### Task 3: Prediction-Quality Sanity Check

**Files you may edit:** none (read-only audit)

Review the end-to-end data flow for prediction quality:

```
MarketSignal(s) -> MarketSignalAdapter.findings_from_signals()
    -> ScoutVehicle.run_patrol_pass()
        -> ScoutLeaderboard.record_finding()
            -> MarketTwinTranslator.add_axe_scout_finding()
                -> to_ws_payload() / export_alpha_streams()
```

Answer these questions in your summary:
1. Is there any point where a low-confidence or malformed signal could silently produce a high-scoring finding? If yes, where and how?
2. Does the `signals` field in the final `alpha_stream.csv` preserve the original `MarketSignal.summary` + `signals`, or could it lose information?
3. If `AdaptiveQueryMemory` is attached and `record_adaptive_yields()` runs after a patrol with zero high-alpha findings, does the `AdaptiveQueryMemory` degrade useful patterns or preserve them?

---

## Guardrails

- **Do not touch** `core_framework/adapters/live_sources.py` (Kilo’s file)
- **Do not touch** `core_framework/bin/scout_vehicle.py` unless Task 1 forces a genuine bug fix
- **Do not touch** `core_framework/output/*` (runtime artifacts)
- **Do not modify** `core_framework/fixtures/market_signals.json` existing entries
- **Do not push** to any remote unless explicitly asked
- All tests must pass: `python3 -m pytest tests/test_scoring_engine.py tests/test_ingest_adapter.py tests/test_adaptive_memory.py -q`

---

## Success Criteria

1. `test_scoring_engine.py` has 3–5 new deterministic tests, all passing.
2. `test_ingest_adapter.py` has 2–3 new tests for `MarketSignalAdapter`, all passing.
3. No edits to `live_sources.py` or `scout_vehicle.py` unless a genuine bug was found and fixed.
4. Your summary includes:
   - List of files you edited
   - Any bugs found and fixed
   - Answers to Task 3’s three prediction-quality questions
   - Any remaining risks or gaps you spotted

---

## Baseline Test Command

```bash
cd /home/bleaknarratives/core_framework
python3 -m pytest tests/test_scoring_engine.py tests/test_ingest_adapter.py tests/test_adaptive_memory.py -q
```

Current baseline: **31 passed in 2.05s** (must stay green or improve).
