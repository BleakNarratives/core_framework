# MOLT Marketplace — Living Skill bundles

> Every listing is a **self-updating runtime**, not a text file. Scout daemon pre-fetches into `sidecar.json` so the prompt is **already hydrated — 0 tool calls**. Hive bundles make them **distributed + versioned + evolving** via `~/.whorl/bus/`.

## Bundle index (16 bundles · `validate_bundle --all` PASS)

| Bundle | Category | For | Price | Scout |
|---|---|---|---|---|
| `saas-churn-oracle` | High-Ticket B2B | B2B founders & Sales Ops | $199–$499 | 1h · depth 3 |
| `adversary-emulator` | Cybersecurity | SecOps & Lead Devs | $299–$599 | 30m · depth 4 |
| `bureaucracy-judo` | Legal / Compliance | LegalTech & Agencies | $149–$349 | 6h · depth 3 |
| `talent-singularity-scout` | HR / Executive | VC & Recruiters | $249 + bounty | 2h · depth 3 |
| `mcp-replacement` | **MCP Replacement** | Dev + Product Ops (Jira/GitHub/HubSpot) | $199–$399 | 15m · depth 3 |
| `negotiation-ghost` | **Kid: Voice/Text Whisperer** | Founders / Sales / M&A | $149–$349 | 1h · depth 4 |
| `dopamine-architect-in-reverse` | **Kid: Attention OS** | Families & Deep-work teams | $79–$199 | 1h · depth 2 |
| `scout-foreman` | **Marketplace utility** | Every buyer (herds Scouts) | $49 (free w/ 2+) | 15m · depth 2 |
| `provenance-oracle` | **Marketplace utility** | Media (Sora/Flux/Veo) | $199–$449 | 1h · depth 3 |
| `whorl-bus-dispatcher` | **Hive: Nervous System** | Distributed teams (Termux/Chromebook/desktop) | $299–$549 | 1m · depth 3 |
| `loom-thread-weaver` | **Hive: Choreographer** | Ops & AI engineers | $249–$449 | 5m · depth 3 |
| `git-state-snapshotter` | **Hive: Time Machine** | SRE & Security | $199–$399 | 6h · depth 2 |
| `arena-logic-gladiator` | **Hive: Evolution Engine** | ML/R&D teams | $199–$399 | 1h · depth 3 |
| `molt-instar-autoloop` | **Sovereign: Autoloop** | AI Lab Leads & Sovereign Founders | $349–$699 | 10m · depth 4 |
| `akasha-mutation-vault` | **Sovereign: Vault** | SRE & Security (audit) | $299–$549 | 10m · depth 3 |
| `merkaba-claw-bridge` | **Sovereign: Bridge** | Platform & Infra (Merkaba+Claw) | $299–$599 | 5m · depth 3 |

## Banner (paste at top of every listing)

> **Stop paying the MCP tool-calling tax — this prompt is already hydrated. 0 tool calls. Saves 70–90% on API spend.**

## Subscription model

Base = `SKILL.md + sidecar.json + sidecar.schema.json + daemon/ + first hydrate`. Monthly retainer = private high-frequency Scout feeds (gated via `entitlements.active` + `license.key` + Oracle gate, offline-capable). See each bundle's `LICENSE.md`.

## Docs

- `BUNDLE_SPEC.md` — bundle layout + authoring flow
- `PITCH_AND_PRICING.md` — all pricing, banner, proof flow, what's in the zip
- `MCP_REPLACEMENT.md` — "Stop paying the MCP tax" pitch + demo script (N → 0)
- `KID_TOOLCHAINS.md` — Scout + Oracle sub-agent bundles + composition
- `bundles/<skill>/LISTING.md` — paste-ready listing per bundle
- `bundles/whorl-bus-dispatcher/` — **Wire first** — the nervous system (18 + 4 bus types, zero-network)
- `bundles/<skill>/LICENSE.md` — feed entitlements (base vs premium)

## Validate

```bash
python tools/marketplace/scaffold_bundle.py --all
python tools/marketplace/validate_bundle.py --all
```

See: `src/skill/gambit.py` (buyer advances via Instar ladder → unlocks deeper Scout feeds).

See also: `INTEGRATIONS.md` — OpenRouter / VS Code / Vibe / Aider (copy-paste).
See also: `HIVE_MIND.md` — Whorl bus + Loom + Agent State + Arena + Overseer (wire **whorl-bus-dispatcher first**).
See also: `SOVEREIGN_LOOP.md` — ACTUAL Recursive Engine + the two junctions (Implor→Thoth first, then Merkaba→Claw).
