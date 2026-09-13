---
name: bureaucracy-judo
version: 1.0.0
scout:
  depth: 3
  interval: "6h"
  target_domains: ["state_filings.internal", "zoning.internal", "foia_logs.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Bureaucracy Judo — Living Runtime (Hydrated Zero-Bloat)

> `bureaucracy-judo` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: regulatory filings, zoning updates, foia logs

Baked into ``filing_templates`, `eligibility_deltas`, `deadline_map`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `regulatory_filings` — local Scout feed
- `zoning_updates` — local Scout feed
- `foia_logs` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``filing_templates`, `eligibility_deltas`, `deadline_map``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp bureaucracy-judo/SKILL.md .agents/skills/bureaucracy-judo/SKILL.md
cp bureaucracy-judo/sidecar.json rag_storage/sidecars/bureaucracy-judo.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill bureaucracy-judo --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** LegalTech & Agencies
- **Tier:** mid — **$149–$349** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
