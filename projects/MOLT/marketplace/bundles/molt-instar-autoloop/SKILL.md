---
name: molt-instar-autoloop
version: 1.0.0
scout:
  depth: 4
  interval: "10m"
  target_domains: ["implor.internal", "thoth.bus", "openclaw.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---


> **SOVEREIGN LOOP** — ACTUAL Molt Recursive Engine (Implor→Thoth→Merkaba→Claw→Endempts→Akasha). Daemon that triggers Implor→Thoth→Open Claw mutations when bus idle — self-evolution without human prompt.
# Molt Instar Autoloop — Living Runtime (Hydrated Zero-Bloat)

> `molt-instar-autoloop` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: implor blueprint, thoth synthesis, idle signal

Baked into ``next_goal`, `blueprint`, `last_verdict`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `implor_blueprint` — local Scout feed
- `thoth_synthesis` — local Scout feed
- `idle_signal` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``next_goal`, `blueprint`, `last_verdict``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp molt-instar-autoloop/SKILL.md .agents/skills/molt-instar-autoloop/SKILL.md
cp molt-instar-autoloop/sidecar.json rag_storage/sidecars/molt-instar-autoloop.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill molt-instar-autoloop --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** AI Lab Leads & Sovereign Founders
- **Tier:** high — **$349–$699** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
