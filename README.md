# MOLT — Markdown Originated Living Triad

> **Static markdown molts into living runtime.**  
>
> **Workspace navigation:** start with [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) before browsing the surrounding Molt, Whorl, and Vertical AI workspaces.

> Inert `SKILL.md` → autonomous, RAG-enabled execution runtime. No MCP server. No extension. One API call.

<!-- METRICS:START -->
[![Tests](https://img.shields.io/badge/tests-236%20passing-brightgreen)](#tests)
<!-- METRICS:END -->
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#install)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)

MOLT replaces static `SKILL.md` specs and legacy MCP servers with **Living Markdown**: a triad-powered,
self-evolving skill framework that scales from a prompt shortcut (OOMF 1) to a full domain runtime
(OOMF 5) without breaking existing CLI tools (Vibe, Codebuff, Gemini CLI, VS Code).

---

## One-liner

```python
from src.skill.inference_bridge import molt_one_shot
text = molt_one_shot("med-triage-copilot", "triage: 34F, SOB, vitals...", oomf_level=3, dry_run=True)
# then toss the hydrated prompt at ANY model in ONE call — no tools, no schema, no MCP
```

---

## The Triad

| Engine | Role | What it does |
|--------|------|--------------|
| **Scout** | senses | Web query, doc scrape, RAG bake into `rag_storage/sidecars/`. Depth `1→5` (`OOMF_LEVEL`). |
| **Oracle** | judges | Isolated audit for deadlocks, exploits, privilege drift, HIPAA/GDPR — before any write. |
| **Governor** | guards | Session-scoped `--elevate` (read/write/network/exec), TTY confirms, audit log. |

Hydrate happens **before** the API call — that's how we nix tool-call loops.

---

## 30-Second Demo

```bash
# List living skills, doctor the install, hydrate without hitting the network
python -m src.skill.inference_bridge --list-skills
python -m src.skill.inference_bridge --skill my-living-skill --oomf 3 --dry-run "hello" | head

# Scout at depth 3 (needs --elevate network)
from src.skill.scout import Scout
from src.skill.governor import Governor
gov = Governor(); gov.request_elevation({"network"}, reason="demo", require_confirmation=False, auto_confirm=True)
Scout(governor=gov).run("my-living-skill", depth=3, target_domains=["https://example.com"])

# Oracle gate
from src.skill.oracle import Oracle
Oracle(mode="strict", verify_compliance=["HIPAA"]).audit(mutation, frontmatter)

# Gambit — human molts WITH the doc
from src.skill.gambit import InstarEngine
g = InstarEngine(user_id="bubba")
g.calibrate("med-triage-copilot")                # placement quiz → may start you at Weaver
g.challenge("med-triage-copilot")                # next task at your instar
g.submit("med-triage-copilot", answer="...", elapsed_ms=12000)  # keyword-scored; streak promotes
print(g.progress("med-triage-copilot"))          # instar, auto_oomf, xp, unlocks
```

---

## Living Frontmatter

Every `SKILL.md` carries a YAML header that drives runtime:

```yaml
---
name: med-triage-copilot
version: 1.0.0
scout:
  depth: 4
  interval: "6h"
  target_domains: [https://www.cdc.gov, https://www.who.int]
oracle:
  mode: strict
  verify_compliance: [HIPAA]
privileges:
  elevated: false
gambit:
  enabled: true        # human↔doc tandem ladder
  memory_mint: false
---
```

New skills from template:

```python
from src.creation.engine import CreationEngine
CreationEngine().create_living_skill("disaster-relief-unit",
    scout_depth=5, target_domains=["https://www.fema.gov"],
    oracle_mode="strict", output_path=".agents/skills/disaster-relief-unit/SKILL.md")
# also: templates/SKILL.template.md
```

---

## Instar Ladder — Gambit

The doc molts **with** you. 5 stages, fast-track for the proficient, scaffolded for novices:

| Instar | Name | You can… | OOMF cap | Unlocks |
|--------|------|-----------|----------|---------|
| 1 | Hatchling | name the Triad | 1 | vocab quiz |
| 2 | Crawler | run a guided demo | 2 | copy-paste runbook |
| 3 | Forager | ship solo | 3 | RAG bake |
| 4 | Weaver | bend it, swap domains | 4 | edge cases, morph, `--elevate write` |
| 5 | Molt | teach others | 5 | author skills, `--elevate exec` |

Gate advanced runbook sections by instar:

```markdown
<!-- instar:3 -->
## Deep RAG Bake (hidden until Forager)
<!-- /instar -->
```

Hydrate respects your cap:

```python
from src.skill.skill_manager import SkillManager
from src.skill.gambit import InstarEngine
g = InstarEngine(user_id="bubba")
chunk = SkillManager().hydrate("my-living-skill", gambit=g)  # auto-OOMF, gated reveal
```

Docs: [`docs/GAMBIT.md`](docs/GAMBIT.md)

---

## Force Multipliers

Tiny, composable hooks on the hydration path — no spec change, removable, zero-bloat:

| FM | Stage | Effect | Auto |
|----|-------|--------|------|
| `hydrate_cache` | pre_hydrate | skip RAG reassembly if sidecar hash unchanged | yes |
| `auto_distill` | post_hydrate | compress chunk to budget, head > tail | yes |
| `preflight_gate` | pre_inject | Oracle audits RAG before the model sees it (redacts on block) | yes |
| `memory_mint` | post_hydrate | receipt → `.grimoire/bus` + `~/.molt_receipts.jsonl` | opt-in |
| `morph_suggest` | pre_hydrate | preset hint (triage→medical_triage) | yes |
| `retention_nudge` | on_progress | writes `rag_storage/instars/_nudges.json` for spaced recall | yes |

```python
from src.skill.force_multipliers import toggle, FM_REGISTRY
toggle("hydrate_cache", False)  # disable one — hydrate still works
```

Docs: [`docs/FORCE_MULTIPLIERS.md`](docs/FORCE_MULTIPLIERS.md)

---

## Domain Presets (scales without breaking CLI)

One `SKILL.md` morphs into a specialized runtime:

```python
from src.repurposing.engine import RepurposingEngine
RepurposingEngine().morph_skill("triage-base", "medical_triage")     # HIPAA strict, CDC/WHO
RepurposingEngine().morph_skill("triage-base", "sports_broadcast")   # permissive, shallow
# medical_triage | disaster_relief | vision_clinic | dental_clinic
# emergency_services | sports_broadcast | legal_financial
```

---

## Install

```bash
pip install pyyaml requests   # only runtime deps (both optional — degrades without)
python3 -m src.skill.inference_bridge --list-skills
python3 -m unittest discover -s tests -v   # repository test suite
```

## Zero-Bloat CLI Contract

These flags are **additive**. Unknown flags are ignored — existing tools see no change unless you opt in:

- `--oomf 1..5` — sets Scout depth for the call (still capped by your Instar)
- `--elevate [scopes]` — `read|write|network|exec` (no arg = all), TTY confirms, 1h TTL
- `--elevate-ttl 3600` — custom TTL

Works: Vibe CLI, Codebuff, Gemini CLI, VS Code — all via `src/skill/inference_bridge.py`.

## Workspace verification

The surrounding Vertical AI workspaces have dependency manifests and a safe,
network-free verifier. It parses Python syntax and local imports, and runs only
the deterministic `vertical_local` debate smoke test; it does not read secrets,
contact providers, start servers, or invoke live LLMs:

```bash
python scripts/verify_vertical_ai.py
```

Project manifests:

- [`vertical_ai/manifest.json`](vertical_ai/manifest.json) — outreach prototype
- [`vertical_local/manifest.json`](vertical_local/manifest.json) — local wrapper
- [`vertical_radar/manifest.json`](vertical_radar/manifest.json) — radar prototype
- [`vertical_ai_engine/manifest.json`](vertical_ai_engine/manifest.json) — Coach Bleak legacy engine

The full relationship map and migration gates live in
[`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) and
[`docs/VERTICAL_AI_MIGRATION.md`](docs/VERTICAL_AI_MIGRATION.md).

---

## Architecture

```
src/skill/
  skill_manager.py       # lifecycle: list / parse / hydrate / scan_active / apply_mutation
  scout.py               # depth 1..5 fetcher + RAG baker + sidecar writer
  oracle.py              # isolated audit: injection / drift / deadlock / compliance / bloat
  governor.py            # --oomf / --elevate parsing, sessions, TUI, audit log
  gambit.py              # InstarEngine — calibrate / challenge / submit / auto_oomf / gate
  force_multipliers.py   # FM_REGISTRY — 6 FMs + 3 stubs, toggleable
  inference_bridge.py    # molt_one_shot / molt_hydrate — one-shot, no tool loop
  audience/context.py    # AudienceContext — session-scoped CLI flag context
templates/
  SKILL.template.md      # Living Markdown template with gambit + FM docs
docs/
  GAMBIT.md
  FORCE_MULTIPLIERS.md
tests/
  test_molt_triad.py     # 48 tests — Triad pipeline
  test_molt_redteam.py   # 18 tests — exploits, leaks, privilege drift, preflight
```

See also: [`projects/MOLT/NAMING.md`](projects/MOLT/NAMING.md) — naming rationale.

---

## Security

Red-teamed in [`tests/test_molt_redteam.py`](tests/test_molt_redteam.py): prompt injection via
fetched docs, code exec escalation without `--elevate`, secret leakage, XSS payloads,
gated content leak, private-net fetch, oversized mutation bloat, compliance flagging,
and `preflight_gate` RAG redaction. `user_only` Oracle still blocks `critical`.

---

## Marketplace — Living Skill bundles (the bag)

> **Stop paying the MCP tool-calling tax — this prompt is already hydrated. 0 tool calls. Saves 70–90% on API spend.**

Every marketplace unit is a **self-updating runtime**, not a text file: `SKILL.md + Scout daemon + typed sidecar.json + schema`. The daemon pre-fetches on a local cron so the prompt is already hydrated when the IDE opens — no MCP server, no tool loop.

```bash
python tools/marketplace/scaffold_bundle.py --all    # scaffold bundles
python tools/marketplace/validate_bundle.py --all    # 16 PASS
```

| Bundle | Category | For | Price |
|---|---|---|---|
| `saas-churn-oracle` | High-Ticket B2B | B2B founders & Sales Ops | **$199–$499** |
| `adversary-emulator` | Cybersecurity | SecOps & Lead Devs | **$299–$599** |
| `bureaucracy-judo` | Legal / Compliance | LegalTech & Agencies | **$149–$349** |
| `talent-singularity-scout` | HR / Executive | VC & Recruiters | **$249 + bounty** |
| `mcp-replacement` | **MCP Replacement** | Dev + Product Ops (Jira/GitHub/HubSpot) | **$199–$399** |
| `negotiation-ghost` | **Kid: Whisperer** | Founders / Sales / M&A | **$149–$349** |
| `dopamine-architect-in-reverse` | **Kid: Attention OS** | Families & Deep-work | **$79–$199** |
| `provenance-oracle` | Media (Sora/Flux/Veo) | Media production | **$199–$449** |
| `scout-foreman` | Utility | Every buyer — herds all Scouts | **$49** *(free w/ 2+)* |
| `whorl-bus-dispatcher` | **Hive: Bus** | Distributed teams | **$299–$549** |
| `loom-thread-weaver` | **Hive: Loom** | Ops / AI engineers | **$249–$449** |
| `git-state-snapshotter` | **Hive: State** | SRE & Security | **$199–$399** |
| `arena-logic-gladiator` | **Hive: Arena** | ML/R&D teams | **$199–$399** |
| `molt-instar-autoloop` | **Sovereign: Autoloop** | AI Lab Leads & Sovereign Founders | **$349–$699** |
| `akasha-mutation-vault` | **Sovereign: Vault** | SRE & Security (audit) | **$299–$549** |
| `merkaba-claw-bridge` | **Sovereign: Bridge** | Platform & Infra (Merkaba+Claw) | **$299–$599** |

**MCP Replacement** — pitch: *"Convert Jira/GitHub/HubSpot MCP servers into one MOLT package. Scout runs as a local cron job, pre-fetching schemas/tickets/commits into `sidecar.json` — 0 tool calls at IDE open."* See `projects/MOLT/marketplace/MCP_REPLACEMENT.md`.

**Kid Toolchains** — Scout + Oracle sub-agents that compose by reading each other's `sidecar.json` without calling tools (typed `sidecar.schema.json`). See `projects/MOLT/marketplace/KID_TOOLCHAINS.md`.

**Subscription (retainer):** Base = `SKILL.md + daemon + schema + first hydrate`. Retainer (monthly) = private high-frequency Scout feeds — gated via `entitlements.active + license.key + Oracle gate` (offline-capable). See `projects/MOLT/marketplace/PITCH_AND_PRICING.md` and each bundle's `LICENSE.md`.

Full bundle index: `projects/MOLT/marketplace/README.md` · Hive mind: `projects/MOLT/marketplace/HIVE_MIND.md` — **wire whorl-bus-dispatcher first** · Sovereign loop: `projects/MOLT/marketplace/SOVEREIGN_LOOP.md` — **Implor→Thoth first, then Merkaba→Claw** · Bundle contract: `projects/MOLT/marketplace/BUNDLE_SPEC.md`

---

## License

MIT

---

*Built with — not in — the dust storm. Bug? You'll find it buried where the signal thins. —M*
