---
name: arena-logic-gladiator
version: 1.0.0
scout:
  depth: 3
  interval: "1h"
  target_domains: ["whorl.arena", "rag_storage/arena", "~/.whorl/arena_signals.jsonl"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Arena Logic Gladiator — Living Runtime (Hydrated Zero-Bloat)

> `arena-logic-gladiator` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: benchmark scores, oracle verdicts, token usage, elo updates

Baked into ``leaderboard`, `evolution_rate`, `survival_report`, `mutation_queue`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `benchmark_scores` — local Scout feed
- `oracle_verdicts` — local Scout feed
- `token_usage` — local Scout feed
- `elo_updates` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``leaderboard`, `evolution_rate`, `survival_report`, `mutation_queue``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp arena-logic-gladiator/SKILL.md .agents/skills/arena-logic-gladiator/SKILL.md
cp arena-logic-gladiator/sidecar.json rag_storage/sidecars/arena-logic-gladiator.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill arena-logic-gladiator --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** ML/R&D teams (survival-of-the-fittest skill evolution)
- **Tier:** hive — **$199–$399** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
