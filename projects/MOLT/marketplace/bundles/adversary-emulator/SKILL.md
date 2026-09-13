---
name: adversary-emulator
version: 1.0.0
scout:
  depth: 4
  interval: "30m"
  target_domains: ["nvd.nist.gov", "cisa.gov", "github.com/exploits"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Adversary Emulator — Living Runtime (Hydrated Zero-Bloat)

> `adversary-emulator` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: cve feed, cisa kev, exploit pocs

Baked into ``defense_rules`, `zero_day_drafts`, `coverage_delta`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `cve_feed` — local Scout feed
- `cisa_kev` — local Scout feed
- `exploit_pocs` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``defense_rules`, `zero_day_drafts`, `coverage_delta``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp adversary-emulator/SKILL.md .agents/skills/adversary-emulator/SKILL.md
cp adversary-emulator/sidecar.json rag_storage/sidecars/adversary-emulator.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill adversary-emulator --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** SecOps & Lead Devs
- **Tier:** high — **$299–$599** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
