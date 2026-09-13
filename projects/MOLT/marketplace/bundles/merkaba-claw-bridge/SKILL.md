---
name: merkaba-claw-bridge
version: 1.0.0
scout:
  depth: 3
  interval: "5m"
  target_domains: ["merkaba.ka", "whorl.bus", "openclaw.endpoint"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---


> **SOVEREIGN LOOP** — ACTUAL Molt Recursive Engine (Implor→Thoth→Merkaba→Claw→Endempts→Akasha). Zero-latency IPC Merkaba routing matrix ↔ Open Claw execution — on-device, no sockets, Oracle+Governor gated.
# Merkaba Claw Bridge — Living Runtime (Hydrated Zero-Bloat)

> `merkaba-claw-bridge` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: ka package, bus route, claw staged intent

Baked into ``ka_path`, `route_receipt`, `claw_gate`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `ka_package` — local Scout feed
- `bus_route` — local Scout feed
- `claw_staged_intent` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``ka_path`, `route_receipt`, `claw_gate``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp merkaba-claw-bridge/SKILL.md .agents/skills/merkaba-claw-bridge/SKILL.md
cp merkaba-claw-bridge/sidecar.json rag_storage/sidecars/merkaba-claw-bridge.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill merkaba-claw-bridge --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Platform & Infra (Merkaba + Claw)
- **Tier:** high — **$299–$599** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
