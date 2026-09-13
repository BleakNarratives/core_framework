# CURATOR — projects/ScoutEmpire
*Scout Empire project. Created 2026-09-12.*

| File | Type | Purpose |
|---|---|---|
| `manifest.json` | index | 40 scouts + 8 continents, source of truth |
| `cli/scout` | CLI | unified `scout` command (list/run/retrain/sweep/report) |
| `scouts/` | symlinks | 40 links -> .agents/skills/*/scout (live, no copy) |
| `docs/CATALOG.md` | doc | human catalog by continent |
| `docs/FOREMAN.md` | doc | herding guide |
| `docs/DESIRED_SETTINGS.md` | doc | tuning guide |

## Use
```
scout list; scout doctor; scout sweep; scout report
scout run <slug> -- --help
scout retrain --all
```
Source: `.agents/skills/<slug>/scout/` — _never duplicate_.
Foreman herds 39 (scout-foreman is meta, not managed).
