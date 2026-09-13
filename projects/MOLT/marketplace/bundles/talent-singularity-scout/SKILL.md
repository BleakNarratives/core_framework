---
name: talent-singularity-scout
version: 1.0.0
scout:
  depth: 3
  interval: "2h"
  target_domains: ["github.com", "x.com", "discourse.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Talent Singularity Scout — Living Runtime (Hydrated Zero-Bloat)

> `talent-singularity-scout` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: commit velocity, github x signals, latent discourse

Baked into ``talent_leads`, `signal_strength`, `reach_playbook`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `commit_velocity` — local Scout feed
- `github_x_signals` — local Scout feed
- `latent_discourse` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``talent_leads`, `signal_strength`, `reach_playbook``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp talent-singularity-scout/SKILL.md .agents/skills/talent-singularity-scout/SKILL.md
cp talent-singularity-scout/sidecar.json rag_storage/sidecars/talent-singularity-scout.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill talent-singularity-scout --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** VC & Recruiters
- **Tier:** bounty — **$249 + bounty share** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
