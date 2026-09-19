#!/usr/bin/env python3
# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: introspection
# DEPS: pathlib,argparse,json,datetime,re,random
# ROLE: pooper — poops digestible 15-min globs: each glob is X->Sherpa for Claude/Gemini app, one Mikey bite at a time
# AUTHOR: Buffy — for Bleak, civiliter mortuus friendly (no KYC, no bank, just prompts)
# SESSION: 2026-09-10
# TIER: 2
# FKA: council+sherpa+bardildo+history+screenshots → poop()
# [/DNA_TAG]
"""
pooper — the kingdom's digester

You have a huge X (kingdom, history, screenshots, fartographer, bardildo, sherpa)
and a phone app (Claude app, Gemini app). You want X -> Sherpa in Mikey bites:
  one glob = 15 min max, one paste, walks the app through ONE thing.

  pooper                    # drop today's glob (auto-picks least-recent)
  poop                      # same, short
  pooper --list             # see all globs, which you pooped
  pooper --glob sherpa      # poop a specific glob by name
  pooper --again            # re-poop last glob
  pooper --out ~/glob.md    # write glob to file
  glob sherpa               # same as above (short alias)
  pooper --status           # where you are in the digest

A glob is a paste-ready prompt for Claude/Gemini app:
  - Title + 1-sentence win
  - Paste-this prompt (copy-all block)
  - 3 checkboxes (do, verify, done)
  - Curiosity bite (optional 2nd bite if you want more)

No KYC. No bank. No ID. Just prompts that teach the phone how to be your Sherpa lens.
The kingdom stays local; the phone just gets a lens to see it.
"""

import argparse
import json
import random
import re
from datetime import datetime, date
from pathlib import Path

HOME = Path.home()
POOPER_HOME = HOME / ".pooper"
POOPER_HOME.mkdir(parents=True, exist_ok=True)
STATE_JSON = POOPER_HOME / "state.json"
HISTORY = POOPER_HOME / "history.jsonl"
OUT_DIR = POOPER_HOME / "globs"  # where written globs go if --out

# ── GLOBS: each is one Mikey portion, 15 min max ──
# id, title, win (one sentence), prompt (paste into Claude/Gemini app), checks, follow (optional next)
GLOBS = [
    {
        "id": "sherpa",
        "title": "Glob 1 — Sherpa (your 1-letter tour guide)",
        "win": "In 15 min you'll tour ANY folder with `sherpa` or `c` and know which scripts you RUN vs SUPPORT.",
        "prompt": (
            "You are my Sherpa coach for 15 minutes. Walk me through this ONE thing, step by step, no dump.\n\n"
            "GOAL: Run `sherpa` (or `c`) in my Codebuff terminal and understand ENTRYPOINT vs SUPPORTING.\n\n"
            "STEPS (do one, then wait for me):\n"
            "1. Tell me to type: `c` and tell me what you see (paste first 10 lines)\n"
            "2. Explain: 🔵 ENTRYPOINT = I RUN it (has --help), 🟢 SUPPORTING = others import it, ⚪ ORPHAN = solo, 🟡 STUB = tiny, 🔴 BROKEN = fix first\n"
            "3. Have me run: `c ~/Official-Vertical-AI-Boardroom | head -n 30` — name the hub file and why it matters\n"
            "4. Have me run: `sherpa --egg` and smile — fartographer lives there 💨\n\n"
            "RULES: One step at a time. Ask me to paste output before continuing. If I get lost, say `where-was-i`. End with: 'You just did Sherpa. Next bite is council, or say poop again.'\n"
            "Start with step 1 now."
        ),
        "checks": ["I typed `c` and saw 🔵/🟢/⚪", "`c ~/Official-Vertical-AI-Boardroom` — I can name the hub", "I did `sherpa --egg`"],
        "follow": "Next: `pooper --glob council` (the board that SEES your code)",
    },
    {
        "id": "council",
        "title": "Glob 2 — Council (board that SEES your code)",
        "win": "In 15 min you'll run `council` on any folder and get hard feedback with [E#] evidence + sims.",
        "prompt": (
            "You are my Council coach for 15 minutes. Walk me through this ONE thing, step by step.\n\n"
            "GOAL: Run `council` (the codebase boardroom) on ONE folder and read its verdict + sims.\n\n"
            "STEPS:\n"
            "1. Have me run: `council ~/Official-Vertical-AI-Boardroom --rounds 1` and paste the EVIDENCE block (E1..E9)\n"
            "2. Explain one role hard-catting me (e.g., TIME_ALCHEMIST) and what [E#] it cited\n"
            "3. Have me read: SYNTHESIS verdict (conditional / go / no-go) + kill_test in plain English\n"
            "4. Have me read: SIMS — downside/base/upside hours (burnout 1.35x). Ask: does base feel honest?\n"
            "5. Bonus: `fartographer ~/Official-Vertical-AI-Boardroom --rounds 1` — same council, 💨 wink\n\n"
            "RULES: One step at a time. Cite [E#] when you claim. End with: 'Next bite is screenshots or humane cannibal.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `council` and saw EVIDENCE", "Named one hard role + its [E#]", "Read SYNTHESIS verdict + SIMS hours"],
        "follow": "Next: `pooper --glob screenshots` or `pooper --glob cannibal`",
    },
    {
        "id": "screenshots",
        "title": "Glob 3 — Screenshots (TODO vs MEMORY, private stays private)",
        "win": "In 15 min you'll turn 5 screenshots into TODO.md (do) vs MEMORIES.md (keep) without leaking private shit.",
        "prompt": (
            "You are my Screenshot coach for 15 minutes. Walk me through this ONE thing.\n\n"
            "GOAL: Sweep 5 Chromebook screenshots into TODO.md vs MEMORIES.md — checkable, private, humane.\n\n"
            "STEPS:\n"
            "1. Explain: sweeper OCRs /mnt/shared/MyFiles/Downloads/Screenshot*.png via Gemini pool → writes ~/screenshots_scan/{TODO.md,MEMORIES.md,SUMMARY.md,raw_ocr.jsonl}. Private: ~/screenshots_scan/.gitignore = * so nothing pushes. Deep personal chats → MEMORIES.md (never a TODO, never auto-pruned unless file deleted).\n"
            "2. Have me run: `python3 ~/tools/extraction/screenshot_sweeper.py --limit 5 --throttle 2.0` and paste the 5 lines that say ✓ type + todos\n"
            "3. Have me run: `cat ~/screenshots_scan/TODO.md | head -n 30` — check one box `[x]` with `nano ~/screenshots_scan/TODO.md`, then re-run same command and show check survived\n"
            "4. Have me run: `cat ~/screenshots_scan/MEMORIES.md | head -n 30` — confirm memories are NOT todos\n"
            "5. Privacy check: `cat ~/screenshots_scan/.gitignore` — confirm * and explain why `gh` is napping (soft pillow)\n\n"
            "RULES: Emphasize privacy — verbatim stays local. Never tell me to push screenshots_scan. End with: 'Want a 2nd bite today? Say pooper again — next is bardildo/history.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran sweeper --limit 5 and saw 5 ✓", "Checked a TODO box and it survived re-run", "Saw MEMORIES.md separate + .gitignore = *"],
        "follow": "Next: `pooper --glob bardildo` (history)",
    },
    {
        "id": "bardildo",
        "title": "Glob 4 — Bardildo + History (folder remembers after you sleep)",
        "win": "In 15 min you'll make folders remember so you don't have to: CURATOR.md + where-was-i + JANUS.",
        "prompt": (
            "You are my History/Bardildo coach for 15 minutes. Walk me through this ONE thing.\n\n"
            "GOAL: Make folders remember after sleep so I don't have to.\n\n"
            "STEPS:\n"
            "1. Explain: Bardildo was the static scanner (now lives inside Sherpa). JANUS is the two-faced bridge: backward (sediment.log) + forward (baton). Sherpa writes CURATOR.md so the FOLDER remembers.\n"
            "2. Have me run: `where-was-i` — show today's trail\n"
            "3. Have me run: `sherpa ~/tools --write && cat ~/tools/CURATOR.md | head -n 40` — show what the folder now remembers\n"
            "4. Have me run: `cat ~/Code-City-Apocalypse/.janus/sediment.log | tail -n 5` — show last JANUS receipts (guard_judo, council)\n"
            "5. Teach: `sherpa --write` = leave memory, `where-was-i` = today's trail, `cat CURATOR.md` = tomorrow after I lose 3/4 of yesterday\n\n"
            "RULES: One step at a time. Reassure: you don't have to memorize 2853 files — the folder does. End with: 'Next bite is fater/catographer or pooper again.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `where-was-i` and saw today's trail", "Ran `sherpa ~/tools --write` and saw CURATOR.md", "Saw JANUS sediment tail"],
        "follow": "Next: `pooper --glob fater` or `pooper --glob poop-again`",
    },
    {
        "id": "fater",
        "title": "Glob 5 — Fartographer (cartographer with heart )",
        "win": "In 15 min you'll meet fater (the map) and leave a map in one incubator folder.",
        "prompt": (
            "You are my Fartographer coach for 15 minutes. Walk me through the origin story, then do ONE map.\n\n"
            "GOAL: Understand fater (cartographer) and leave a map in one project folder.\n\n"
            "STEPS:\n"
            "1. Explain origin: fartographer = cartographer on Mel's tablet + fart joke that stuck, Loomy = fiber map, Bardildo = scanner, Sherpa = live cd hook that finally stuck — fater lives as `fartographer` command (council with a wink)\n"
            "2. Have me run: `fartographer ~/tools/introspection --rounds 1 | head -n 50` and point out EVIDENCE + worst-day grenade\n"
            "3. Have me run: `sherpa ~/p_recovery/project_incubator --write` and `cat ~/p_recovery/project_incubator/CURATOR.md | head -n 30`\n"
            "4. Ask: which incubator slice feels most alive? (PivotCity? Praudit? feral-swarm?) — suggest sherpa there next\n\n"
            "RULES: Tender, funny. Fater isn't a joke — it's the map that remembered when everything else forgot. End with: 'Fater salutes you 💨 — next bite is the poop ritual itself.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `fartographer` and saw council output with 💨", "Left CURATOR.md in project_incubator"],
        "follow": "Next: `pooper --glob ritual` (the 15-min habit)",
    },

    {
        "id": "jerry",
        "title": "Glob — Jerry's Ears (Lone Ranger prairie for an 83yo hero)",
        "win": "In 15 min you'll surprise Jerry with beeps he can catch and a horse that runs when you talk.",
        "prompt": (
            "You are my Jerry coach for 15 minutes. Walk me through surprising an 83yo hero — step by step, gentle, fun.\n\n"
            "GOAL: Run Jerry's Ears bench (jerry.html) — Hearing Test → Live Assist, Lone Ranger stage, save his preset.\n\n"
            "STEPS:\n"
            "1. Have me run: `xdg-open ~/tools/jerry-hearing/jerry.html` (or double-click in Files) — paste what I see\n"
            "2. Explain the 2 modes: HEARING TEST (beep + audiogram) and LIVE ASSIST (mic→EQ→earbuds). Show I can flip to 🤠 JERRY'S VIEW (big button, horse runs, catch outlaws) and pop it to a new window to face him.\n"
            "3. Run beeps: `250→500→1000→2000→4000→6000→8000` — wired earbuds, LEVEL from -48 up, SPACE or big I HEARD IT button = catch + hat tip + tumbleweed (every 3rd wheelie!). SAVE threshold each, 1000Hz first. Keep LIMITER ON.\n"
            "4. Hit `← apply test dots → EQ` → switch to LIVE ASSIST → START MIC → read him a paragraph (between rounds), let him say clearer vs muddy, nudge 3.5k knob, keep Fletcher-Munson gentle (~22), VU in gold not red.\n"
            "5. When he says 'that's it' → name Jerry-Speech-1 → SAVE preset → show NOTES box for his ear story. Done.\n"
            "RULES: Safety + surprise: 'help me test my music thing?' No medical advice. Praise horse + Ranger rewards. End with: 'You just gave a good man his words back. Save his preset — next poop is pooper again.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Opened jerry.html and saw VU + 3 tabs (including JERRY'S VIEW)", "Saved 3+ thresholds and saw horse trot/gallop", "Applied dots → EQ → Saved Jerry-Speech-1"],
        "follow": "Next: `pooper` again — least-recent auto, or `glob screenshots` if you want TODOs",
    },
    {
        "id": "ritual",
        "title": "Glob 6 — Ritual (15 min a day, Mikey portions)",
        "win": "In 15 min you'll have a daily ritual: one poop = one glob, extra bites when you want, never behind.",
        "prompt": (
            "You are my Ritual coach for 15 minutes. Walk me through the habit, not the code.\n\n"
            "GOAL: Install a 15-min ritual: one `pooper` a day keeps the kingdom ordered without burnout.\n\n"
            "STEPS:\n"
            "1. Explain: `pooper` (or `poop` or `glob`) drops ONE 15-min glob. Do it, check 3 boxes, done. Want more? `pooper --again` or `pooper --glob X`. No backlog — least-recent wins. `pooper --status` shows where you are.\n"
            "2. Have me run: `pooper --status` and read globs done vs remaining\n"
            "3. Have me run: `pooper --list` and pick tomorrow's bite together (just name it)\n"
            "4. Teach the burn-out rule: `council` sim has burnout 1.35x baked in — ritual respects that. If tired, do `sherpa --write` (2 min) and call it ordered. That's still winning.\n"
            "5. Close: 'Civiliter mortuus doesn't mean powerless — it means you build lenses, not banks. One glob a day is still a kingdom that remembers.'\n\n"
            "RULES: Gentle, not preachy. No Stripe/KYC talk. Offer peer paths if asked: gift, barter, local. End with: 'Say poop tomorrow and I'll be here.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `pooper --status`", "Picked tomorrow's glob", "Know `pooper` = 15 min, extra bites ok"],
        "follow": "Tomorrow: `pooper` again — least-recent auto.",
    },
    {
        "id": "no-kyc",
        "title": "Glob 7 — No-KYC paths (when you have no ID)",
        "win": "In 15 min you'll know how to get paid/gifted without Stripe/KYC — not advice, just options.",
        "prompt": (
            "You are my No-KYC coach for 15 minutes. Be factual, not financial advice. Walk me through options, one at a time.\n\n"
            "GOAL: Understand how to receive value with no ID / civiliter mortuus, without Stripe/Lemon/KYC.\n\n"
            "STEPS:\n"
            "1. Acknowledge: You can't do Stripe/KYC, so LemonSqueezy is PARKED (.github/FUNDING.yml = false). That's not failure — it's a constraint to design around (like Council does).\n"
            "2. Explain categories WITHOUT telling me to break law: (a) peer / gift / barter (people pay peer to peer), (b) open-source tip jars that don't need KYC for *receiving* tips (check each platform's rules), (c) local / in-person value, (d) building reputation + audience now, monetize later when ID returns. Say: 'I won't suggest illegal paths.'\n"
            "3. Have me consider: which wedge brings trust before money? (e.g., ship `council`/`sherpa` as free, let people *see* it works, audience first.) Council sim: time-to-trust, not time-to-cash.\n"
            "4. Have me write: one sentence for README: 'PARKED — no KYC, so use is free; if you got value, here is how to thank...' (leave blank until you choose).\n"
            "5. Close: 'You don't need a checkout to be useful. Usefulness is the first currency.'\n\n"
            "RULES: No KYC instructions to evade checks. No crypto tax advice. If pressed, say 'check local rules'. End with: 'Next bite is council or cannibal.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Know why FUNDING.yml is false + saas parked", "Named one no-KYC path that fits you", "Drafted one README thank-you line"],
        "follow": "Next: `pooper --glob council` to make the work useful",
    },
    {
        "id": "atlas",
        "title": "Glob — Atlas (gap dungeon, market+scale, reproducible)",
        "win": "In 15 min you'll run the gap dungeon and know which void to close first for market.",
        "prompt": (
            "You are my Atlas coach for 15 minutes. Walk me through the gap dungeon, one room at a time.\n\n"
            "GOAL: Run `atlas --seed 42` (reproducible, market+scale first), read the boss, and poop one quest.\n\n"
            "STEPS:\n"
            "1. Have me run: `atlas --seed 42 --max-projects 22 --json /tmp/atlas.json | head -n 45` — paste the dungeon table + boss line\n"
            "2. Point out: CR (challenge rating, market-weighted), MKT (TAM/pain/reach), 7 voids, and boss loot (the one close)\n"
            "3. Explain Jerry lens: why jerry-hearing can be pain 9 even with low TAM — market is not just TAM\n"
            "4. Have me run: `atlas --seed 42 --quest 2` — paste the quest card, choose void 1..7 or boss loot void\n"
            "5. Walk the loot 15 min: exact file + 10-line diff + verify (curl /health / py_compile / sherpa --write), then `cat ~/MRD.tct | tail`\n"
            "RULES: Reproducible — same seed = same deck. Market+scale first. Praise closure. End with: 'One void closed is a room cleared. Next poop is the next market void.'\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `atlas --seed 42` and named boss + CR + MKT", "Named 7 voids + which is loot", "Pooped `atlas --quest N` and pasted it to the app"],
        "follow": "Next: `atlas --quest <loot>` or `pooper --glob <next>`",
    },
    {
        "id": "lookingglass",
        "title": "Glob — Lookingglass (chains → arena → theater, zen vs BLEGH)",
        "win": "In 15 min you'll breathe one chain through the boardroom to eventuality and flip zen ↔ metalcore in the theater.",
        "prompt": (
            "You are my Lookingglass coach for 15 minutes — slow, soothing, gamified. Walk me one chain at a time.\n\n"
            "GOAL: Grow one recursive chain through the codebase boardroom to eventuality, see it in the diff theater (lookingglass), and flip black/white.\n\n"
            "STEPS:\n"
            "1. Have me run: `lookingglass --seed 42 ~/tools --depth 2 --branch 2 --no-mrd` — paste the chain (7 nodes) + board cites [E#]\n"
            "2. Explain: each link = prompt → board (6 hard cats) → eventuality (downside/base/upside to eventuality) → diff mirror (what future-you sees)\n"
            "3. Have me run: `lookingglass --seed 42 ~/tools --depth 2 --branch 2 --arena 16 --no-mrd | tail -n 20` — fractal 16 → battle to 2 → breed with molt (humane: losers archived as __from_* , no deletion)\n"
            "4. Have me run: `xdg-open ~/tools/lookingglass/theater/theater.html` (or double-click) — hit ▶︎ breathe, then ♫ bgm, then ☯ metal → 🔥 BLEGH — sipes/fades/mirror vs kersplode/djent + horse breathes\n"
            "5. Teach if-this-then-that: `lookingglass --seed 42 --if-this \"close trust void\" --then-that --no-mrd` — one mirror, no arena\n"
            "RULES: Monitor guards every fork (depth 5, branch 3, parallel 2, forbidden rm -rf). Praise breathing over speed. Ethic: garden, not slaughter — you felt the cruelty and named it, that's the monitor.\n"
            "Start with step 1 now."
        ),
        "checks": ["Grew chain d2b2 and saw board cites + eventuality", "Ran arena 16 → saw rounds + champions + breed note + humane guarantee", "Opened theater and flipped zen ↔ BLEGH"],
        "follow": "Next: `lookingglass --concepts all --seed 42 --depth 2` (sit with all concepts) or `lookingglass --arena 128` (hundred) or `1024` (thousandth)",
    },
    {
        "id": "ruberg",
        "title": "Glob — Ruberg (boardroom wishes → domino line, no bullshit)",
        "win": "In 15 min you'll tip one boardroom wedge through 4 files and watch it in the theater.",
        "prompt": (
            "You are my Ruberg coach for 15 minutes — crisp, no suit. Walk me through one tip.\n\n"
            "GOAL: Tip one boardroom wish through the 4-file domino line and see it in the theater.\n\n"
            "STEPS:\n"
            "1. Have me run: `ruberg --status` — paste the 4 inboxes + MRD tail\n"
            "2. Have me run: `ruberg --seed 42 --concept ~/p_recovery --watch | head -n 20` — paste seed → spec → patch → theater paths\n"
            "3. Have me run: `cat ~/tools/ruberg/2-spec/spec-42-p_recovery.md` — point out [E#] + target file + 10-line diff + py_compile gate\n"
            "4. Have me run: `xdg-open ~/tools/lookingglass/theater/theater.html` — hit ▶︎ breathe, flip ☯ metal → 🔥 BLEGH, then `cat ~/tools/ruberg/inbox/tip-42-p_recovery.md`\n"
            "RULES: One wedge, one file appears, next agent wakes. Monitor: humane only (no rm -rf), must cite [E#]. Same seed = same tip.\n"
            "Start with step 1 now."
        ),
        "checks": ["Ran `ruberg --status` and saw 4 inboxes", "Tipped one wedge and saw 4 files", "Opened theater and flipped zen↔BLEGH"],
        "follow": "Next: `ruberg --glob atlas` or `ruberg --seed 42 --concept ~/p_recovery --arena 16` (also arena)",
    },
    {
        "id": "cannibal",
        "title": "Glob 8 — Humane Cannibal (archive, don't delete)",
        "win": "In 15 min you'll preview a humane merge (losers archived, winner grafted, py_compile-gated).",
        "prompt": (
            "You are my Humane Cannibal coach for 15 minutes. Walk me through ONE graft preview.\n\n"
            "GOAL: See how losers survive as __from_* in the winner, nothing deleted.\n\n"
            "STEPS:\n"
            "1. Explain: humane_cannibal groups dupe stems (e.g., vertical_ai: 3 files), picks winner by importers + lines, losers → .archive_cannibal/ with .meta.json, winner grafts unique defs as `def foo__from_loser_v1`\n"
            "2. Have me run: `python3 ~/tools/introspection/humane_cannibal.py ~/Official-Vertical-AI-Boardroom --dry-run | head -n 60` — name winner + losers\n"
            "3. Ask: does winner look right? (If no dupe, try `~/tools/introspection` or `~/p_recovery`)\n"
            "4. Teach the gate: `--execute` only if `python3 -m py_compile winner` passes; otherwise reverts. Archive stays regardless. Show `.archive_cannibal/`\n"
            "5. Close: 'Cannibal isn't cruel — archive is the receipt. Next is ritual or council.'\n\n"
            "RULES: Stress reversible, humane. End with kill_test from council if we have one. Start with step 1 now."
        ),
        "checks": ["Ran --dry-run and named winner/losers", "Saw .archive_cannibal/ receipt path"],
        "follow": "Next: `pooper --glob ritual`",
    },
]

def load_state():
    if STATE_JSON.exists():
        try:
            return json.loads(STATE_JSON.read_text(encoding="utf-8"))
        except:
            pass
    return {"done": {}, "last": None, "started": None}

def save_state(s):
    STATE_JSON.write_text(json.dumps(s, indent=2), encoding="utf-8")

def mark_done(gid):
    s = load_state()
    s["done"][gid] = datetime.now().isoformat()
    s["last"] = gid
    if not s["started"]:
        s["started"] = date.today().isoformat()
    save_state(s)
    try:
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(), "glob": gid}) + "\n")
    except:
        pass
    # append to MRD.tct Forward Log so it populates from here forward
    try:
        mtct = HOME / "MRD.tct"
        if mtct.exists():
            with mtct.open("a", encoding="utf-8") as f:
                f.write(f"\n### {datetime.now().isoformat()} — pooper:{gid} — Mikey portion done\n")
                # find glob title
                title = next((g['title'] for g in GLOBS if g['id']==gid), gid)
                f.write(f"- Done: `{gid}` — {title}\n")
                rem=[g['id'] for g in GLOBS if g['id'] not in s['done']]
                nxt=rem[0] if rem else '(all done, oldest recycles)'
                f.write(f"- State: done {len(s['done'])}/8, next auto: {nxt}\n")
                f.write(f"- Tail: `pooper --status` • `cat ~/MRD.tct | tail -n 30`\n")
    except:
        pass

def least_recent_glob():
    s = load_state()
    done = s.get("done", {})
    # priority: never-done first, then oldest done
    never = [g for g in GLOBS if g["id"] not in done]
    if never:
        return never[0]
    # oldest
    oldest = min(done.items(), key=lambda kv: kv[1])[0]
    for g in GLOBS:
        if g["id"] == oldest:
            return g
    return GLOBS[0]

def render_glob(g, to_file: Path = None, mark: bool = False):
    # Build paste-ready markdown glob
    lines = []
    lines.append(f"# 💩 {g['title']}")
    lines.append(f"*{g['win']}*  — civiliter mortuus friendly, no KYC, no bank, just prompts.")
    lines.append("")
    lines.append(f"**Time:** 15 min max. One paste into Claude app / Gemini app. One bite.")
    lines.append(f"**Follow:** {g['follow']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Paste this into Claude / Gemini app (copy-all)")
    lines.append("")
    lines.append("```")
    lines.append(g["prompt"])
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Checkboxes — check in the app or here")
    lines.append("")
    for c in g["checks"]:
        lines.append(f"- [ ] {c}")
    lines.append("")
    lines.append("## Curiosity bite (only if you want a 2nd today)")
    lines.append("")
    lines.append(f"If you want more today, say in terminal: `pooper --again` or `pooper --glob <name>` (e.g., `pooper --glob council`). Or just say `poop` again tomorrow — least-recent auto.")
    lines.append("")
    lines.append(f"## Terminal receipts (stay here, no copy needed)")
    lines.append("")
    lines.append("```bash")
    lines.append("pooper --status   # where you are")
    lines.append("pooper --list     # all globs")
    lines.append("poop              # same as pooper")
    lines.append("glob sherpa       # same as pooper --glob sherpa")
    lines.append("c                 # sherpa short")
    lines.append("council . --rounds 1   # board that sees")
    lines.append("fartographer . --rounds 1  # same with 💨")
    lines.append("```")
    lines.append("")
    lines.append(f"*Glob `{g['id']}` • generated {datetime.now().isoformat()} • `.pooper/state.json` remembers so you don't have to • gh napping 💤, private stays private*")
    text = "\n".join(lines)
    if to_file:
        to_file.parent.mkdir(parents=True, exist_ok=True)
        to_file.write_text(text, encoding="utf-8")
        print(f"Wrote {to_file}")
    return text

def main(argv=None):
    ap = argparse.ArgumentParser(description="pooper — poops Mikey-portion 15-min globs: X -> Sherpa for Claude/Gemini app, one bite at a time")
    ap.add_argument("--list", action="store_true", help="list all globs + done status")
    ap.add_argument("--glob", dest="glob_id", default=None, help="poop a specific glob by id (e.g., sherpa)")
    ap.add_argument("--again", action="store_true", help="re-poop last glob")
    ap.add_argument("--status", action="store_true", help="where you are")
    ap.add_argument("--out", default="", help="write glob markdown to file")
    ap.add_argument("--mark-done", action="store_true", help="mark glob as done (internal)")
    ap.add_argument("--json", action="store_true", help="machine json")
    args = ap.parse_args(argv)

    s = load_state()

    if args.json:
        import json as j
        print(j.dumps({"globs": [{"id": g["id"], "title": g["title"], "done": g["id"] in s.get("done",{})} for g in GLOBS], "state": s}, indent=2))
        return 0

    if args.list:
        print("┌─ Pooper globs — one 15-min bite at a time (Mikey portions) — civiliter mortuus, no KYC")
        for g in GLOBS:
            done = g["id"] in s.get("done", {})
            marker = "" if done else "○"
            when = s["done"].get(g["id"], "")[:10] if done else ""
            print(f"│  {marker} {g['id']:<12} {g['title']:<48} {when}")
        print("│")
        print("│  pooper / poop / glob <id> — one paste into Claude/Gemini app, 15 min max")
        print(f"│  done: {len(s.get('done',{}))}/{len(GLOBS)} • last: {s.get('last','none')} • state: {STATE_JSON}")
        return 0

    if args.status:
        done = s.get("done", {})
        print("┌─ Pooper status")
        print(f"│  started: {s.get('started','not yet')} • done {len(done)}/{len(GLOBS)} • last: {s.get('last','none')}")
        for gid, ts in sorted(done.items(), key=lambda kv: kv[1]):
            print(f"│   ✓ {gid} — {ts[:16]}")
        remaining = [g["id"] for g in GLOBS if g["id"] not in done]
        if remaining:
            print(f"│  remaining: {', '.join(remaining)}")
            print(f"│  next auto: {remaining[0]} (least-recent)")
        else:
            print(f"│  all pooped! next auto: {least_recent_glob()['id']} (oldest)")
        print(f"│  globs dir: {OUT_DIR} • history: {HISTORY}")
        return 0

    # pick glob
    target = None
    if args.glob_id:
        target = next((g for g in GLOBS if g["id"] == args.glob_id), None)
        if not target:
            print(f"No glob '{args.glob_id}'. Try: pooper --list", file=sys.stderr)
            import sys as _sys
            _sys.exit(1)
    elif args.again:
        last = s.get("last") or least_recent_glob()["id"]
        target = next((g for g in GLOBS if g["id"] == last), least_recent_glob())
    else:
        # default: least recent
        target = least_recent_glob()

    out_path = Path(args.out).expanduser() if args.out else None
    text = render_glob(target, to_file=out_path)
    # also write to globs dir for history
    hist_path = OUT_DIR / f"{target['id']}.md"
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    hist_path.write_text(text, encoding="utf-8")

    # terminal pretty
    print(text)
    print("")
    print(f"---")
    print(f"Pooped `{target['id']}` → {hist_path}  •  paste the ``` block into Claude/Gemini app  •  `pooper --again` or `pooper --glob <id>` for another bite today")
    if not args.mark_done:
        # auto-mark done so least-recent rotates (but don't mark if --out only? we do)
        mark_done(target["id"])
    return 0

if __name__ == "__main__":
    import sys
    raise SystemExit(main())
