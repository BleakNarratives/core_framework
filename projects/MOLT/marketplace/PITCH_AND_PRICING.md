# MOLT Marketplace — Pitch & Pricing (paste-ready)

## One-line banner (put at top of every listing)

> **Stop paying the MCP tool-calling tax — this prompt is already hydrated. 0 tool calls. Saves 70–90% on API spend.**

## The 3-sentence pitch

Static prompt engineering fails the moment data changes, regulation shifts, or edge-case mistakes cost real money. A **MOLT Living Skill** is not a text file — it's a **self-updating runtime**: a `SKILL.md` template plus a background Python **Scout daemon** that pre-fetches on a local cron into a typed `sidecar.json`. When the developer opens their IDE the prompt is already 100% hydrated — **no MCP server, no multi-turn `LLM → call tool → wait → LLM` loop, 70–90% lower API cost.**

## Price ladder

| Bundle | For | Price (base) | Scout interval | Secret sauce |
|---|---|---|---|---|
| `saas-churn-oracle` | B2B founders & Sales Ops | **$199–$499** | 1h | telemetry + support tickets + pricing visits → risk playbooks |
| `adversary-emulator` | SecOps & Lead Devs | **$299–$599** | 30m | CVE + CISA KEV + exploit PoCs → zero-day defense rules |
| `bureaucracy-judo` | LegalTech & Agencies | **$149–$349** | 6h | regulatory filings + zoning + FOIA → auto-filing templates |
| `talent-singularity-scout` | VC & Recruiters | **$249 + bounty** | 2h | commit velocity + GitHub/X signals → 10x talent leads |
| `mcp-replacement` | Dev + Product Ops | **$199–$399** | 15m | **Jira/GitHub/HubSpot MCP replacement** — schemas + tickets + commits |
| `negotiation-ghost` | Founders / Sales / M&A | **$149–$349** | 1h | SEC filings + salary bands → live deal whisperer |
| `dopamine-architect-in-reverse` | Families & Deep-work teams | **$79–$199** | 1h | app usage + screen-time → router blocklist & deep-work schedule |
| `provenance-oracle` | Media (Sora/Flux/Veo) | **$199–$449** | 1h | C2PA + generator signatures → deepfake/provenance seal |
| `scout-foreman` | Every buyer | **$49** *(free with 2+)* | 15m | Herds all Scouts — health, memory, key rotation |
| `whorl-bus-dispatcher` | Distributed teams (Termux/Chromebook/desktop) | **$299–$549** | 1m | **18 atomic bus types** + 4 MOLT — zero-network hive bus |
| `loom-thread-weaver` | Ops & AI engineers | **$249–$449** | 5m | One-shots → **async Loom workflows** — context continuity |
| `git-state-snapshotter` | SRE & Security | **$199–$399** | 6h | **Git-like versioning** of skills — zero-downtime rollback |
| `arena-logic-gladiator` | ML/R&D teams | **$199–$399** | 1h | **Arena combat** of variants — survival-of-the-fittest mutation |
| `molt-instar-autoloop` | AI Lab Leads & Sovereign Founders | **$349–$699** | 10m | **Implor→Thoth→Claw autoloop** — self-evolution when idle |
| `akasha-mutation-vault` | SRE & Security (audit) | **$299–$549** | 10m | **Git-backed crypto vault** — every mutation hash-addressed |
| `merkaba-claw-bridge` | Platform & Infra (Merkaba+Claw) | **$299–$599** | 5m | **Zero-latency IPC** Merkaba matrix ↔ Claw execution |

## Hydrated zero-bloat metric (how to prove it)

Every listing includes a **before/after** in the video/screenshots:

1. **Before (MCP):** same task, N tool calls — show token count. Example: "what's blocked in sprint 17?" takes 4–8 calls via Jira + GitHub MCP.
2. **After (MOLT):** same question, `sidecar.json` already has `ticket_snapshot + commit_digest` — single hydrated prompt, **0 tool calls**.

Overlay: **`N → 0 tool calls · 70–90% API cost eliminated`**. Buyers grok this in 5 seconds.

## Subscription / retainer (how retainer monetizes)

- **Base purchase** = `SKILL.md` + `sidecar.json` (first hydrate) + `sidecar.schema.json` + `daemon/scout.py + config.yaml` + `LISTING.md`.
- **Monthly retainer** = access to **private, high-frequency Scout feeds** (threat intel, stealth job boards, regulatory scrapers, telemetry playbooks, salary band updates, etc.).
- **Gating:** `sidecar.json: entitlements.active` declares `[base]` vs `[base, premium]`; `daemon/config.yaml: entitlements + license.key` + **Oracle gate** enforce it (offline-capable nonce — works air-gapped). See each bundle's `LICENSE.md → Feed entitlements`.

Copy for pricing section:

> *Base = the Living Template + daemon + schema + first hydrate. Retainer = private high-frequency Scout feeds that get smarter without burning API loops — gated via `entitlements` + Oracle + license key (offline-capable).*

## Toolchain placement (for OpenRouter / VS Code / Vibe / Aider marketplaces)

- **MCP Replacement Runtime** — sell `mcp-replacement` as a *replacement* for Jira/GitHub/Postman/Hubspot MCP servers. One Scout cron → N integrations hydrated.
- **Kid (Sub-Agent) Toolchains** — `negotiation-ghost` + `dopamine-architect-in-reverse` are **Scout + Oracle bundles** that read each other's sidecars without calling tools (typed `sidecar.schema.json`). See `KID_TOOLCHAINS.md`.
- **Marketplace utilities** — `scout-foreman` + `provenance-oracle` are attachable to any IDE; both handle **OpenRouter, VS Code, Vibe, Aider** via `src/skill/inference_bridge.molt_one_shot` (works with any inference API).

## Authoring / validation commands (keep in listing for trust)

```bash
python tools/marketplace/scaffold_bundle.py --all             # scaffold the 4 flagships
python tools/marketplace/scaffold_bundle.py --skill my-skill  # or one custom bundle
python tools/marketplace/validate_bundle.py --all             # structural + schema + pitch checks
```

## What's actually in the zip (buyer's deliverable)

```
bundles/<skill>/
  SKILL.md            # Living Markdown template (versioned, gambit-enabled)
  sidecar.json        # last hydrated payload — what the IDE sees as already-fetched
  sidecar.schema.json # JSON Schema — typed contract for toolchain composition
  daemon/
    scout.py          # cron/systemd shim — no MCP server process to keep alive
    config.yaml       # cadence + feeds + OOMF + entitlements + license.key
  LICENSE.md          # base vs retainer entitlements
  LISTING.md          # paste-ready marketplace copy (hydrated pitch)
  receipts/           # optional .grimoire-style delivery receipts
```

Also see: `BUNDLE_SPEC.md` (bundle contract), `MCP_REPLACEMENT.md` (full MCP replacement guide), `KID_TOOLCHAINS.md` (sub-agent composition).

See: `HIVE_MIND.md` — Whorl × Loom hive mind: which wire first + headless Termux/Chromebook/desktop bring-up.
See: `SOVEREIGN_LOOP.md` — ACTUAL Recursive Engine (Implor→Thoth→Merkaba→Claw→Endempts→Akasha) + autoloop/vault/bridge.
See: `INTEGRATIONS.md` for the full OpenRouter / VS Code / Vibe / Aider guides.
