---
name: git-state-snapshotter
version: 1.0.0
scout:
  depth: 2
  interval: "6h"
  target_domains: ["~/.whorl/agents", "rag_storage/molt_state"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Git State Snapshotter — Living Runtime (Hydrated Zero-Bloat)

> `git-state-snapshotter` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: version logs, mutation diffs, branch maps, rollback events

Baked into ``snapshot_head`, `version_history`, `diff_preview`, `rewind_receipts`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `version_logs` — local Scout feed
- `mutation_diffs` — local Scout feed
- `branch_maps` — local Scout feed
- `rollback_events` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``snapshot_head`, `version_history`, `diff_preview`, `rewind_receipts``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp git-state-snapshotter/SKILL.md .agents/skills/git-state-snapshotter/SKILL.md
cp git-state-snapshotter/sidecar.json rag_storage/sidecars/git-state-snapshotter.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill git-state-snapshotter --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** SRE & Security (zero-downtime rollback)
- **Tier:** hive — **$199–$399** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
