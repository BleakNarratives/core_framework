# Force Multipliers — MOLT

Tiny, composable, removable hooks that multiply the human×doc tandem.
They don't change the MOLT spec — they make the existing path faster, safer, more retentive.

> **Scope, so this file doesn't overpromise.** Every entry here optimizes the
> **hydrate path** — caching, chunk truncation, an Oracle preflight gate, receipts,
> retention manifests. **None of them touch a buyer, a price, or a channel.**
> There is no revenue multiplier in this registry, and adding an eleventh local
> optimization will not move any money. The "human×doc tandem" in the line above
> means one operator reading one document faster — not a market.
>
> This is a deliberate note, not a disclaimer: the registry is genuinely useful
> and genuinely complete *for what it is*. It was written down because the file's
> framing invited the wrong expectation, and "where is the missing force
> multiplier?" is a question that recurred without an answer in the repo.

- **Where they fire:** `pre_hydrate` → `post_hydrate` → `pre_inject` (Oracle on RAG) → `on_progress`
- **Registry:** `src/skill/force_multipliers.py` → `FM_REGISTRY`
- **All are additive.** Disable any with `toggle("hydrate_cache", False)`.

---

## The Six

| # | Name | Stage | What it does | Auto | Perf |
|---|------|-------|--------------|------|------|
| 1 | `hydrate_cache` | `pre_hydrate` | Skip RAG assembly if sidecar hash unchanged | yes | 10–50ms saved per warm hydrate |
| — | `hydrate_cache_store` | `post_hydrate` | Store result for next cache hit | yes | — |
| 2 | `auto_distill` | `post_hydrate` | Compress chunk to budget (head > tail), truncate middle | yes | keeps context window clean |
| 3 | `preflight_gate` | `pre_inject` | Oracle audit on RAG snippets **before** model sees them; redacts RAG on block | yes | fail-closed on injection |
| 4 | `memory_mint` | `post_hydrate` | Receipt → `.grimoire/bus` + `~/.molt_receipts.jsonl` | opt-in* | doc remembers how you ran it |
| 5 | `morph_suggest` | `pre_hydrate` | Heuristic: skill name/body → suggested `domain_preset` (triage→medical_triage) | yes | surfaces repurposing |
| 6 | `retention_nudge` | `on_progress` | Write `rag_storage/instars/_nudges.json` with next due dates | yes | powers spaced recall |

\* `memory_mint` is opt-in via frontmatter `gambit.memory_mint: true` or `ctx._mint_memory = True`.

---

## Usage

```python
from src.skill.force_multipliers import list_multipliers, toggle, run_stage, FM_REGISTRY

# enumerate
for fm in list_multipliers():
    print(fm.name, fm.stage, fm.enabled)

# disable one temporarily
toggle("hydrate_cache", False)

# run a stage manually (SkillManager already does this inside hydrate)
ctx = {"skill": "med-triage-copilot", "oomf_level": 3, "max_chars": 6000, "hydrated": chunk}
ctx = run_stage("post_hydrate", ctx)
```

Inside `SkillManager.hydrate()` the pipeline is:

```
FM: pre_hydrate  →  body + sidecar assembly  →  FM: post_hydrate  →  FM: pre_inject  →  gambit banner
```

---

## Adding a New One

```python
from src.skill.force_multipliers import register

@register("cost_guard", stage="pre_scout",
          description="Estimate fetch cost at depth, block if over budget.", auto=False)
def fm_cost_guard(ctx):
    depth = ctx.get("depth", 3)
    if depth > 4 and not ctx.get("elevated"):
        return {"blocked": True, "_fm_errors": ["cost_guard: depth 5 requires --elevate"]}
    return None
```

Then flip it on: `toggle("cost_guard", True)` or `from src.skill.force_multipliers import FM_REGISTRY; FM_REGISTRY["cost_guard"].enabled = True`.

---

## Stubs (wired, disabled by default)

| Name | Intended |
|------|----------|
| `orphan_detector` | Flag sidecars with no parent SKILL.md |
| `cost_guard` | Budget-gate deep Scout fetches |
| `post_oracle_tune` | Tune Oracle thresholds from verdict history |

Wire whatever scouts you already have — same `register()` decorator, same toggle.

---

## Frontmatter Hooks

```yaml
gambit:
  enabled: true        # enables gambit-gated hydration + banner
  memory_mint: true    # enables memory_mint FM for this skill
```

`memory_mint` is the only FM that reads frontmatter; the rest are global toggles.

---

## Guarantee

Force multipliers never change `skill_manager.hydrate()`'s contract. They only
transform `ctx` dicts between stages. Remove the entire `force_multipliers.py`
file and hydrate still works — just without the speed/safety/retention bonuses.

