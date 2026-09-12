# Pheromone Schema v1

One event shape, every signal type. This replaces "STANK.md has one format, WHO_DID_WHAT.md has another, card.json has a third" with a single append-only log any agent — yours, CodeBuddy, Gemini, an external A2A caller — can read and understand without knowing which subsystem wrote it.

## The shape

Every pheromone is one JSON object, one per line, in `pheromones.jsonl`:

```json
{
  "id": "phm_20260908_0001",
  "type": "VALIDATION_PASS",
  "source": "ToolMapper",
  "path": "lib/swarm/spark_integrity.py",
  "timestamp": "2026-09-08T14:02:11Z",
  "strength": 1.0,
  "decay_rate": 0.0,
  "payload": {
    "entity_class": "Spark",
    "capabilities": ["bus_watch", "fabrication_detection"]
  }
}
```

## Fields

| Field | Meaning |
|---|---|
| `id` | Unique, sortable (date-prefixed is fine). |
| `type` | One of the enum below. |
| `source` | Which agent/subsystem laid this trace — `ToolMapper`, `Spark_integrity_v1`, `CodeBuddy`, a human username, etc. |
| `path` | File or directory this pheromone is about. Empty string if it's not file-scoped (e.g. a task claim on an abstract task). |
| `timestamp` | ISO 8601 UTC. Always. |
| `strength` | 0.0–1.0. How strong the signal is right now. Most events start at 1.0. |
| `decay_rate` | How fast `strength` fades per hour of no reinforcement. `0.0` = permanent (a CUT decision doesn't need to fade). A `TASK_CLAIM` should decay — that's what lets a stale claim stop blocking other agents without anyone manually clearing it. |
| `payload` | Type-specific detail. Whatever that event needs, nothing more. |

## Type enum

- `VALIDATION_PASS` — ToolMapper verified a SwarmEntity. Replaces the implicit signal that used to only exist as a card.json file.
- `VALIDATION_FAIL` — dead limb found. This *is* what gets written to STANK.md — STANK.md becomes a generated view of `pheromones.jsonl` filtered by type, not its own source of truth.
- `CONTRIBUTION` — an agent did a thing worth recording. This *is* what gets written to WHO_DID_WHAT.md, same relationship as above.
- `TASK_CLAIM` — an agent is starting work on a path/task. This is the piece that didn't exist before tonight and is the actual fix for two agents writing the same file. `decay_rate` should be nonzero (e.g. fades to 0 over 1 hour) so an agent that crashed mid-task doesn't block everyone else forever.
- `TASK_RELEASE` — explicit "I'm done" companion to a claim, so you don't have to wait for decay in the normal case.
- `CARD_EMIT` — same data currently in `*.card.json`, just also logged to the shared stream so an agent doesn't have to glob the whole directory tree to discover what exists.
- `ABSORB_DECISION` — Phase 1's keep/merge/cut judgment calls, in the same stream as everything else instead of a separate manifest file.

## Why decay matters (this is the actual stigmergy part)

A `VALIDATION_FAIL` should never decay — a dead file is dead until someone fixes it. A `TASK_CLAIM` *should* decay — that's the ant-colony property that makes the system self-healing. Real ant trails fade if not reinforced, so a path nobody's walking stops attracting ants. Applied here: if an agent claims a task and then hangs (like V and the Moto 4 session did tonight), its claim naturally fades instead of permanently locking that task out for every other agent. No manual cleanup required — that's the entire point of stigmergy over explicit locking.

## Backward compatibility

STANK.md and WHO_DID_WHAT.md don't need to disappear immediately. A tiny reader script (`pheromone_views.py`, companion to this) can regenerate both as filtered, human-readable views of `pheromones.jsonl` on demand — so nothing that already depends on reading those files breaks, but there's now one real source of truth underneath them.
