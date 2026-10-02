# core_framework

Lightweight orchestration layer for **Code City**, **ModMind**, and **Vertical AI**.
This project contains **no copied source code** — every file here is a pointer
into the canonical trees already on disk.

## Canonical sources (untouched)

| System | Canonical root |
|---|---|
| Code City | `~/Code-City-Apocalypse/` |
| ModMind | `~/Code-City-Apocalypse/Code_City_Unified/modmind_unified/` |
| Vertical AI | `~/The-Werkz/Official-Vertical-AI-Boardroom/` |
| Vertical AI Engine | `~/vertical_ai_engine/` |

Sidecars preserved in place: crash feeder, red/blue teams, radar, tribunal,
coach_bleak, boardroom, scouts, genetic arena, and all agent swarms.

## One domino (start here)

From the repo root, one command fires the whole scout machine offline:

```bash
./domino.sh            # preflight -> serve -> patrol -> broadcast -> status
./domino.sh help       # all stages: serve | stop | patrol | broadcast | plan | status | skill
```

`~/domino.sh` is a thin root-level wrapper that execs the canonical, modular
orchestrator at `core_framework/bin/domino.sh`. It is safe by default: offline
fixtures, localhost backend, no secrets, no network (pass `--live` / set
`SEC_USER_AGENT` only when you mean it).

## Quick start

```bash
# Single system
python -m core_framework.launchers.code_city
python -m core_framework.launchers.modmind
python -m core_framework.launchers.vertical_ai

# All three together
python -m core_framework.launchers.unified all

# Daemon-safe: own session, logs to logs/<system>.log, returns immediately
python -m core_framework.launchers.unified all --detach

# Scout vehicle: patrol -> score -> dual-stream export -> WebSocket broadcast
python core_framework/bin/scout_vehicle.py ws://localhost:8765
```

## Asymmetric scoring & exports

The `scout_vehicle` module is also a CLI: `python -m core_framework.bin.scout_vehicle --ingest sec=PATH --plan`
(offline) or `--live` (network-gated). `core_framework/bin/scout_vehicle.py` scores findings with
`Base Value × Difficulty Multiplier × Confidence × Novelty` (filings 3.5×/50,
news 1.0×/10), adds cross-medium verification bounties (+100 deep / +25 fast)
and false-positive penalties (−20), then writes two commercial streams to
`core_framework/output/`: `market_twin.json` (3D) and `alpha_stream.csv` (alpha).

Venvs are resolved dynamically (`shared/config.py`), not hard-coded. Generated
artifacts (`output/`, `logs/`, `scout_leaderboard.json`, caches) are gitignored.

## Adaptive loop

`shared/adaptive_memory.py` is a stdlib-only, network-free pheromone memory:
it records per-query/source yield, rewards high-alpha runs, decays with a
configurable half-life, and plans the next queries with an epsilon-greedy
explore/exploit step. Attach it to a `ScoutVehicle` to enable
`plan_adaptive_watchlist()` and `record_adaptive_yields()`; without it, the
vehicle behaves exactly as before.

`.github/workflows/scout_cron.yml` is a dispatch-first GitHub Actions template
for running the loop on a schedule (schedule commented until ingestion exists).
See `CLOUD_ADAPTIVE_BLUEPRINT.md` for what that free-cloud plan will and will
not do.

## Architecture

See `design/ARCHITECTURE.md` and `design/VERTICAL_AI_ORIGINAL_VISION.md`.
See `BUFFY_ASSESSMENT.md` for the verified task status and known blockers
(notably the backend `websockets` venv issue), and
`CLOUD_ADAPTIVE_BLUEPRINT.md` for the free-cloud roadmap and its limits.

## Safety guarantee

Removing `core_framework/` has **zero effect** on any canonical source tree.
No files are duplicated, moved, or modified by this package.

## Handoff & Roadmap

See `ROADMAP.md` for verified baseline, Freebuff task list, and session boundary.
