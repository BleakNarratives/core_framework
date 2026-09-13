# MOLT × Whorl × Loom — Hive Mind (Living Map)

> MOLT one-shots were isolated. **Whorl + Loom turn them into a distributed, persistent hive mind** that mutates, version-controls, and competes in real time.

```
 [ Scout Engine ]  ──(RAG Context)──► [ MOLT Triad ] ──(Atomic Write)──► [ Whorl Bus ]
                                           │                                   │
                                    (Instar Gate)                     (~/.whorl/bus/)
                                           ▼                                   ▼
 [ Loom Workflow ] ◄──(Version Commit)── [ Oracle ] ◄──(Logic Combat)─── [ Whorl Arena ]

```

## The 4 complimentary hive skills

These are **not add-ons**. They make the marketplace bundles distributed, resumable, versioned, and evolving — that's why they command hive pricing.

| Skill bundle | Role | Scout focus | Optimization goal | Price | Scout |
|---|---|---|---|---|---|
| **`whorl-bus-dispatcher`** — The Nervous System | Bridge `inference_bridge.py` ↔ Whorl's **18 atomic bus types** + 4 MOLT extensions | Monitors `~/.whorl/bus/` payload events across Termux/Chromebook/desktop | **Latency minimization & zero-drop throughput** | **$299–$549** | 1m · depth 3 |
| **`loom-thread-weaver`** — The Choreographer | Stitches one-shot MOLT injections into **multi-step async Loom workflows** | Execution traces + agent states across long-running background tasks | **Context continuity across pipelines** | **$249–$449** | 5m · depth 3 |
| **`git-state-snapshotter`** — The Time Machine | Hooks `~/.whorl/agents/` Git-like versioning at **Instar 5 (Molt)** | Code mutations + differential state histories | **Zero-downtime rollback on poisoned mutations** | **$199–$399** | 6h · depth 2 |
| **`arena-logic-gladiator`** — The Evolution Engine | Pits **2 variant prompts** in **Whorl Arena** | Benchmark scores + token usage + Oracle passes | **Survival-of-the-fittest mutation rate** | **$199–$399** | 1h · depth 3 |

## Bus types (18 atomic + 4 MOLT)

- **Atomic (18):** `agent.register / heartbeat / deregister` · `task.dispatch / result / cancel / timeout` · `state.update / query / response` · `score.record / ack / drill.sweep_start / drill.sweep_done` · `guard.check / status / restart / result`
- **MOLT extensions (4):** `molt.hydrate / molt.sidecar / molt.mutation / molt.oracle_verdict`

All are implemented in `src/skill/whorl_bus.py` (`WhorlBusDispatcher`). See `Whorl/docs/AGENT_BUS_SPEC.md` for the filesystem bus contract.

## Architectural upgrades (how they plug in)

### 1. Zero-Network Bus Transport
**Wire `scout.py` to deposit sidecar context straight into `~/.whorl/bus/` via atomic file writes.**
- `src/skill/scout.py` now optionally deposits every bake into the bus (`molt.sidecar` broadcast) — headless nodes on Termux/Chromebook/desktop tail `~/.whorl/bus/bus.jsonl` and `inbox/` without opening ports.
- `src/skill/inference_bridge.py` deposits hydrated prompts as `molt.hydrate` so offline consumers see the preview without the full RAG.
- **Termux/Chromebook/desktop:** `bus.poll_inbox("molt-dispatcher")` or `tail -f ~/.whorl/bus/log/bus.jsonl | jq`.

### 2. State Branching & Rollbacks
**Use Whorl's Git-like tree (`~/.whorl/agents/molt-<skill>/` or `rag_storage/molt_state/molt-<skill>/` fallback) to snapshot before every `apply_mutation()`.**
- `src/skill/state_snapshotter.py` — snapshots `frontmatter + body_hash` pre-mutate as `vN`, commits post-mutate, exposes `rewind(skill, version)`, `branch(...)`, `diff(v1, v2)`, `log(...)`.
- `src/skill/skill_manager.py` — `apply_mutation(..., snapshotter, bus)` now snapshots before, reports to bus on both `block` and `pass`, and rewinds via `rewind_skill(skill, version)` (zero-downtime).
- If Oracle flags a poisoned mutation or tests break, `StateSnapshotter.rollback_on_failure(skill, before_version, reason)` instantly restores the last known good commit.
- **Instar 5 hook:** `git-state-snapshotter` auto-snapshots at Molt for audit; use `branch()` to fork a risky morph and `rewind()` to kill it.

### 3. Headless Overseer Integration
**Connect `whorl Overseer daemon` directly to MOLT's Governor.**
- `src/skill/governor.py` — `audit_to_overseer(whorl_dir)` exposes `audit_lines + last_event + active_scopes + pending` for the sweep; `heartbeat_to_bus(agent_name)` pushes bus heartbeats so the Overseer monitors **session TTLs + audit logs across multiple CLI tools** without polling files.
- Overseer rules live at `~/Overseer/rules.json` — no MOLT change needed; MOLT just becomes legible to the existing sweep (60s interval, ~20k files). MOLT stays **zero-bloat**: no daemon started, no elevation required.

### 4. Arena Evolution Loop
- `src/skill/arena_gladiator.py` — pits variant prompts for the same skill, scores by `token_proxy + Oracle verdict + latency` (and Whorl Arena judge when available), reports `mutation_rate = wins / total`. Use `evolve(skill, variants, rounds)` to rank variants and feed the mutation rate back into Scout interval tuning.

## Which wire first? → `whorl-bus-dispatcher`

**Answer: `whorl-bus-dispatcher` first**, then Arena.

**Why:** The bus is the nervous system. Once it's wired, Loom + state + Arena all ride it for free.
- Dispatcher already verified: `WhorlBusDispatcher(agent_name="test-molt").send("broadcast","molt.hydrate",{...})` → `~/.whorl/bus/inbox/broadcast/*.json` + `bus.jsonl`.
- Arena auto-evaluator (`arena-logic-gladiator`) then scrapes `arena_signals.jsonl + Oracle + token` and emits `mutation_rate` — but it needs the bus to distribute the winning variant.

**Bring-up (headless-verified):**

```python
from src.skill.whorl_bus import WhorlBusDispatcher
bus = WhorlBusDispatcher(agent_name="molt-dispatcher")
print(bus.status())           # available, types=22
bus.monitor_bus()             # {total_inbox, dead_letters, clock_latency_ms, zero_drop}

from src.skill.loom_weaver import LoomThreadWeaver
weaver = LoomThreadWeaver(bus=bus)
weave = weaver.weave(skill="saas-churn-oracle", prompts=["score acme-corp", "draft save playbook"])
print(weaver.report(weave["workflow_id"]))

from src.skill.state_snapshotter import StateSnapshotter
snap = StateSnapshotter()
snap.snapshot("saas-churn-oracle", {"body_hash": "abc"}, label="pre-evolve")
# ... mutate ...
snap.rewind("saas-churn-oracle", to_version=1)  # zero-downtime

from src.skill.arena_gladiator import ArenaGladiator
ArenaGladiator(bus=bus).combat("saas-churn-oracle",
    red={"prompt": "tight variant", "oomf": 2},
    blue={"prompt": "verbose variant", "oomf": 4},
    challenge_id="hallucination_field")

from src.skill.governor import Governor
Governor().audit_to_overseer()   # exposed to ~/Overseer sweep
Governor().heartbeat_to_bus()    # session TTL -> Whorl bus
```

## Bundle map (16 total)

```
Flagship 4 (one-shot):                        Hive 4 (distributed):
  saas-churn-oracle  $199–$499                  whorl-bus-dispatcher     $299–$549 ★ first
  adversary-emulator $299–$599                  loom-thread-weaver       $249–$449
  bureaucracy-judo   $149–$349                  git-state-snapshotter    $199–$399
  talent-singularity $249+bounty                arena-logic-gladiator    $199–$399
Toolchain + MCP:                              Sovereign 3 (ACTUAL Recursive Engine):
  mcp-replacement    $199–$399                  molt-instar-autoloop     $349–$699
  negotiation-ghost  $149–$349                  akasha-mutation-vault    $299–$549
  dopamine-reverse   $79–$199                  merkaba-claw-bridge      $299–$599 ★ Implor→Thoth first
  scout-foreman      $49 (free w/ 2+)
  provenance-oracle  $199–$449
```

All 16 validate: `python tools/marketplace/validate_bundle.py --all` (16 PASS).

See `SOVEREIGN_LOOP.md` — ACTUAL Recursive Engine (Implor→Thoth→Merkaba→Claw→Endempts→Akasha) + autoloop/vault/bridge.

## Source map

- `src/skill/whorl_bus.py` — 18 + 4 types, register/heartbeat, send/read/ack, `send_molt_hydrate`, `monitor_bus`, zero-network fallback
- `src/skill/state_snapshotter.py` — Whorl `~/.whorl/agents/molt-<skill>/` or `rag_storage/molt_state/` fallback, `snapshot/rewind/branch/diff/log`
- `src/skill/loom_weaver.py` — `weave(skill,prompts)`, `chain`, `resume`, `report`, bus dispatch per step, `rag_storage/loom/<workflow>.json`
- `src/skill/arena_gladiator.py` — `combat(skill,red,blue)`, `evolve(skill,variants,rounds)`, `history`, Whorl Arena signals + bus scores
- Patches: `src/skill/scout.py` (bus deposit), `src/skill/skill_manager.py` (snapshot+bus in `apply_mutation`), `src/skill/governor.py` (Overseer `audit_to_overseer` + `heartbeat_to_bus`), `src/skill/inference_bridge.py` (hydrate bus preview)

See also: `Whorl/docs/AGENT_BUS_SPEC.md`, `Whorl/docs/SIGNAL_LOOM.md`, `Whorl/whorl/arena/__init__.py`, `Overseer/rules.json`.
