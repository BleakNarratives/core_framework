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
./domino.sh                 # preflight -> serve -> patrol -> broadcast -> status
./domino.sh leaderboard     # run the driver offline, print the leaderboard queue
./domino.sh help            # stages: serve | stop | patrol | broadcast | plan
                            #         leaderboard | status | sprawl | skill
```

`~/domino.sh` is a thin root-level wrapper that execs the canonical, modular
orchestrator at `core_framework/bin/domino.sh`. It is safe by default: offline
fixtures, localhost backend, no secrets, no network (pass `--live` / set
`SEC_USER_AGENT` only when you mean it).

## Doc sprawl

One command maps every roadmap / handoff / QRD / MRD / STANK / white-paper doc
and produces a triage plan:

```bash
./domino.sh sprawl          # writes SPRAWL_INDEX.md + SPRAWL_TRIAGE.md at the repo root
```

`sprawl_scan.py` is read-only: it extracts open checklist items, classifies docs,
and separates **active** projects from **museum/backup/recovery** copies so the
work surface stays small. Regenerate any time; the two root files are generated,
not hand-edited.

### Duplicate consolidation (opt-in)

`sprawl_scan.py` also plans safe duplicate collapses. It classifies every
byte-identical filename family and only ever touches **SAFE** strays — copies
that sit outside their canonical tree. Deliberate multi-project mirrors,
agent/tool config copies, and point-in-time workspace snapshots are classified
and deliberately left alone:

```bash
python3 -m core_framework.bin.sprawl_scan --consolidate          # write SPRAWL_CONSOLIDATE.md (plan only)
python3 -m core_framework.bin.sprawl_scan --consolidate --apply  # back up + replace strays with pointer stubs
```

`--apply` copies each duplicate to `~/.sprawl_backup/<stamp>/` before writing
the pointer, so every collapse is reversible.

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

## Session bootstrap (CannibalContext)

One command gives every session a ring-music intro without burning tokens:

```bash
python3 -m core_framework.bootstrap.cannibal_context kickoff            # banner + menu
python3 -m core_framework.bootstrap.cannibal_context kickoff --track 2  # pick an angle
python3 -m core_framework.bootstrap.cannibal_context kickoff --auto     # resume last angle
python3 -m core_framework.bootstrap.cannibal_context handshake          # [SYS_INIT] bridge line
./domino.sh kickoff                                                     # same via domino
```

It loads the low-token operator context (`bootstrap/cannibal_context.json`),
renders the multiple-choice session menu (Tracks 1-3, Blue Sky, Custom Angle),
suggests the first domino command for the chosen angle, prints the auto-boot
plan, and appends the choice to a JSONL session stream
(`~/.config/freebuff/sessions.jsonl`) so the next `--auto` kickoff resumes
where the last one left off. Non-TTY runs (cron/CI) render the menu and record
nothing.

Install a user-owned config (survives reboots, packaged default never clobbers
your edits):

```bash
python3 -m core_framework.bootstrap.cannibal_context install
```

Auto ring music on every login — one line in `~/.bashrc`:

```bash
python3 -m core_framework.bootstrap.cannibal_context kickoff || true
```

The `handshake` output is the bridge primitive for pasting into any external
agent chat (GLM, Gemini, novel web tools):

```
[SYS_INIT]: Operator=Mikey | VCS=Nat | Output=cat<<'EOF' | Arch=core_framework | Mode=Goal-Oriented / Profit-Minded / Boardroom Approved
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
explore/exploit step. State persists at a stable path
(`output/adaptive_memory.json` by default) with **atomic** writes (temp file +
fsync + `os.replace`), so a crash mid-write never tears the file, and a corrupt
file is quarantined as `*.corrupt-<UTC>` rather than silently overwritten —
learned state survives across runs. Attach it to a `ScoutVehicle` to enable
`plan_adaptive_watchlist()` and `record_adaptive_yields()`; without it, the
vehicle behaves exactly as before.

`.github/workflows/scout_cron.yml` is a dispatch-first GitHub Actions template
for running the loop on a schedule (schedule commented until ingestion exists).
See `CLOUD_ADAPTIVE_BLUEPRINT.md` for what that free-cloud plan will and will
not do.

## Architecture

**Kernel bus lock-in** — `shared/kernel_bus.py` declares GossipBus
(`RootBase/gossip_bus.py`) as THE canonical kernel and catalogs the other buses
(`integration_bus`, `event_bus`, `outclaw_bus`, `whorl_bus_adapter`) as demoted
adapters with an auditable health report (`python3 -m
core_framework.shared.kernel_bus`; also surfaced by `./domino.sh preflight`).
Pointer-layer rules apply: the kernel file is never copied, and the registry
degrades gracefully on machines that don't carry the home workspace.

See `design/ARCHITECTURE.md` and `design/VERTICAL_AI_ORIGINAL_VISION.md`.
See `BUFFY_ASSESSMENT.md` for the verified task status and known blockers
(notably the backend `websockets` venv issue), and
`CLOUD_ADAPTIVE_BLUEPRINT.md` for the free-cloud roadmap and its limits.

## Safety guarantee

Removing `core_framework/` has **zero effect** on any canonical source tree.
No files are duplicated, moved, or modified by this package.

## Handoff & Roadmap

See `HANDOFF_20261004.md` for the current handoff record (what changed, how it
was verified, open TODOs), and `ROADMAP.md` for the verified baseline, task
list, and session boundaries.
