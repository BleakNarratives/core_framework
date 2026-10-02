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

## Quick start

```bash
# Single system
python -m core_framework.launchers.code_city
python -m core_framework.launchers.modmind
python -m core_framework.launchers.vertical_ai

# All three together
python -m core_framework.launchers.unified all
```

## Architecture

See `design/ARCHITECTURE.md` and `design/VERTICAL_AI_ORIGINAL_VISION.md`.

## Safety guarantee

Removing `core_framework/` has **zero effect** on any canonical source tree.
No files are duplicated, moved, or modified by this package.

## Handoff & Roadmap

See `ROADMAP.md` for verified baseline, Freebuff task list, and session boundary.
