---
name: scout-foreman
version: 1.0.0
scout:
  depth: 2
  interval: "15m"
  target_domains: ["local.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Scout Foreman — Living Runtime (Hydrated Zero-Bloat)

> `scout-foreman` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: scout health, memory footprint, secret rotation, sweep results

Baked into ``herd_status`, `footprint_budget`, `key_vault_refs`, `sweep_log`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `scout_health` — local Scout feed
- `memory_footprint` — local Scout feed
- `secret_rotation` — local Scout feed
- `sweep_results` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``herd_status`, `footprint_budget`, `key_vault_refs`, `sweep_log``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp scout-foreman/SKILL.md .agents/skills/scout-foreman/SKILL.md
cp scout-foreman/sidecar.json rag_storage/sidecars/scout-foreman.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill scout-foreman --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Marketplace buyers (herds all Scouts)
- **Tier:** utility — **$49 (free with 2+ bundles)** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
