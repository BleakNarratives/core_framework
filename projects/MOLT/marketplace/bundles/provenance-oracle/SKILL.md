---
name: provenance-oracle
version: 1.0.0
scout:
  depth: 3
  interval: "1h"
  target_domains: ["c2pa.org", "verify.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# Provenance Oracle — Living Runtime (Hydrated Zero-Bloat)

> `provenance-oracle` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: c2pa manifests, generator signatures, attestation log

Baked into ``manifest_index`, `deepfake_flags`, `provenance_seal`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `c2pa_manifests` — local Scout feed
- `generator_signatures` — local Scout feed
- `attestation_log` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``manifest_index`, `deepfake_flags`, `provenance_seal``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp provenance-oracle/SKILL.md .agents/skills/provenance-oracle/SKILL.md
cp provenance-oracle/sidecar.json rag_storage/sidecars/provenance-oracle.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill provenance-oracle --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** Media production houses (Sora/Flux/Veo pipeline)
- **Tier:** high — **$199–$449** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
