---
name: my-living-skill
version: 1.0.0
scout:
  depth: 3           # 1 (inert/generalized) to 5 (deep RAG + active web crawl)
  interval: "6h"
  target_domains: []
oracle:
  mode: strict       # strict | permissive | user_only
  verify_compliance: []   # e.g. [HIPAA, GDPR, PCI, SOX]
privileges:
  elevated: false    # must be explicitly elevated via --elevate or Governor
gambit:
  enabled: false     # true = human+doc tandem (Instar Ladder)
  memory_mint: false # true = mint run receipts to .grimoire/bus
---

# {{SKILL_NAME}} — Living Skill

> **MOLT** — Markdown Originated Living Triad. This file molts.
> Static instructions -> autonomous RAG runtime, gated by Oracle, guarded by Governor.

## Purpose
<!-- One sentence: what this skill does when hydrated -->
Describe the core job here.

## When to Use
Trigger: user says `{{trigger phrases}}` or invokes `skill("my-living-skill")`.

## OOMF Levels (Scout Depth)
| OOMF | Behavior |
|------|----------|
| 1 | Inert shortcut — no fetch, just this markdown |
| 2 | Shallow — 1-2 whitelisted docs |
| 3 | Standard — full `target_domains` + RAG bake (default) |
| 4 | Deep — standard + 1-hop link expansion |
| 5 | Crawl — deep + active web search |

## Execution Runbook

### 1. Hydrate (no tools needed)
```python
from src.skill.skill_manager import SkillManager
mgr = SkillManager()
chunk = mgr.hydrate("my-living-skill", oomf_level=3)
# chunk is ready to prepend to any API call — one shot, no tool loop
```

### 2. One-Shot Inference (any model)
```python
from src.skill.inference_bridge import molt_one_shot
text = molt_one_shot("my-living-skill", user_query, oomf_level=3, dry_run=False)
```

### 3. Scout Refresh (requires --elevate network)
```bash
python -m src.skill.scout --skill my-living-skill --depth 3
# or via manager:
# scout = Scout(governor=gov); scout.run("my-living-skill", depth=3)
```

### 4. Oracle Gate (always)
```python
from src.skill.oracle import Oracle
oracle = Oracle(mode="strict", verify_compliance=["HIPAA"])
verdict = oracle.audit(mutation, skill_frontmatter)
# verdict.verdict in ("pass","warn","block")
```

### 5. Governor Gate (write/exec require user)
```bash
scout sweep --oomf 5 --elevate network,write   # session-scoped, TTY confirms
# or programmatic:
# gov.request_elevation({"write","network"}, reason="scout bake", auto_confirm=True)
```

## Domain Scaling Examples
This same file scales from inert shortcut to full runtime:

- **Pop-up medical triage** — `depth: 4`, `verify_compliance: [HIPAA]`, target_domains=[cdc.gov, who.int]
- **Disaster relief unit** — `depth: 5`, target_domains=[fema.gov, redcross.org]
- **Vision/dental clinic** — `depth: 3`, verify_compliance=[HIPAA, PCI]
- **Emergency services** — `depth: 4`, oracle strict, Governor user_only for exec
- **School sports broadcast** — `depth: 2`, no compliance, shallow docs

No MCP server. No extension. CLI flags are additive: `--oomf`, `--elevate`.

## RAG Sidecars
Scout writes to `rag_storage/sidecars/<skill>.jsonl` + `rag_storage/<skill>_<hash>.md`.
SkillManager hydrates freshest snippets on every `hydrate()` — auto-update hook:

```
<!-- scout: depth 3 baked 8 RAG docs — hydrate on next load -->
```

## Safety
- Oracle **always** runs before mutation — isolated, no network, no writes.
- Governor **always** gates `write`/`exec`/`network` — session-scoped, audit logged to `rag_storage/governor_audit.jsonl`.
- Hazard-guardian style safety locks cannot be overridden by Scout or Oracle auto-approval.

## Instar Ladder — Gambit (human ↔ doc tandem)
When `gambit.enabled: true`, the doc molts *with* you. Novices are scaffolded;
proficient humans fast-track. Doc's OOMF auto-caps to your instar.

| Instar | Name | You can… | OOMF cap | Reveal |
|--------|------|----------|----------|--------|
| 1 | Hatchling | name the Triad | 1 | vocab + map |
| 2 | Crawler | run a guided demo | 2 | copy-paste runbook |
| 3 | Forager | ship solo | 3 | RAG bake |
| 4 | Weaver | bend it, swap domains | 4 | edge cases, morph |
| 5 | Molt | teach others | 5 | author new skills |

Gate doc sections by instar:
```html
<!-- instar:3 -->Advanced RAG bake runbook (hidden until Forager)<!-- /instar -->
```

Python:
```python
from src.skill.gambit import InstarEngine
from src.skill.skill_manager import SkillManager
g = InstarEngine(user_id="bubba")
g.calibrate("my-living-skill")          # 60s placement — may place you at 3/4
chunk = SkillManager().hydrate("my-living-skill", user_id="bubba", gambit=g)
# chunk is gated to your instar
```

Challenge loop (white-box, no grind):
```bash
molt challenge my-living-skill          # pull next challenge at your instar
molt submit my-living-skill "answer"    # keyword-scored; streak promotes
molt progress my-living-skill           # instar, XP, OOMF cap, streak
```

Fast-track: ace calibration in <45s → start at Weaver (instar 4). 3× perfect streak doubles molts.

## Force Multipliers (registered, removable)
Tiny composable hooks on the hydration/lifecycle path — no spec change.

| FM | Stage | What it does | Auto? |
|----|-------|--------------|-------|
| hydrate_cache | pre_hydrate | skip RAG assembly if sidecars unchanged | yes |
| auto_distill | post_hydrate | compress chunk to budget (head > tail) | yes |
| preflight_gate | pre_inject | Oracle audits RAG before model sees it | yes |
| memory_mint | post_hydrate | receipt → .grimoire/bus + Anchor | opt-in |
| morph_suggest | pre_hydrate | preset hint (triage→medical_triage) | yes |
| retention_nudge | on_progress | schedule spaced recall (24h/48h) | yes |

Toggle: `from src.skill.force_multipliers import toggle; toggle("hydrate_cache", False)`

More stubs: orphan_detector, cost_guard, post_oracle_tune (opt-in).

## CLI Compatibility (zero-bloat)
These flags are additive and ignored if absent — existing tools see no change:

| Flag | Effect |
|------|--------|
| `--oomf 1..5` | Sets Scout depth for this call (still capped by your instar) |
| `--elevate [scopes]` | Elevates (read/write/network/exec), TTY confirms |
| `--elevate-ttl 3600` | Session TTL |

Compatible: Vibe CLI, Codebuff, Gemini CLI, VS Code (via `src/skill/inference_bridge.py`).

## References
- Spec: `src/skill/skill_manager.py` (frontmatter parse + hydrate + gambit gate)
- Scout: `src/skill/scout.py`
- Oracle: `src/skill/oracle.py`
- Governor: `src/skill/governor.py`
- Bridge: `src/skill/inference_bridge.py`
- Gambit: `src/skill/gambit.py` (InstarEngine — calibrate/challenge/submit/progress)
- FMs: `src/skill/force_multipliers.py` (6 + stubs)
- Docs: `docs/GAMBIT.md`, `docs/FORCE_MULTIPLIERS.md`
