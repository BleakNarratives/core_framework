---
name: dopamine-architect-in-reverse
version: 1.0.0
scout:
  depth: 2
  interval: "1h"
  target_domains: ["local.telemetry", "router.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Dopamine Architect In Reverse — Living Runtime (Hydrated Zero-Bloat)

> `dopamine-architect-in-reverse` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: app usage, screen time, social hooks, blocklist state

Baked into ``attention_report`, `hook_inventory`, `blocklist_patch`, `deep_work_schedule`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `app_usage` — local Scout feed
- `screen_time` — local Scout feed
- `social_hooks` — local Scout feed
- `blocklist_state` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``attention_report`, `hook_inventory`, `blocklist_patch`, `deep_work_schedule``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp dopamine-architect-in-reverse/SKILL.md .agents/skills/dopamine-architect-in-reverse/SKILL.md
cp dopamine-architect-in-reverse/sidecar.json rag_storage/sidecars/dopamine-architect-in-reverse.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill dopamine-architect-in-reverse --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Families & Deep-work teams (Attention OS)
- **Tier:** mid — **$79–$199** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
