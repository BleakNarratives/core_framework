# GLOBS — 15-min Mikey bites: X → Sherpa

Each glob is one paste into Claude app / Gemini app. Copy the ``` block, phone walks you one step at a time, you paste terminal output back.

## 1. sherpa — Sherpa (your 1-letter tour guide)

**Win:** Tour any folder with `c` and know RUN vs SUPPORT in 15 min.

**Paste:** `pooper --glob sherpa` → copy the ``` block → Claude/Gemini app.

**Checks:** typed `c`, named hub, did `sherpa --egg`.

---

## 2. council — Council (board that SEES your code)

**Win:** Run `council` on any folder, read hard feedback with [E#] + sims.

**Paste:** `pooper --glob council`

**Checks:** ran council, named one hard role + its [E#], read synthesis + sims.

**Also:** `fartographer` is same council with 💨 wink.

---

## 3. screenshots — TODO vs MEMORY, private stays private

**Win:** Sweep 5 screenshots → TODO.md vs MEMORIES.md, checks survive.

**Paste:** `pooper --glob screenshots`

**Checks:** ran `--limit 5`, checked a TODO box and it survived re-run, saw MEMORIES separate + `.gitignore = *`.

**Private:** `~/screenshots_scan` is `*` in `.gitignore`, `raw_ocr.jsonl` local, memories never auto-pruned.

---

## 4. bardildo — Bardildo + History

**Win:** Make folders remember after you sleep: CURATOR + JANUS + where-was-i.

**Paste:** `pooper --glob bardildo`

**Checks:** `where-was-i`, `sherpa --write`, JANUS tail.

---

## 5. fater — Fartographer 💨🗺️

**Win:** Meet the map with heart, leave a CURATOR in one incubator folder.

**Paste:** `pooper --glob fater`

**Checks:** ran `fartographer`, left CURATOR in `project_incubator`.

**Origin:** cartographer on Mel's tablet + fart joke that stuck → `fartographer` command.

---

## 6. ritual — 15 min a day

**Win:** Install the habit: one poop a day = ordered kingdom without burnout.

**Paste:** `pooper --glob ritual`

**Checks:** `pooper --status`, picked tomorrow's glob, know extra bites are ok.

**Rule:** Council sim has burnout 1.35x baked in — respect it. `sherpa --write` (2 min) still counts as ordered.

---

## 7. no-kyc — No-KYC paths (civiliter mortuus)

**Win:** Know how to be useful without Stripe/KYC — not advice, just options. Funding PARKED.

**Paste:** `pooper --glob no-kyc`

**Checks:** know why `FUNDING.yml = false`, named one no-KYC path, drafted README thank-you line.

**Status:** `Official-Vertical-AI-Boardroom/.github/FUNDING.yml` false/false, `saas_lemonsqueezy.py` PARKED. No KYC provider is live.

---

## 8. cannibal — Humane Cannibal

**Win:** Preview a humane merge (archive, graft, py_compile-gated).

**Paste:** `pooper --glob cannibal`

**Checks:** `hc --dry-run` named winner/losers, saw `.archive_cannibal/` receipt.

---

## How the pooper decides

- Least-recent glob auto-wins (`pooper` with no args).
- `--again` re-poops last for a 2nd bite today.
- `--glob <id>` forces one.
- `--status` shows done vs remaining + next auto.
- `--out` writes markdown to file.
- State: `~/.pooper/state.json` (done timestamps, last, started).
- History: `~/.pooper/history.jsonl`.
- Globs on disk: `~/.pooper/globs/*.md`.

## Adding a new glob

Edit `tools/pooper/pooper.py` → `GLOBS` list: add dict with `id, title, win, prompt, checks, follow`. Run `python3 -m py_compile tools/pooper/pooper.py`, then `pooper --list`.
