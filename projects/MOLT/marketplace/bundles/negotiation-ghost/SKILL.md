---
name: negotiation-ghost
version: 1.0.0
scout:
  depth: 4
  interval: "1h"
  target_domains: ["sec.gov", "levels.fyi", "company.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Negotiation Ghost — Living Runtime (Hydrated Zero-Bloat)

> `negotiation-ghost` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: sec filings, salary bands, deal history, playbook hints

Baked into ``counterparty_dossier`, `band_table`, `leverage_map`, `whisper_lines`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `sec_filings` — local Scout feed
- `salary_bands` — local Scout feed
- `deal_history` — local Scout feed
- `playbook_hints` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``counterparty_dossier`, `band_table`, `leverage_map`, `whisper_lines``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp negotiation-ghost/SKILL.md .agents/skills/negotiation-ghost/SKILL.md
cp negotiation-ghost/sidecar.json rag_storage/sidecars/negotiation-ghost.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill negotiation-ghost --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Founders, Sales & M&A (live deal whisperer)
- **Tier:** high — **$149–$349** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
