# 🌀 Ruberg — boardroom wishes → domino line (files tip files)

**Gemini pasted boxes and arrows (too much suit). This is files that tip files.**

No daemon. No overlap. One wedge, one file appears, next agent wakes because a file is *there*.

```
                  ┌─────────────────────────┐
                  │  BOARDROOM (wishes)     │
                  │  council --rounds 1     │
                  │  kill test + [E#]       │
                  └───────────┬─────────────┘
                              │ wedge
                              ▼
  1-spark/seed.md  (Muse: 2 sentences + zen vs BLEGH)  ──┐
     │ file appears                                        │
     ▼                                                     │
  2-spec/spec.md   (Gemini: sherpa+atlas, cites [E#])      │
     │                                                     │
     ▼                                                     │
  3-patch/patch.diff (Codex: humane graft, py_compile)     │
     │                                                     │
     ▼                                                     │
  4-theater/trigger.json (Vibe → lookingglass)  ───────────┘
     │
     ▼
  inbox/tip-*.md → MRD.tct + JANUS (receipt) → next wedge
```

**Monitor guards every handoff:** forbidden `rm -rf`/`shred`/`DROP`, must cite `[E#]` after spark, humane only (archive not delete).

```bash
ruberg --seed 42 --concept ~/p_recovery          # boardroom picks wedge for that concept
ruberg --glob atlas --seed 42                    # alias: atlas / screenshots / jerry / tools
ruberg --seed 42 --concept ~/tools --watch       # tip one + hint theater
ruberg --seed 42 --concept ~/tools --arena 16    # tip + also grow lookingglass arena 16→2
ruberg --status                                  # what's in each inbox
cat ~/tools/ruberg/2-spec/spec-42-tools.md       # the 15-min spec Gemini would write
xdg-open ~/tools/lookingglass/theater/theater.html  # Vibe's theater (flip ☯ metal → 🔥 BLEGH)
```

Roles (so no stepping on toes):
- **Muse (Spark)** — `1-spark/seed.md` only. Creative, no code.
- **Gemini (Heavy Architect)** — `2-spec/spec.md` only. Runs `sherpa` + `atlas --seed`, writes 10-line diff + gate, cites [E#].
- **Codex (Boss Coder)** — `3-patch/patch.diff` only. Executes spec, `py_compile` or revert, humane graft.
- **Vibe (Observer)** — `4-theater/trigger.json` → pokes `theater.json` for lookingglass.

Where it lives:
```
tools/ruberg/
  1-spark/seed-42-*.md
  2-spec/spec-42-*.md
  3-patch/patch-42-*.diff
  4-theater/trigger-42-*.json
  inbox/tip-42-*.md   ← one-file handoff (read me first)
  ruberg.py (ENTRYPOINT, 280L)
```

Stay in terminal, gh napping, private stays private, same seed = same tip.
