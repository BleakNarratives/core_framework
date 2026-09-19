# Thoth Orchestration Architecture

Last updated: 2026-09-07

## Overview

The orchestration layer routes ZeroClaw + OpenClaw traffic, agent swarm
activity, and tool invocations through a single local event bus. MotherBrain
analyzes the bus and emits decisions. Thoth executes those decisions. The
Courier (Hermes role) delivers events to subscribed handlers with retry and a
dead-letter queue.

Everything runs on-device. No network service is required.

## Components

### agent_bus.py — The Nervous System

A JSONL append-only event bus at `~/RootBase/logs/shared/agent_events.jsonl`.

- **Multi-writer safe.** `emit_event()` opens the file in append mode. On
  Linux, `O_APPEND` writes are atomic for payloads under 4096 bytes (every
  event is well under that), so multiple processes can append simultaneously
  without corruption.
- **Multi-reader safe.** Each consumer keeps its own cursor in its own state
  file, so agents don't fight over a shared offset.

API:
| Function | Purpose |
|---|---|
| `emit_event(event_type, payload, source, origin, channel, tags)` | Append an event to the bus |
| `read_events(offset, limit)` | Read events since offset; returns `(events, next_offset)` |
| `current_line_count()` | Total lines in the bus file |
| `write_state(state)` / `read_state()` | Persist arbitrary key-value state |
| `read_dead_letters(offset, limit)` | Read failed deliveries for inspection/replay |

### Courier (in agent_bus.py) — Hermes Role

Delivers bus events to subscribed handlers. Consolidates the old Hermes stub
into the bus itself — the bus *is* the courier.

- `subscribe(event_type, handler)` — register a handler; `'*'` matches all events
- `process(limit)` — reads events since the persisted cursor, dispatches to
  matching handlers with retry+backoff, advances the cursor, returns a summary
- Retry: up to `max_attempts` (default 3), sleeping `backoff_seconds * attempt`
  between tries
- Dead-letter queue: handlers that exhaust retries land in `dead_letters.jsonl`
  with the event, handler name, error, and attempt count — nothing is silently
  dropped
- Cursor persisted in `courier_state.json`; a fresh courier starts at the bus
  head (only delivers NEW events on first run)
- A module-level `courier = Courier()` instance is ready at import

### motherbrain.py — Central Decision Unit

Sits above the bus. Consumes events, runs analysis + prediction + decision
hooks, emits decisions back onto the bus for Thoth to act on.

`tick()` runs the full cycle:
1. `ingest()` — pull new events since last offset (no replay on first run)
2. `analyze()` — counts by event_type / source / channel
3. `predict()` — v0 heuristic: hottest sources (swap for real ML here)
4. `decide()` — v0 rule: any source emitting > 5 events in one tick gets throttled
5. `emit_decisions()` — emits `motherbrain.decision` events to the bus

State persisted in `motherbrain_state.json`. Extension points for real ML live
in `predict()` and `decide()` — swap the heuristics without touching the bus
plumbing.

### thoth_core.py — Execution Engine

Reads MotherBrain's decisions and acts on them, closing the loop.

- `act_on_decisions(limit)` — reads `motherbrain.decision` events since the
  Thoth cursor, dispatches each via `_execute_decision()`, advances cursor
- `_execute_decision(decision)` — maps decision types to real Thoth actions:

| Decision | Thoth Action | Bus Emission |
|---|---|---|
| `throttle` | Add `target_source` to `self.throttled_sources` | `thoth.action` |
| `revenue_push` | Call `self.generate_revenue(platform=...)` | `thoth.action` |
| `idle` | No-op (no event emitted) | — |
| unknown | Log + record | `thoth.action` (unknown_decision) |

Cursor persisted in `thoth_state.json` (starts at bus head on first run).

### thoth_adapters.py — Traffic Adapters

| Adapter | Wraps | Status |
|---|---|---|
| `zeroclaw` | `zeroclaw_lab_broker` CLI | Working |
| `openclaw` | `openclaw` npm CLI | NOT installed on device; run `npm install -g openclaw` |
| `lough` | Event emit/poll | Working |
| `datacampus` | Lab/assignment management | Working (warns if runtime absent) |
| `payment_bridge` | Invoice status checks | Working |

Additional adapters imported by thoth_core: `higgins` (content generation +
routing), `coach_bleak` (analysis + escalation).

## Multi-Agent Concurrency

### Can multiple agents run simultaneously?

**Yes.** The bus is designed for it:
- `emit_event()` uses append mode — multiple processes can write safely
- Each agent (MotherBrain, ThothCore, Courier) has its own persisted cursor —
  no shared-cursor conflicts
- The Courier supports multiple handlers in one process (sequential dispatch)

### How to run the swarm

#### `swarm_cli.py` — Unified multi-process supervisor (primary)

One CLI launches all agents as parallel processes, monitors them, and
auto-restarts on crash. This is the production approach.

```bash
cd ~/thoth_orchestrator

python3 swarm_cli.py              # run the full swarm
python3 swarm_cli.py --status      # print bus status + exit
python3 swarm_cli.py --replay-dlq  # replay dead-lettered events
python3 swarm_cli.py --list         # list registered agents
```

**Force multipliers:**
1. Self-healing — auto-restart on crash, exponential backoff (1s→2s→4s→...→30s cap)
2. Heartbeat watch — each agent emits `agent.heartbeat`; supervisor detects hangs
3. Shared intelligence — MotherBrain decisions propagate to ALL agents via bus
4. Dead-letter replay — `--replay-dlq` re-injects failed deliveries
5. Self-observing — emits `swarm.runner` events (start/restart/stop) to the bus
6. Graceful shutdown — SIGTERM propagates to children; agents flush state

**Agent registry** (in `swarm_cli.py`):

| Agent | Module | Target | Interval |
|---|---|---|---|
| motherbrain | motherbrain | MotherBrain.tick | 5s |
| thoth | thoth_core | ThothCore.act_on_decisions | 3s |
| courier | agent_bus | courier.process | 2s |

Python agents self-invoke (`python3 swarm_cli.py --agent <name>`). External
CLI/JS agents can be added with a `"cmd"` key instead of `"module"`/`"target"`
(see Future section below).

#### Manual single-process loop (dev)

For quick testing without the supervisor:

```python
import sys; sys.path.insert(0, ".")
from motherbrain import MotherBrain
from thoth_core import ThothCore
import agent_bus

mb = MotherBrain()
thoth = ThothCore()
while True:
    mb.tick()                         # analyze + decide -> bus
    thoth.act_on_decisions()          # read decisions -> execute
    agent_bus.courier.process()       # deliver pending events to handlers
```

#### Via CodeBuddy Code CLI (dev/debug only)

```bash
# One MotherBrain tick
python3 -c "import sys; sys.path.insert(0,'.'); from motherbrain import MotherBrain; MotherBrain().tick()"

# One Thoth decision pass
python3 -c "import sys; sys.path.insert(0,'.'); from thoth_core import ThothCore; ThothCore().act_on_decisions()"

# Inspect the bus
python3 -c "
import sys; sys.path.insert(0,'.')
from agent_bus import read_events, current_line_count
events, _ = read_events(offset=current_line_count()-10, limit=10)
for e in events: print(e['event_type'], e['source'], e.get('payload'))
"
```

**Not suitable for persistent runtime** — agents spawned by the CLI die when
the session ends. Use this for building, debugging, and inspecting.

## Event Flow

```
  [Any agent] --emit_event()--> agent_events.jsonl
                                      |
                         MotherBrain.ingest() (own cursor)
                                      |
                         MotherBrain.analyze() + predict() + decide()
                                      |
                         MotherBrain.emit_decisions()
                                      |
                         motherbrain.decision event on bus
                                      |
                         ThothCore.act_on_decisions() (own cursor)
                                      |
                         ThothCore._execute_decision()
                           throttle    -> throttled_sources.add(target)
                           revenue_push -> generate_revenue(platform)
                           idle        -> no-op
                                      |
                         ThothCore emits thoth.action
                                      |
                         Courier.process() (own cursor)
                           dispatches to subscribed handlers
                           retry+backoff on failure
                           dead_letters.jsonl on exhaustion
```

## State Files

All in `~/RootBase/logs/shared/`:

| File | Owner | Purpose |
|---|---|---|
| `agent_events.jsonl` | agent_bus | The event bus itself |
| `dead_letters.jsonl` | Courier | Failed deliveries (event + error + attempts) |
| `courier_state.json` | Courier | Delivery cursor offset |
| `motherbrain_state.json` | MotherBrain | Ingest cursor offset |
| `thoth_state.json` | ThothCore | Decision cursor offset |
| `agent_bus_state.json` | agent_bus | Generic key-value state |

## Existing Infrastructure

| File | What it does | Uses bus? |
|---|---|---|
| `swarm_cli.py` | **Multi-process supervisor** — launches, monitors, auto-restarts agents with force multipliers | Yes |
| `thoth_daemon.py` | Single-process event loop; maps bus events to ThothCore methods; 10s sleep | Yes |
| `thoth_automation_engine.py` | Task-queue engine with priority queue; file-based via `foxwood_comms.json` | No (separate system) |
| `launch_thoth_swarm.sh` | Shell script that launches `thoth_automation_engine.py` | — |

`swarm_cli.py` is the primary entry point. It replaces the need for
`thoth_daemon.py` and manual process management. `thoth_automation_engine.py`
is a separate coordination system that uses its own JSON file instead of the
bus — it could be folded into the swarm_cli agent registry as a future step.

## Quick Start

```bash
cd ~/thoth_orchestrator

# 1. Run the full swarm (MotherBrain + Thoth + Courier, all in parallel)
python3 swarm_cli.py

# 2. In another terminal, check status
python3 swarm_cli.py --status

# 3. Replay any dead-lettered events
python3 swarm_cli.py --replay-dlq

# 4. List registered agents
python3 swarm_cli.py --list
```

## Future: JS Tool Absorption & Config Unification

The `swarm_cli.py` agent registry is designed to absorb external CLI/TUI
tools (including JS-based ones) into one unified interface. Two planned steps:

### Step 1: Register external CLI tools as agents

Add JS/external tools to the `AGENTS` dict in `swarm_cli.py` using the `"cmd"`
key instead of `"module"`/`"target"`:

```python
AGENTS = {
    # ...existing Python agents...
    "some_js_tool": {
        "cmd": ["node", "/path/to/index.js"],
        "interval": 10,
    },
}
```

External agents are launched via `subprocess.Popen` and monitored the same
way as Python agents (crash detection via `poll()`). They don't emit
heartbeats (they don't know about the bus), but crash-restart still works.

### Step 2: Unify configs, API keys, and .env files

Pull all `.env` files, `models.json`, config files, and API keys from the
external CLI/TUI tools into a single config source that `swarm_cli.py` loads
at startup and exposes to all agents. Tools that don't conform to the unified
config get dropped from the system.

## Extension Points

| Want to... | Where to change |
|---|---|
| Add real ML predictions | `motherbrain.py` → `predict()` |
| Add new decision rules | `motherbrain.py` → `decide()` |
| Handle new decision types | `thoth_core.py` → `_execute_decision()` |
| Subscribe a handler to events | `agent_bus.courier.subscribe(event_type, handler)` |
| Wire a new CLI tool as an adapter | `thoth_adapters.py` (mirror `ZeroClawAdapter`) |
| Replay dead-lettered events | `python3 swarm_cli.py --replay-dlq` |
| Add a Python agent to the swarm | `swarm_cli.py` → `AGENTS` dict (`module`/`target`) |
| Add an external CLI/JS agent | `swarm_cli.py` → `AGENTS` dict (`cmd` key) |
| Change agent tick interval | `swarm_cli.py` → `AGENTS` dict (`interval`) |
| Tune restart backoff | `swarm_cli.py` → `BACKOFF_CAP`, `HEARTBEAT_TIMEOUT` |
