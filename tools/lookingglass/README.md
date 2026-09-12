# 🪞 Lookingglass — recursive chains → boardroom → eventuality → diff theater

**The slow one. Chain breathes, not sprints.**

You said: *these go too speedy, can we make it … soothing, gamified, if-this-then-that, seen thru a lookingglass?* + *fractal to a thousandth → battle until 2 → breed with molt + thinning* + *black/white? zen vs metalcore BLEGH?* + *sit and do this to all concepts more or less?*

This does all of it — same ethic, two skins.

## What it is

- **Recursive prompt chains** — parent → children, seeded, reproducible (same seed = same chain)
- Each link runs through **Codebase Boardroom** (6 hard cats, `[E#]`, state + sims)
- **Monitor safeguards every fork**: humane (archive not delete), bounded (depth 5, branch 3, parallel 2, budget 8k), no `rm -rf`, citations required
- **Sim to eventuality**: each tip forecasts downside/base/upside to *eventuality* (not next sprint — where does this path settle if you follow it?)
- **Lookingglass perspective**: every diff is a mirror — what would *future-you* thank you for?
- **Diff theater** — gamified, relaxing, `if this → then that`, subtle BGM, horse breathes with chain, **sipes/fades/mirrors that didn't exist yet** (now they do), flip **☯ metal → 🔥 BLEGH** for kersplosions/djent/thalls

## The arena you remembered (now humane)

OG boardroom: tracks → rounds → generations → arena (2 battle). We kept the **math** (tournament + genetics + Molt) and changed the **ethic** (garden, not slaughter):

```
fractal N (prompt variants, thinned BEFORE burning boardroom)
  → battle pairs (arena_score = 10-CR_eventual + delta + cites + mkt) until 2 remain
    → each survivor gets 1 molt shed (recursive improvement vector, contextual, not generic)
      → thinning = archiving, not deleting (loser → .archive_cannibal + __from_* graft)
        → breed final 2: host keeps both behaviors (humane_cannibal) → one more molt
```

Your drugs / avoidance / apology note? Heard. You *felt* the cruelty in `battle/breed/thin` in the same breath you imagined it — that's the monitor. `Molt` is shedding, not killing.

```bash
lookingglass --seed 42 ~/Official-Vertical-AI-Boardroom --depth 3 --branch 2          # chain 7 nodes, soothing
lookingglass --seed 42 ~/tools --depth 2 --branch 2 --arena 32 --generations 2       # demo arena (fractal 32 → battle → 2 → breed)
lookingglass --seed 42 ~/tools --arena 128                                            # hundred
lookingglass --seed 42 ~/tools --arena 1024                                           # thousandth (capped, thinned before burn)
lookingglass --seed 42 --if-this "close monetization void in p_recovery" --then-that  # single mirror
lookingglass --theater                                                                 # open theater (BGM + metal toggle)
lookingglass --concepts all --seed 42 --depth 2 --branch 2                             # sit with ALL concepts, one slow chain each (12 max, 0.35s breath)
lookingglass --concepts ~/p_recovery --seed 42 --arena 16 --depth 2                   # sit with that shelf, arena per concept
```

## Theater — white vs black, same ethic

- **White / zen**: teal/gold, sipes (slide+skew), fades (blur), mirrors (scaleX), Silver trotting, ground + cactus + tumbleweed, VU breathes with `delta`
- **Black / metalcore**: toggle `☯ metal` → `🔥 BLEGH` — bg goes void-red, difs `kersplode` + `djent`, square-wave 42Hz hit on fork, horse eye flicks red, same humane receipts
- Controls: `▶︎ breathe` / `⏸︎ hold` / `◀︎ sipe` / `sipe ▶︎` / `🪞 mirror` / `♫ bgm` / `☯ metal` + speed 0.9–4.2s + keys `Space` `←` `→` `M`

## Stay in terminal (you like staying in here)

```bash
lookingglass --seed 42 --depth 3 --branch 2 --no-mrd   # preview, no log
cat ~/tools/lookingglass/chains/chain-42-tools-d2b2.json | head -n 50
cat ~/tools/lookingglass/chains/arena-42-tools-p16g2.json | python3 -m json.tool | head -n 80
xdg-open ~/tools/lookingglass/theater/theater.html     # double-click also works on Chromebook
cat ~/MRD.tct | tail -n 30                              # meatsuit rundown — forward log, append-only
```

Private stays private (`screenshots_scan` .gitignored, theater.json local). `gh` napping. Humane: no deletion, ever.

