# GAMBIT — Instar Ladder (Human ↔ Doc Tandem)

> The doc molts **with** you. You don't read it — you molt through it.

MOLT without the human advancing = the doc outruns the user.
The Gambit fixes that with a 5-stage **Instar Ladder** inspired by insect molting:
each stage unlocks only when you demonstrate **comprehension + retention**.

---

## Instars at a Glance

| Instar | Name | What you can do | OOMF cap | Unlocks | Next |
|------|------|----------------|----------|---------|------|
| 1 | **Hatchling** | name the Triad | 1 | vocab quiz, Triad map | 30 XP + 2-streak |
| 2 | **Crawler** | run a guided demo | 2 | copy-paste runbook | 40 XP + 2-streak |
| 3 | **Forager** | ship solo | 3 | RAG bake | 50 XP + 2-streak |
| 4 | **Weaver** | bend it, swap domains | 4 | edge cases, morph, `--elevate write` | 60 XP + 2-streak |
| 5 | **Molt** | teach others | 5 | author skills, `--elevate exec`, spawn swarm | — |

Storage: `rag_storage/instars/<user>__<skill>.json` — portable, offline, survives reboot.

**Fast-track:** Ace calibration in <45s → start at Weaver (instar 4).
3× perfect streak with <20s answers → double molt.

---

## Calibration (Placement)

Don't start at 1 if you don't need to.

```python
from src.skill.gambit import InstarEngine
g = InstarEngine(user_id="bubba")
q = g.calibrate("med-triage-copilot")          # returns 5-question quiz
result = g.calibrate_submit("med-triage-copilot",
                            answers=["scout does RAG...", "oracle gates...", ...],
                            elapsed_ms=28000)
# result: {"instar": 4, "pct": 0.92, "auto_oomf": 4, ...}
```

Thresholds: 0–30%→1, 30–60%→2, 60–85%→3, 85–100% <45s → 4, 100% <30s → 4+bonus XP.

---

## Challenge Loop

```python
c = g.challenge("med-triage-copilot")
# {"instar": 3, "challenge": {"q": "...", "points": 20}, "scaffold": "..."}

r = g.submit("med-triage-copilot", answer="my answer here", elapsed_ms=12000)
# {"passed": True, "points": 20, "new_instar": 4, "leveled": True, "auto_oomf": 4}
```

Scoring: keyword heuristic (≥50% keyword hit = pass), speed bonus <15s on perfect.

---

## Auto-OOMF

Doc depth is always `min(frontmatter_depth, gambit_cap)`. So even if a skill says
`scout.depth: 5`, a Hatchling still hydrates at 1. No dust left in the dust.

```python
from src.skill.skill_manager import SkillManager
mgr = SkillManager()
# gambit-aware hydrate:
chunk = mgr.hydrate("med-triage-copilot", user_id="bubba", gambit=g)
# or pass gambit object directly:
chunk = mgr.hydrate("med-triage-copilot", gambit=g)
```

CLI equivalent (future): `molt hydrate med-triage-copilot --user bubba`

---

## Doc Gating

Hide advanced sections behind instar markers — revealed only when ready:

```markdown
<!-- instar:3 -->
## Deep RAG Bake Runbook
...advanced material...
<!-- /instar -->
```

Below your instar, you see a teaser: `🔒 Instar 3 locked — … Complete a challenge to molt → molt challenge <skill>`

Implemented in `InstarEngine.gate_hydration()` — called automatically from `SkillManager.hydrate()` when gambit is active.

---

## Progress & Spaced Retention

```python
g.progress("med-triage-copilot")
# {"instar": 3, "instar_name": "Forager", "xp": 20, "xp_to_next": 50, "auto_oomf": 3, "streak": 1, ...}
```

Every `submit()` sets `next_due_at` → 24h (48h if streak ≥3). The `retention_nudge` force multiplier
writes due dates to `rag_storage/instars/_nudges.json` — a cron or startup hook can surface them.

---

## Frontmatter

```yaml
gambit:
  enabled: true        # opt-in per skill (default: false — no behavior change)
  memory_mint: false   # mint run receipts to .grimoire/bus when hydrating
```

Global/context-scoped toggles live in `src/audience/context.py`:

```python
from src.audience.context import AudienceContext
ctx = AudienceContext.from_cli(user_id="bubba")  # parses --oomf/--elevate
mgr = SkillManager()
mgr.audience_context = ctx  # if wired
```

---

## Why "Gambit"?

A gambit is an opening sacrifice that earns position. Here, the doc sacrifices immediacy
(hiding its sharpest sections) to earn *your* competence — so when you finally see them,
you can wield them.

## See Also

- `src/skill/gambit.py` — engine implementation
- `src/skill/force_multipliers.py` — `retention_nudge` FM
- `templates/SKILL.template.md` — instar markers + gambit frontmatter
- `docs/FORCE_MULTIPLIERS.md` — all FMs

