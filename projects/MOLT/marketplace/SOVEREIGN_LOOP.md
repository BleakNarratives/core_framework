# MOLT Sovereign Loop — ACTUAL Recursive Improvement Engine

> The hive is persistent. The sovereign loop makes it **self-rewriting**. Architecture doesn't just execute — it versions, judges, and replaces itself.

```
   ┌─────────────────────────────────────────────────────────────┐
   │                       1. INTROSPECT                         │
   │   [Implor] analyzes codebase, token overhead, precision     │
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                      2. ORCHESTRATE                         │
   │   [Hermes/Thoth] synthesizes patch — consults Akasha ledger │
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                        3. ROUTE                             │
   │   [Merkaba] transports payloads (sandbox · Whorl bus · mesh)│
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                        4. EXECUTE                           │
   │   [Zero/Open Claw] applies patch · compiles · tests          │
   └──────────────────────────────┬──────────────────────────────┘
                                  ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                        5. VALIDATE                          │
   │   [Endempts] gate → [Akasha] commit / rollback               │
   └─────────────────────────────────────────────────────────────┘
```

## Layer matrix

| Layer | System | Role in loop | Recursive function |
|---|---|---|---|
| **Foundational** | **Akasha** | Universal memory & state storage | Persistent vault + checkpoint journal — every mutation + failure is ledgered, future cycles consult it before regenerating |
| **Introspection** | **Implor** | Internal dialogue & reflection | RepoWalker + ProfileBuilder sweep → bottleneck blueprint (local CC check always runs even without Implor) |
| **Vehicular** | **Merkaba** | Geometry / routing / transport | Ba→Ka generation (`ka_gen.py`) + Whorl bus + Thoth `agent_bus` parallel deposit — zero-network |
| **Execution** | **Zero / Open Claw** | Low-level shell & HW | Gated `apply_mutation` via `SkillManager` — compile + `unittest discover` — no silent self-rewrite |
| **Orchestration** | **Hermes / Thoth** | Comms & synthesis | `agent_bus.emit_event` + `MotherBrain.tick()` — distributed generation + guard note when Akasha says this failed before |
| **Boundary** | **Endempts** | Boundaries & termination | SHIP / HOLD / KILL + rollback handle (`StateSnapshotter.rewind`) + Akasha `Checkpoint` seal |

## Two junctions — which first?

**Wire `Implor → Thoth` first, then `Merkaba → Claw`.**

* **`Implor → Thoth` (`src/sovereign/bridges.implor_to_thoth_packet`)** builds the `ContextPacket` (Akasha) from the Implor scan and emits `molt.implor.packet` on Thoth's `agent_bus`; `MotherBrain.tick()` fires immediately. This is the **thinking** wire — without it, downstream routing has nothing worth routing.
* **`Merkaba → Claw` (`src/sovereign/bridges.merkaba_claw_bridge`)** then takes the orchestrated `patch_plan` and materializes it as a Merkaba Ka (`ka_gen.py` + `validator.py`), deposits it on both `Whorl bus` (zero-network) and `agent_bus`, and stages an `openclaw` intent. This is the **doing** wire — gated by Oracle+Governor, staged as intent-only unless `--elevate write` is set.

That order is what `RecursiveEngine.cycle()` does: Introspect(Implor) → Orchestrate(Thoth+Akasha) → Route(Merkaba+Whorl) → Execute(Claw, gated) → Validate(Endempts+Akasha).

## Security — no clause bypasses the gate

* **Governor** is checked before any write/exec/network. `RecursiveEngine` defaults to **staged intent only** (`\"staged — awaiting --elevate write\"`) — tests + compile + Oracle still run, but files aren't mutated silently.
* **Oracle `strict`** audits every staged mutation (`injection / drift / HIPAA / bloat`) before `apply_mutation` — `block` rolls back even in `user_only` mode.
* `RECURSIVE_DIR = ~/RootBase/logs/shared/recursive_engine/` — journal `cycles.jsonl` is append-only, bus deposits are typed (`molt.recursive.*`), Akasha vault objects are content-hashed.

## The 3 sovereign daemons (concrete — not theater)

| Daemon | Module | What it does | Price |
|---|---|---|---|
| **`molt-instar-autoloop`** | `src/sovereign/daemons.tick_instar_autoloop` + `src/sovereign/recursive_engine.molt_instar_autoloop` + `RecursiveEngine.autoloop()` | Triggers `Implor → Thoth → Merkaba → Claw` mutations **when idle exceeds threshold** (Thoth bus line-count stability sample). Runs `max_cycles`; each cycle is the full 5-phase loop. | **$349–$699** |
| **`akasha-mutation-vault`** | `src/sovereign/daemons.akasha_mutation_vault` + `src/sovereign/bridges.akasha_store_evidence` | **Git-backed, crypto-signed store** for every staged/rewritten file (or `patch_plan` while gated). Index at `recursive_engine/mutation_vault_index.jsonl` + `Avault` fallback at `~/.akasha`-like dir. Rollback handle is `StateSnapshotter.rewind()`. | **$299–$549** |
| **`merkaba-claw-bridge`** | `src/sovereign/daemons.tick_merkaba_claw_bridge` + `src/sovereign/bridges.merkaba_claw_bridge` | **Zero-latency IPC** Merkaba routing matrix ↔ Open Claw execution — on-device (Whorl bus + agent_bus + staged intent), no sockets opened. Ka synthesis via `ka_gen.py` whether remote mesh is present or not. | **$299–$599** |

## Engine API

```python
from src.sovereign import RecursiveEngine, implor_to_thoth_packet, merkaba_claw_bridge

# 1) Single self-improvement turn (safe, no elevate = staged intent)
eng = RecursiveEngine(project_id="molt-sovereign")
rec = eng.cycle(goal="reduce hydrate overhead 20% without losing RAG")
print(rec.outcome, rec.validate)   # rolled_back | committed | failed

# 2) The two junctions directly
pkt = implor_to_thoth_packet(codebase=".", goal="tighten preflight_gate", project_id="molt-sovereign")
# -> scan + ContextPacket + agent_bus event + MotherBrain tick
route = merkaba_claw_bridge(intent="tighten preflight_gate", payload=rec.orchestrate["patch_plan"])

# 3) Autonomous daemon (idle-gated)
eng.autoloop(interval_s=600, idle_threshold_s=300, max_cycles=3)

# 4) Swarm / cron shims
from src.sovereign.daemons import tick_instar_autoloop, akasha_mutation_vault, tick_merkaba_claw_bridge
tick_instar_autoloop(max_cycles=1)         # safe single tick
akasha_mutation_vault()                    # vault last cycle + produce rollback handle
tick_merkaba_claw_bridge(intent="ship Ka for last patch_plan")
```

## Storage

* `~/RootBase/logs/shared/recursive_engine/cycles.jsonl` — append-only cycle journal (`CycleRecord.to_dict()`)
* `~/RootBase/logs/shared/recursive_engine/packet_<hash>.json` — Akasha `ContextPacket` sealed per cycle
* `~/RootBase/logs/shared/recursive_engine/mutation_vault_index.jsonl` — vault index
* `~/RootBase/logs/shared/recursive_engine/checkpoint_<cycle_id>.json` — Akasha `Checkpoint` when gate == SHIP
* Falls back to `rag_storage/molt_state/` when `Whorl`/`Akasha` home dirs aren't mounted — headless still runs.

## Source map

* `src/sovereign/recursive_engine.py` — `RecursiveEngine`, 5-phase helpers, `EngineConfig`, `molt_instar_autoloop`
* `src/sovereign/bridges.py` — `implor_to_thoth_packet`, `merkaba_claw_bridge`, `akasha_store_evidence`, `endempts_gate`
* `src/sovereign/daemons.py` — `tick_instar_autoloop`, `akasha_mutation_vault`, `tick_merkaba_claw_bridge`
* Hive underneath: `src/skill/whorl_bus.py`, `state_snapshotter.py`, `loom_weaver.py`, `arena_gladiator.py` + patches in `scout.py`, `skill_manager.py`, `governor.py`, `inference_bridge.py`

See also: `HIVE_MIND.md`, `BUNDLE_SPEC.md`, `Akasha/akasha/checkpoint.py`, `Akasha/akasha/packet.py`, `Merkaba/validator.py`, `Merkaba/ka_gen.py`, `thoth_orchestrator/agent_bus.py`.
