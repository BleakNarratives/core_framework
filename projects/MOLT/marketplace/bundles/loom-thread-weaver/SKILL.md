---
name: loom-thread-weaver
version: 1.0.0
scout:
  depth: 3
  interval: "5m"
  target_domains: ["whorl.loom", "rag_storage/loom", "~/.whorl/bus"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Loom Thread Weaver — Living Runtime (Hydrated Zero-Bloat)

> `loom-thread-weaver` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: execution traces, agent states, chain digests, loom weaves

Baked into ``weave_index`, `trace_tail`, `continuity_digest`, `resume_points`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `execution_traces` — local Scout feed
- `agent_states` — local Scout feed
- `chain_digests` — local Scout feed
- `loom_weaves` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``weave_index`, `trace_tail`, `continuity_digest`, `resume_points``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp loom-thread-weaver/SKILL.md .agents/skills/loom-thread-weaver/SKILL.md
cp loom-thread-weaver/sidecar.json rag_storage/sidecars/loom-thread-weaver.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill loom-thread-weaver --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Ops & AI engineers (multi-step async pipelines)
- **Tier:** hive — **$249–$449** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
