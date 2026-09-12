# Pooper — Mikey-portion digester

**One `X` → one `Sherpa`, one 15-min paste at a time.**

You have a huge `X` (kingdom: 2853 py files, 1021 screenshots, fartographer, bardildo, history, sherpa, council, guard_judo, humane cannibal) and a phone app (Claude app / Gemini app). You want `X → Sherpa` without reading 92G or holding it all in your head.

`pooper` poops **globs** — digestible, paste-ready prompts.

- **One glob = 15 min max.** One paste into the phone app, walks you step-by-step through ONE thing, then stops.
- **One a day is winning.** Take a 2nd if you want more — `pooper --again` or `pooper --glob <id>`.
- **Least-recent wins** — `pooper` auto-picks the glob you haven't pooped in longest. No backlog guilt.
- **No KYC, no bank.** Civiliter mortuus friendly. Just prompts — the kingdom stays local.
- **Private stays private.** `~/screenshots_scan` is `*` in `.gitignore`, `gh` naps, memories ≠ todos.

## Stay in terminal, no copy trick

```bash
pooper              # today's bite — auto least-recent
poop                # same, short
glob sherpa         # specific: sherpa / council / screenshots / bardildo / fater / ritual / no-kyc / cannibal
pooper --again      # re-poop last for a 2nd bite today
pooper --list       # 8 globs, ✓ vs ○
pooper --status     # done X/8, next auto
pooper --out ~/glob.md  # write to file
cat ~/.pooper/globs/sherpa.md   # read a past glob
```

Each glob:
- Title + 1-sentence win
- `Paste this into Claude/Gemini app` copy-all block (step-by-step, one at a time)
- 3 checkboxes
- Curiosity bite (how to get a 2nd today)
- Terminal receipts

## Globs (8)

| id | title | win |
|---|---|---|
| `sherpa` | Sherpa (your 1-letter tour guide) | Tour any folder with `c` and know RUN vs SUPPORT |
| `council` | Council (board that SEES your code) | Run `council` and get hard feedback with [E#] + sims |
| `screenshots` | Screenshots (TODO vs MEMORY) | Turn 5 screenshots into TODO vs MEMORY, private stays private |
| `bardildo` | Bardildo + History | Make folders remember after sleep (CURATOR + JANUS + where-was-i) |
| `fater` | Fartographer 💨🗺️ | Meet the map, leave a CURATOR in one incubator folder |
| `ritual` | Ritual (15 min a day) | Install the habit — one poop a day keeps the kingdom ordered |
| `no-kyc` | No-KYC paths (civiliter mortuus) | No ID, no KYC — peer/gift/local paths, funding parked |
| `cannibal` | Humane Cannibal | Preview a humane merge (archive, graft, py_compile-gated) |

## Humane rules

- No delete. Cannibal archives losers to `.archive_cannibal/` + grafts `__from_*`.
- Memories (deep chats) → `MEMORIES.md`, never a TODO, never auto-pruned unless file deleted.
- `gh` naps (soft pillow): `gh` → 💤, wake with `command gh`. Private stays local.
- `git go / gcb / back / grand` — checkout hell fixed, you never guess again.

## Where it lives

- `tools/pooper/pooper.py` — digester
- `~/.pooper/state.json` — done/last/started
- `~/.pooper/globs/*.md` — pooped globs on disk
- `~/.pooper/history.jsonl` — ts + glob
- `tools/pooper/CURATOR.md` — folder remembers
- `MRD.tct` — Master Receiving Details: tonight's run-back + living forward log (append-only)

## Tonight's run-back

See `~/MRD.tct` — full silly shit from tonight forward, digestible. `~/MRD.txt` stays as money plumbing; `MRD.tct` is the story.
