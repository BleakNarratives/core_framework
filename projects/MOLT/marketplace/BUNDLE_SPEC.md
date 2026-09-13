# MOLT Marketplace — Living Skill Bundle Spec

Every sellable unit is **not a text file** — it's a self-updating runtime.

```
bundles/<skill>/
  SKILL.md            # Living Markdown template (committed, versioned)
  sidecar.json        # last hydrated payload (JSON — what the IDE sees as already-fetched)
  sidecar.schema.json # JSON Schema for sidecar (validation + types for MCP replacement)
  daemon/
    scout.py          # cron/systemd shim — pre-fetches on schedule, no MCP server process
    config.yaml       # cadence + feeds + OOMF level + oracle gate
  LICENSE.md          # per-license entitlements (what Scout feeds are unlocked)
  LISTING.md          # marketplace copy (hydrated zero-bloat pitch)
  receipts/           # .grimoire-style delivery receipts (optional, for subscription audit)
```

## What the buyer actually gets

1. **`SKILL.md`** — the Living Markdown they hydrate with one API call.
2. **Scout daemon** — local cron job (no MCP server to run). Pre-fetches on schedule directly into `sidecar.json` so the prompt is already 100% hydrated when they open their IDE — **0 tool calls required**.
3. **Sidecar contract** — typed, versioned, validates at startup. Toolchains can compose sidecars without calling tools.

## Why this commands $199–$499

- **Hydrated zero-bloat metric:** We prove the listing with a before/after: the same task took **N tool calls → 0**. Buyers grok this instantly — it's a cost and latency cut of **70–90%**.
- **Feeds get smarter without burning API loops.** The Scout daemon runs locally on a cron, not as a turn inside the chat. No tool-call tax.

## Subscription model (retainer)

- Base purchase = `SKILL.md` + daemon + sidecar schema + first hydrate.
- Monthly retainer = access to **private, high-frequency Scout feeds**: threat intel, stealth job boards, regulatory scrapers, telemetry playbooks. This is gated in `sidecar.json` via `feed_entitlements` and enforced by the Oracle gate + license key check (offline-capable).

## Authoring a bundle

```bash
# 1) Generate from the Living template
python -m src.creation.engine --skill saas-churn-oracle --template templates/SKILL.template.md

# 2) Scaffold the bundle
python tools/marketplace/scaffold_bundle.py --skill saas-churn-oracle --price-tier high

# 3) Validate
python tools/marketplace/validate_bundle.py bundles/saas-churn-oracle/
```

See: `src/skill/gambit.py` (buyer advances via Instar ladder → unlocks deeper Scout feeds over time).

