# Project Map

**Measured:** 2026-09-17  
**Purpose:** canonical navigation for the mixed workspace while cleanup is staged.

This map is intentionally descriptive, not a move plan. The workspace contains
multiple independent projects, nested Git repositories, generated output, archives,
and local runtime state. Do not move or delete an entry based on its name alone.

## Start here

| Area | Preferred entry point | Role | Status / boundary |
|---|---|---|---|
| **MOLT** | [`projects/MOLT/README.md`](../projects/MOLT/README.md) | Living Markdown runtime, marketplace bundles, Scout/Oracle/Governor lifecycle | Primary tracked project in this repository |
| **MOLT runtime** | [`src/skill/`](../src/skill/) and [`src/sovereign/`](../src/sovereign/) | Core runtime and recursive/sovereign extensions | Shared source for this repository; do not duplicate into project folders |
| **Whorl** | [`Whorl/README.md`](../Whorl/README.md) | Field intelligence and agent deployment workbench | Separate nested Git repository; keep independently testable |
| **lean** | [`projects/lean/README.md`](../projects/lean/README.md) | Keyboard-only client for the local AI gateway | Separate nested Git repository (3 commits, no remote); deliberately not tracked here |
| **Vertical AI Boardroom** | [`The-Werkz/Official-Vertical-AI-Boardroom/README.md`](../The-Werkz/Official-Vertical-AI-Boardroom/README.md) | Multi-agent debate, chairman synthesis, simulation, genetics, outreach | Main boardroom candidate; path is referenced by shell aliases and runtime artifacts |
| **Vertical AI outreach** | [`vertical_ai/README.md`](../vertical_ai/README.md) · [`manifest.json`](../vertical_ai/manifest.json) | Local-business review and outreach workflow | Separate workspace; relationship to Boardroom needs validation before merging |
| **Vertical Local** | [`vertical_local/README.md`](../vertical_local/README.md) · [`manifest.json`](../vertical_local/manifest.json) | Model-agnostic local/API FastAPI wrapper and UI | Separate application; deterministic debate dry run is available |
| **Vertical Radar** | [`vertical_radar/README.md`](../vertical_radar/README.md) · [`manifest.json`](../vertical_radar/manifest.json) | Risk-assessment swarm prototype | Prototype workspace; live-only entrypoint |
| **Vertical Radar duplicate** | [`vertical_radar_dupe/README.md`](../vertical_radar_dupe/README.md) · [`manifest.json`](../vertical_radar_dupe/manifest.json) | Same stated purpose and README as `vertical_radar/` | Suspected incomplete duplicate; preserve pending provenance review |
| **Vertical AI Engine / Coach Bleak** | [`vertical_ai_engine/README.md`](../vertical_ai_engine/README.md) · [`manifest.json`](../vertical_ai_engine/manifest.json) | Older accountability/FOIA/document-analysis application and thread archive | Archive-plus-code workspace; do not mix with current Boardroom without a provenance decision |

## Repository boundaries

- The repository root is `/home/bleaknarratives` on the current machine.
- Tracked source is primarily under `src/`, `projects/`, `docs/`, `templates/`,
  `tests/`, and `tools/`.
- `Whorl/` has its own `.git` directory. Changes inside it must be treated as a
  separate repository operation.
- `projects/lean/` is also a nested repository: own `.git`, branch `main`, three
  commits, and no remote. This repository deliberately does not track it --
  adding it would record a gitlink no clone could resolve -- so its files cannot
  be committed here as ordinary source. Test it from inside it:
  `cd projects/lean && python -m pytest tests/ -q` (79 tests, no network).
- `projects/herald/` is not a nested repository, but its suite is nested: tests
  live in `projects/herald/tests/` and need that directory as the top level, so
  `python -m unittest discover -s tests` did not reach them. They are now covered
  by `tests/test_herald_suite_offline.py`, which runs herald's own suite as a
  subprocess — so the root command does count them. Run them directly with
  `python -m unittest discover -s projects/herald/tests -t projects/herald`
  (130 tests, offline). Its lead data (`LEADS.md`, `OUTREACH_DRAFTS.md`) is
  deliberately ignored by `projects/herald/.gitignore`.
- `thoth_orchestrator/` is ignored by the root `.gitignore` (`/*`, with no allowlist
  entry) and yet imported by tracked code: `src/sovereign/recursive_engine.py` and
  `src/sovereign/bridges.py` reach `thoth_orchestrator.agent_bus` and
  `thoth_orchestrator.motherbrain`, so `agent_bus` also resolves as a top-level
  import wherever `sys.path` picks up its directory. Both imports sit behind
  try/except, so a clone without the directory degrades rather than fails.
  Its state paths are pinned to one machine in several files. `agent_bus.py` used to
  default its bus directory to `/home/bleaknarratives/RootBase` regardless of
  `$HOME`; it now defaults to `$HOME/RootBase`. Because the directory is untracked,
  that fix cannot travel in a commit — `tests/test_thoth_bus_location.py` records it
  instead, and skips where `agent_bus` is not importable.
- The current branch is `feature/ribbon-animation`. As of 2026-09-19 the working
  tree is committed apart from the untracked items catalogued above; this
  document describes the tree and does not imply ownership of anything in it.
- `projects/whorl_ecosystem/` is reserved for a future mapped migration. Nothing
  should be moved there without a source-to-destination inventory.

## Recommended conceptual layout (not yet applied)

```text
projects/
├── MOLT/                         # current tracked MOLT product/docs
├── vertical-ai-boardroom/        # future home for the canonical Boardroom app
├── vertical-ai-outreach/         # future home for review/outreach workflow
├── vertical-local/                # future home for local model wrapper
├── vertical-radar/                # future home for the radar prototype
├── vertical-ai-engine/            # future home for Coach Bleak archive/app
└── whorl_ecosystem/               # reserved; separate Whorl-related work only

Whorl/                             # remains a separate nested repository for now
src/skill/ and src/sovereign/      # MOLT runtime integration in this repository
```

The future names above are proposals only. In particular, they do **not** authorize
moving files, merging Git histories, or deleting `vertical_radar_dupe`.

## Current Vertical AI relationship map

```text
Official-Vertical-AI-Boardroom  ← canonical boardroom candidate
        ├── vertical_ai.py      ← legacy/current CLI entry point
        ├── vertical_ai_v2.py   ← local-first experimental conductor
        └── The-Werkz ecosystem ← external integrations and path references

vertical_ai/                     ← outreach/reviews workflow
vertical_local/                  ← local/API wrapper and web face
vertical_radar/                  ← risk-assessment prototype
vertical_radar_dupe/             ← unverified duplicate
vertical_ai_engine/              ← Coach Bleak/Veritas archive and application
projects/vai_2d259c8e22fa/       ← manifest-only artifact observed
```

## Before any physical reorganization

1. Inventory imports, shell aliases, cron jobs, systemd units, and generated state.
2. Treat `.env`, vaults, key-shaped files, databases, logs, exports, and backups as
   data or quarantine—not as source to be swept into `projects/`.
3. Preserve each nested repository's boundary and test command.
4. Resolve whether `vertical_ai/`, `vertical_local/`, and the Boardroom share a
   contract or merely share a name.
5. Compare `vertical_radar` and `vertical_radar_dupe` byte-for-byte or by explicit
   manifest before considering consolidation.
6. Make one logical move at a time and verify references immediately afterward.

For the Vertical AI-specific dependency graph and migration gates, see
[`VERTICAL_AI_MIGRATION.md`](VERTICAL_AI_MIGRATION.md). The dependency manifests
are the `manifest.json` links in the table above; the safe offline verifier is
[`scripts/verify_vertical_ai.py`](../scripts/verify_vertical_ai.py).
For broader path dependencies
and the prior root migration analysis, see [`PATH_MAPPING.md`](PATH_MAPPING.md) and
[`REPO_ROOT_MIGRATION.md`](REPO_ROOT_MIGRATION.md).
