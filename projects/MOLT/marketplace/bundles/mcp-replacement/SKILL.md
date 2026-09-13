---
name: mcp-replacement
version: 1.0.0
scout:
  depth: 3
  interval: "15m"
  target_domains: ["api.github.com", "atlassian.net", "api.hubspot.com"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Mcp Replacement — Living Runtime (Hydrated Zero-Bloat)

> `mcp-replacement` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: api schemas, active tickets, recent commits, deal pipeline

Baked into ``schemas_cached`, `ticket_snapshot`, `commit_digest`, `pipeline_state`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `api_schemas` — local Scout feed
- `active_tickets` — local Scout feed
- `recent_commits` — local Scout feed
- `deal_pipeline` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``schemas_cached`, `ticket_snapshot`, `commit_digest`, `pipeline_state``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp mcp-replacement/SKILL.md .agents/skills/mcp-replacement/SKILL.md
cp mcp-replacement/sidecar.json rag_storage/sidecars/mcp-replacement.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill mcp-replacement --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Dev teams & Product Ops (Jira/GitHub/HubSpot replacement)
- **Tier:** high — **$199–$399** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
