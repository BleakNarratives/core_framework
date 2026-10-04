# core_framework/design/ARCHITECTURE.md

## Unified Framework Architecture

### Design Philosophy

This is a **transplant, not a takeover**. Every file in `core_framework/` is a
pointer into an existing canonical source tree. Removing this directory has zero
effect on the original systems.

### System Map

```
core_framework/
├── launchers/          # Thin entry points (sys.path injection + runpy)
│   ├── code_city.py    → Code-City-Apocalypse/code_city_apocalypse.py
│   ├── modmind.py      → Code_City_Unified/modmind_unified/src/modmind_architect.py
│   ├── vertical_ai.py  → The-Werkz/Official-Vertical-AI-Boardroom/vertical_ai.py
│   ├── market_twin.py  → Vertical AI → market-twin adapter → Code City
│   └── unified.py      → Starts any combination as isolated subprocesses
│                         (--detach for daemon-safe, non-blocking launch)
├── adapters/           # Real-pipeline translation into Code City entities
│   ├── market_twin.py  # Vertical AI / AxeScout → buildings, monsters, agents
│   ├── district_schema.py  # segment → district, deterministic building positions
│   └── axe_scout_spec.py   # standalone finding → ScoutIntel spec
├── bin/
│   ├── scout_vehicle.py # Patrol pass, asymmetric ScoutLeaderboard, exporters,
│   │                    # WebSocket broadcast, and the scout CLI
│   └── domino.sh        # Canonical one-shot orchestrator (~/domino.sh wraps it)
├── bootstrap/          # CannibalContext session bootstrap (low-token kickoff)
│   └── cannibal_context.py  # config -> banner/menu -> JSONL history -> [SYS_INIT]
├── fixtures/           # Offline demo findings (no network)
├── shared/
│   ├── config.py       # Central path resolution, venv resolution, env defaults
│   ├── adaptive_memory.py  # Pheromone memory (atomic persistence, corrupt quarantine)
│   └── kernel_bus.py   # GossipBus kernel lock-in + adapter-demotion registry
├── output/             # Generated: market_twin.json + alpha_stream.csv (gitignored)
├── logs/               # Generated: detached launcher logs (gitignored)
├── design/             # Architecture docs, original intent preserved
│   ├── ARCHITECTURE.md
│   └── VERTICAL_AI_ORIGINAL_VISION.md
└── tests/              # Framework-level smoke + scoring/export/launcher tests

### Safety Guarantees

1. **No source files copied**: All launchers use `runpy.run_path()` on canonical files
2. **No sidecars moved**: crash_feeder, red_team, radar, tribunal, scouts stay in place
3. **Subprocess isolation**: `unified.py` launches each system in its own process
4. **Fresh project root**: `core_framework/` is self-contained at repo root level

### Data flow

```
findings ──▶ ScoutLeaderboard.record_finding()
                 │  Base × Multiplier × Confidence × Novelty
                 │  + cross-medium bounty / − false-positive penalty
                 ▼
           ScoutVehicle.run_patrol_pass()
                 │
        ┌────────┴─────────┐
        ▼                  ▼
MarketTwinTranslator   export_alpha_streams()
        │                  │
        ▼                  ├── output/market_twin.json  (3D spatial)
 broadcast_payload()       └── output/alpha_stream.csv   (alpha stream)
        │
        ▼  WebSocket (ws://localhost:8765)
 Code City backend.server.py → browser viewport
```

### Transport invariant

The Code City backend is a `websockets` server. Any producer must complete a
WebSocket handshake; a raw TCP JSON write is not a valid protocol and is not
supported. `scout_vehicle.broadcast_payload()` therefore uses a WebSocket client
and fails gracefully when the server is down or `websockets` is unavailable.

### Extension Points

- Add new launchers by following the `launchers/*.py` pattern
- Add shared utilities in `shared/`
- Document architectural decisions in `design/`
- Keep generated output out of version control via `.gitignore`

### Known blockers

See `../BUFFY_ASSESSMENT.md`. Most notable: `Code-City-Apocalypse/backend/server.py`
imports `websockets` before its own venv fallback runs, so it needs the resolved
venv on `PYTHONPATH` (or a launcher that injects it) to start.
