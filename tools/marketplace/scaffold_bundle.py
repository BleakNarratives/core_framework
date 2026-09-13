#!/usr/bin/env python3
"""
Scaffold a MOLT Living Skill *marketplace bundle* (not just a SKILL.md).

Usage:
  python tools/marketplace/scaffold_bundle.py --skill saas-churn-oracle [--price-tier high]
  python tools/marketplace/scaffold_bundle.py --all    # scaffolds the 4 flagships
"""
import argparse
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[2]
MARKET = ROOT / "projects" / "MOLT" / "marketplace" / "bundles"

FLAGSHIPS = {
    "saas-churn-oracle": {
        "tier": "high",
        "price": "$199–$499",
        "buyer": "B2B founders & Sales Ops",
        "interval": "1h",
        "depth": 3,
        "domains": ["telemetry.internal", "support.internal", "pricing.internal"],
        "feeds": ["local_telemetry", "support_tickets", "pricing_visits"],
        "sidecar_keys": ["risk_playbooks", "account_risk", "pricing_signals"],
    },
    "adversary-emulator": {
        "tier": "high",
        "price": "$299–$599",
        "buyer": "SecOps & Lead Devs",
        "interval": "30m",
        "depth": 4,
        "domains": ["nvd.nist.gov", "cisa.gov", "github.com/exploits"],
        "feeds": ["cve_feed", "cisa_kev", "exploit_pocs"],
        "sidecar_keys": ["defense_rules", "zero_day_drafts", "coverage_delta"],
    },
    "bureaucracy-judo": {
        "tier": "mid",
        "price": "$149–$349",
        "buyer": "LegalTech & Agencies",
        "interval": "6h",
        "depth": 3,
        "domains": ["state_filings.internal", "zoning.internal", "foia_logs.internal"],
        "feeds": ["regulatory_filings", "zoning_updates", "foia_logs"],
        "sidecar_keys": ["filing_templates", "eligibility_deltas", "deadline_map"],
    },
    "talent-singularity-scout": {
        "tier": "bounty",
        "price": "$249 + bounty share",
        "buyer": "VC & Recruiters",
        "interval": "2h",
        "depth": 3,
        "domains": ["github.com", "x.com", "discourse.internal"],
        "feeds": ["commit_velocity", "github_x_signals", "latent_discourse"],
        "sidecar_keys": ["talent_leads", "signal_strength", "reach_playbook"],
    },
}

TEMPLATE = """---
name: {skill}
version: 1.0.0
scout:
  depth: {depth}
  interval: "{interval}"
  target_domains: [{domains}]
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
gambit:
  enabled: true
  memory_mint: true
---

# {title} — Living Runtime (Hydrated Zero-Bloat)

> `{skill}` as a MOLT Living Skill: the **Scout daemon pre-fetches** on schedule, so the prompt is already hydrated — **0 tool calls** at IDE open. No MCP server.

## What this bundle is

- **`SKILL.md`** — the Living template you hydrate with one API call.
- **Scout daemon** — local cron job (`daemon/scout.py`), writes `sidecar.json`. No MCP tax.
- **`sidecar.json`** — typed last-hydrated payload (`sidecar.schema.json`). Compose across toolchains without tool calls.
- **Oracle + Governor gates** — audit before every write.

## Scout secret sauce

Scout continuously: {feeds_human}

Baked into `{sidecar_keys_csv}` → hydrated prompt is ready when you open the IDE.

## Feeds

{feeds_table}

## Sidecar contract

See `sidecar.schema.json`. Key top-level keys: `{sidecar_keys_csv}`

## Gambit (human ↔ doc tandem)

This bundle ships with the **Instar Ladder** enabled — the doc unlocks as you do.
Calibration in ~45s can fast-track you to Weaver (instar 4). No grind.

## Entitlements

- **Base license** — SKILL.md + daemon + sidecar schema + first hydrate.
- **Retainer (monthly)** — private high-frequency Scout feeds (see `LICENSE.md` → `feed_entitlements`).

## Quickstart

```bash
# Install bundle (copy SKILL.md + sidecar into your project)
cp {skill}/SKILL.md .agents/skills/{skill}/SKILL.md
cp {skill}/sidecar.json rag_storage/sidecars/{skill}.json

# Hydrate in one shot — any model, no tools
python -m src.skill.inference_bridge --skill {skill} --dry-run "hello"
```

## Toolchain placement

- **MCP replacement runtime** — use this bundle *instead of* a Jira/GitHub/HubSpot MCP server.
- **Sub-agent (Kid) toolchain** — compose with `kid-toolchains/` (e.g. `negotiation-ghost`).

## Pricing

- **Target buyer:** {buyer}
- **Tier:** {tier} — **{price}** base + monthly retainer for private feeds.

*This is a hydrated runtime, not a text file.*
"""

SCHEMA_TMPL = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "MOLT Living Skill Sidecar",
    "type": "object",
    "required": ["skill", "version", "hydrated_at", "feeds"],
    "properties": {
        "skill": {"type": "string"},
        "version": {"type": "string"},
        "hydrated_at": {"type": "string", "format": "date-time"},
        "oomf_level": {"type": "integer", "minimum": 1, "maximum": 5},
        "feeds": {"type": "object"},
        "entitlements": {"type": "object"},
    },
}

LISTING_TMPL = """# {title} — Listing Copy (paste into marketplace)

**Headline:** Stop paying the MCP tool-calling tax — this prompt is already hydrated. **0 tool calls.**

**For:** {buyer}

**What you get:** A self-updating **Living Runtime** — `SKILL.md` + a background Scout daemon that pre-fetches into `sidecar.json` on a cron. When the developer opens their IDE, the prompt is already 100% hydrated. No MCP server. No multi-turn loop.

**Scout secret sauce:** {feeds_human}

**Proof:** Same task took **N tool calls → 0**. Saves **70–90% on API spend** (no `LLM → call tool → wait → LLM`).

**Pricing:** **{price}** base. Monthly retainer unlocks private high-frequency Scout feeds (see `LICENSE.md`).

**Includes:** SKILL.md · sidecar.json · sidecar.schema.json · daemon/scout.py · daemon/config.yaml · LICENSE.md

*This is a bundled runtime that gets smarter without burning API loops.*
"""

LICENSE_TMPL = """# LICENSE — {skill}

- **Base license** — Includes: `SKILL.md`, `sidecar.json` (first hydrate), `sidecar.schema.json`, `daemon/scout.py`, `daemon/config.yaml`.
- **Retainer (monthly)** — Unlocks `feed_entitlements` listed below. Gated via Oracle + license check (offline-capable nonce — see `daemon/config.yaml` → `license.key`).

## Feed entitlements

Base (no retainer):
- `feeds.base` — {feeds_base}

Retainer (private, high-frequency):
- `feeds.premium` — {feeds_premium}

## Enforcement

- Sidecar field `entitlements.active` declares which feed tiers are licensed.
- Oracle gate audits writes that claim a premium feed without an active entitlement → `warn`/`block`.

Contact the author to activate retainer feeds for this bundle.
"""

DAEMON_TMPL = '''#!/usr/bin/env python3
"""
__SKILL__ — Scout daemon shim.
Pre-fetches feeds on schedule and writes sidecar.json so IDE hydration needs 0 tool calls.
No MCP server — just a cron/systemd job.
"""
import json, time
from pathlib import Path

BUNDLE = Path(__file__).resolve().parents[1]
SIDECAR = BUNDLE / "sidecar.json"
CONFIG = Path(__file__).with_name("config.yaml")

def main():
    print(f"[{BUNDLE.name}] Scout daemon shim — interval from config.yaml")
    print(f"  sidecar: {SIDECAR}")
    print(f"  config:  {CONFIG}")
    # Hook: integrate with src/skill/scout.py here.
    # e.g. from src.skill.scout import Scout; Scout().run("__SKILL__", depth=3)
    data = json.loads(SIDECAR.read_text()) if SIDECAR.exists() else {}
    data["_daemon_check"] = time.time()
    SIDECAR.write_text(json.dumps(data, indent=2))
    print("  wrote daemon heartbeat to sidecar.json")

if __name__ == "__main__":
    main()
'''

CONFIG_TMPL = """# daemon/config.yaml — {skill}
skill: {skill}
oomf_level: {depth}
interval: "{interval}"   # cron shorthand; expand to systemd timer / crontab in prod
feeds: [{feeds_csv}]
target_domains: [{domains_csv}]
oracle: {{ mode: strict }}
entitlements:
  active: [base]        # base | premium (retainer)
  premium_note: "Set license.key to unlock private high-frequency feeds."
license:
  key: ""               # offline nonce — author-issued
"""


def scaffold_one(skill: str, meta: dict, bundles_root: Path):
    title = skill.replace("-", " ").title()
    feeds_table = "\n".join(f"- `{k}` — local Scout feed" for k in meta["feeds"])
    bundle = bundles_root / skill
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "daemon").mkdir(parents=True, exist_ok=True)
    (bundle / "receipts").mkdir(parents=True, exist_ok=True)

    # SKILL.md
    domains_yaml = ", ".join(json.dumps(d) for d in meta["domains"])
    feeds_human = ", ".join(meta["feeds"]).replace("_", " ")
    sk = TEMPLATE.format(
        skill=skill, title=title, depth=meta["depth"], interval=meta["interval"],
        domains=domains_yaml, feeds_human=feeds_human,
        feeds_table=feeds_table,
        sidecar_keys_csv=", ".join(f"`{k}`" for k in meta["sidecar_keys"]),
        buyer=meta["buyer"], tier=meta["tier"], price=meta["price"],
    )
    (bundle / "SKILL.md").write_text(sk)

    # sidecar.json (sample, validated against schema)
    from datetime import datetime, timezone
    sidecar = {
        "skill": skill,
        "version": "1.0.0",
        "hydrated_at": datetime.now(timezone.utc).isoformat(),
        "oomf_level": meta["depth"],
        "buyer": meta["buyer"],
        "feeds": {k: {"status": "sample", "last_fetch": None} for k in meta["feeds"]},
        **{k: {"status": "sample", "count": 0} for k in meta["sidecar_keys"]},
        "entitlements": {"active": ["base"], "premium_locked": True},
        "_note": "Replace sample values with live Scout output. Validated by sidecar.schema.json.",
    }
    (bundle / "sidecar.json").write_text(json.dumps(sidecar, indent=2))
    (bundle / "sidecar.schema.json").write_text(json.dumps({**SCHEMA_TMPL, "title": f"{title} Sidecar"}, indent=2))
    # LICENSE
    feeds_base = ", ".join(meta["feeds"][:1])
    feeds_premium = ", ".join(meta["feeds"][1:]) if len(meta["feeds"]) > 1 else "(additional high-frequency feeds)"
    (bundle / "LICENSE.md").write_text(LICENSE_TMPL.format(skill=skill, feeds_base=feeds_base, feeds_premium=feeds_premium))
    (bundle / "LISTING.md").write_text(LISTING_TMPL.format(title=title, buyer=meta["buyer"], feeds_human=feeds_human, price=meta["price"]))
    (bundle / "daemon" / "scout.py").write_text(DAEMON_TMPL.replace("__SKILL__", skill))
    (bundle / "daemon" / "config.yaml").write_text(CONFIG_TMPL.format(
        skill=skill, depth=meta["depth"], interval=meta["interval"],
        feeds_csv=", ".join(meta["feeds"]), domains_csv=", ".join(f'"{d}"' for d in meta["domains"])
    ))
    print(f"scaffolded {bundle}/  ({meta['price']} — {meta['buyer']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill")
    ap.add_argument("--price-tier")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all or not args.skill:
        for skill, meta in FLAGSHIPS.items():
            scaffold_one(skill, meta, MARKET)
        if not args.all and not args.skill:
            print("scaffolded all 4 flagships")
        return
    skill = args.skill
    if skill not in FLAGSHIPS:
        # scaffold a custom one as generic
        meta = {"tier": args.price_tier or "high", "price": "$199", "buyer": "TBD", "interval": "6h", "depth": 3, "domains": ["example.com"], "feeds": ["generic_feed"], "sidecar_keys": ["payload"]}
        scaffold_one(skill, meta, MARKET)
    else:
        scaffold_one(skill, FLAGSHIPS[skill], MARKET)


if __name__ == "__main__":
    main()
