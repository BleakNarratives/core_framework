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
│   └── unified.py      → Starts any combination as isolated subprocesses
├── shared/
│   └── config.py       # Central path resolution, env defaults
├── design/             # Architecture docs, original intent preserved
│   ├── ARCHITECTURE.md
│   └── VERTICAL_AI_ORIGINAL_VISION.md
└── tests/              # Framework-level smoke tests

### Safety Guarantees

1. **No source files copied**: All launchers use `runpy.run_path()` on canonical files
2. **No sidecars moved**: crash_feeder, red_team, radar, tribunal, scouts stay in place
3. **Subprocess isolation**: `unified.py` launches each system in its own process
4. **Fresh project root**: `core_framework/` is self-contained at repo root level

### Extension Points

- Add new launchers by following the `launchers/*.py` pattern
- Add shared utilities in `shared/`
- Document architectural decisions in `design/`
