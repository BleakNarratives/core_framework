# CAPS Stego Hygiene Guide — Private Perfect, Public Poison

# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: provenance
# DEPS: none
# ROLE: Why CAPS case-stego is a private cloak, not public hygiene — the boundary that keeps it valuable
# AUTHOR: Buffy (Codebuff) + BleakNarratives (operator insight)
# SESSION: 2026-09-08
# TIER: 2
# FKA: — (companion to HOP_PROTOCOL.md Appendix A + tools/provenance/caps_stego.py + Visor ghost)
# [/DNA_TAG]

> **CAPS_matter_To_tHe_VIEW** — the VIEW's case is the payload: `upper=1 lower=0`, 1 bit per A-Za-z.
> This guide is the boundary. Break it and the trick eats itself.

---

## TL;DR

- **Private (during hops): Perfect.** Ghosted wormholes let you move `agents→agents / models→models / tools→tools / cubs→subs` one pillar at a time without screaming `IMPORT ME` at every scanner, and without `codemap.py` graphing a lie.
- **Public (as shipped API/template): Poison.** If you publish "hide your moves in caps," you train every repo to hide its mess, reward disorg'd structure, and make `tools/*.py` worthless because the graph/flow/feel all disappear into prose.

**Keep it private and it stays magic. Ship it and it's entropy.**

---

## Why it shines *during* consolidation

You have `~` with 208 loosies, `UNPACKED` at 9.7G / 83 items, `w` recovering from emptiness, `RootBase` at 78 items, `Zip/` at 1.4G — the move window is inherently messy. CAPS stego helps because:

1. **Graph honesty.** `codemap.py` parses `import X` edges. A plain shim `from tools.provenance.dna_tag import *` draws a real edge that says "this ghost IS the source." A stego shim is `"""archival prose..."""` + tiny decoder — graph sees docstring, not edge. Truth stays in `tools/provenance/dna_tag.py`.
2. **Signal quiet.** `grep -r "dna_tag"` doesn't catch `tHiS fIlE wAs ReLoCaTeD...`. Low-tier scanners / linters / newcomers don't mirror the forward. Only Architect-class viewers (Visor) or `caps_stego.py decode` see it.
3. **Maiden-name intact.** The canonical file keeps `FKA: ~/dna_tag.py` in `DNA_TAG`. The wormhole keeps the prose. History survives without import pollution.
4. **Decay is honest.** `pheromones.jsonl` `TASK_CLAIM` with `decay_rate` still governs lifetime. `active_by_type("TASK_CLAIM")` → zero hits for 14d → delete shim. `STANK.md`/`WHO_DID_WHAT.md` regenerate as views — no manual tombstones.

This is **Hop step 4 (STEGO WORMHOLE)** — archival docstring + Caps bits + `DeprecationWarning` + `runpy` forward. Same half-life, same `prove before next hop` rule.

---

## Why shipped public stego is worthless

| Public sign | Decay |
|-------------|-------|
| Every shim hidden in caps | Codebase looks "clean" (`ls` shows no forward) but `import` still 404s until you decode. Newcomers learn to hide, not to home. |
| Graph shows no edges for hidden moves | `codemap` reports 0 orphans *because* you hid them — not because structure is clean. Metrics lie. |
| Hygiene taught as "stealth" | Reward signal flips: mess → hide → praise. Disorg'd `feel/flow` becomes aesthetic. Re-org never finishes. |
| Scanners bypass caps by default | Public trick = arms race. Every tool adds `caps_stego decode` and the cloak is worthless overhead. |

> **Operator's call, 2026-09-08:** "If it becomes a public-use thing it'll be kinda inherently worthless and lead to poor code hygiene and a disorg'd appearance/flow/feel... Perfect for me then! Lol"
>
> Exactly. Private spice. Public poison. That's the firewall.

---

## The boundary (non-negotiable)

1. **Never template it for public repos.** Don't put a "CAPS wormhole starter" in `CONTRIBUTING.md` / public docs / scaffold scripts.
2. **Every ghost decays-or-dies.** `decays YYYY-MM-DD` in the shim header + pheromone `decay_rate` + ledger entry. No immortal ghosts.
3. **Visor ghosts, caps carries.** `class >=3 (Specialist/Worker/Recruit)` → `GHOST` → sees `*moved — see vault/HOP_PROTOCOL Appendix A*`. `class <=2 (Operator/Overseer/Architect)` → `SHOW` + decoded path. Rules live in `.SLaSHdotHIDEfiles/masks/stego.json`.
4. **Log or it didn't move.** `pheromones.jsonl` `CARD_EMIT {stego:true, view:GHOST/SHOW}` + `WHO_DID_WHAT.md` line + `EVIDENCE_SPINE.md` ownership.
5. **Prove the veil.** Before next hop:
   ```bash
   caps_stego.py check ~/dna_tag.py --expect tools/provenance/dna_tag.py
   python3 -m py_compile ~/dna_tag.py && python3 -m py_compile tools/provenance/dna_tag.py
   python3 ~/dna_tag.py --help          # exec forward
   python3 -W default -c "import dna_tag; print(dna_tag.__file__)"  # import forward
   visor.py may --file ~/dna_tag.py --entity recruit_01 --action read  # GHOST
   visor.py may --file ~/dna_tag.py --entity architect   --action read  # SHOW
   ```

---

## When to use — checklist

- ✅ Loosies triage (`~/` 208 files → `tools/{provenance,introspection,inference}` / `projects/<pillar>/`)
- ✅ `w` / `UNPACKED` / `RootBase` consolidation while graph is noisy — one pillar per hop
- ✅ Any 1-pillar move where you need imports to stay green but graph to stay honest
- ❌ Public examples, onboarding docs, long-lived shims, or as excuse to skip `CODEMOD (step 5)`
- ❌ Hiding a move that should just be `git mv` + import fix — fix beats hide every time the hop window is closed

---

## Files

- `HOP_PROTOCOL.md` — 7-step hop (step 4 = stego wormhole)
- `HOP_PROTOCOL.md Appendix A` — `CAPS_matter_To_tHe_VIEW` full spec
- `tools/provenance/caps_stego.py` — `encode|decode|check|visor-view` (stdlib, no deps)
- `.SLaSHdotHIDEfiles/masks/stego.json` — GHOST for `class>=3`, SHOW for `class<=2`
- `.SLaSHdotHIDEfiles/visor.py` — is the VIEW; caps is the PAYLOAD — don't mix them

*"If you can read this, you're Architect. If it says 'ghosted' — raise your class."*
