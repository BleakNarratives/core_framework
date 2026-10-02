# Freebuff Agent Handoff & Asymmetric Intel Roadmap

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

## Next Steps for Freebuff Agent
1. Start with Task 1 (daemon hardening): make `launchers/unified.py` and `bin/scout_vehicle.py` safe to background with `nohup` / subprocess without fd hangs.
2. Proceed to Task 2 (scoring engine): edit `ScoutLeaderboard.record_finding()` in `core_framework/bin/scout_vehicle.py` to apply asymmetric weights and cross-verification bounties.
3. Task 3 (exporters): add `export_alpha_streams()` method to `ScoutVehicle` writing CSV/JSON to `core_framework/output/`.

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
