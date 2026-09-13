---
name: akasha-mutation-vault
version: 1.0.0
scout:
  depth: 3
  interval: "10m"
  target_domains: ["akasha.vault", "molt.state", "git.internal"]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---


> **SOVEREIGN LOOP** — ACTUAL Molt Recursive Engine (Implor→Thoth→Merkaba→Claw→Endempts→Akasha). Git-backed, cryptographically-signed mutation store — every rewrite hash-addressed with full rollback.
# Akasha Mutation Vault — Living Runtime (Hydrated Zero-Bloat)

> `akasha-mutation-vault` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: last cycle, vault object, snapshot chain

Baked into ``vault_index`, `checkpoint_id`, `rollback_target`` → hydrated prompt is ready when you open the IDE.

## Feeds

- `last_cycle` — local Scout feed
- `vault_object` — local Scout feed
- `snapshot_chain` — local Scout feed

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: ``vault_index`, `checkpoint_id`, `rollback_target``

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp akasha-mutation-vault/SKILL.md .agents/skills/akasha-mutation-vault/SKILL.md
cp akasha-mutation-vault/sidecar.json rag_storage/sidecars/akasha-mutation-vault.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill akasha-mutation-vault --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** SRE & Security (audit + rollback)
- **Tier:** high — **$299–$549** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
