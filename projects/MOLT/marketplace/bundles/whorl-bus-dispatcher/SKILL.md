---
name: whorl-bus-dispatcher
version: 1.0.0
scout:
  depth: 3
  interval: "1m"
  target_domains: ["~/.whorl/bus", "whorl.core.config", "whorl.bus"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Whorl Bus Dispatcher — Living Runtime (Hydrated Zero-Bloat)

> `whorl-bus-dispatcher` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: bus inbox, dead letters, registry heartbeats, arena signals

Baked into ``bus_status`, `throughput`, `clock_latency`, `zero_drop_report`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `bus_inbox` — local Scout feed
- `dead_letters` — local Scout feed
- `registry_heartbeats` — local Scout feed
- `arena_signals` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``bus_status`, `throughput`, `clock_latency`, `zero_drop_report``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp whorl-bus-dispatcher/SKILL.md .agents/skills/whorl-bus-dispatcher/SKILL.md
cp whorl-bus-dispatcher/sidecar.json rag_storage/sidecars/whorl-bus-dispatcher.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill whorl-bus-dispatcher --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Distributed teams & edge nodes (Termux/Chromebook/desktop hive)
- **Tier:** hive — **$299–$549** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
