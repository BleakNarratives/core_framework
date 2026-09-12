# Atlas — Gap Atlas: gamified reproducible gap lens (market+scale first)

**One command, same deck every time (seed 42), 7 voids scored together for the first time.**

Novel lens: not coverage, not lint — **affordance voids**. Does the code let a *human* run it, pay for it, believe it, come back, scale to 100, find it, and survive without cruelty? Each project gets a **monster card** (CR = market-weighted) + **loot** (one close that moves market most) + **market** (TAM×pain×reach).

```
atlas --seed 42                                           # pan-wide dungeon (reproducible)
atlas ~/tools --seed 42                                   # scope fast
atlas --seed 42 --json /tmp/atlas.json --html /tmp/atlas.html   # map + deck
atlas --seed 42 --quest 2                                 # poop quest card → paste into Claude/Gemini app (15 min)
atlas --seed 42 --quest 5 --html /tmp/atlas.html          # scale quest + map together
```

## 7 voids (10=gap, 0=closed)

| # | void | Q | icon | market weight | loot |
|---|------|---|------|--------------|------|
| 1 | distribution | can a human RUN it? | 🚚 | 1.4 | one ENTRY: `python3 main.py --help` + `/health` |
| 2 | monetization | can a human PAY? | 💰 | 1.6 | gift path behind guard_judo (no KYC) |
| 3 | trust | can a skeptic BELIEVE? | 🧪 | 1.2 | `py_compile` gate + 1 test with receipt |
| 4 | retention | will they COME BACK? | 🔁 | 1.3 | cron/timer + Janus sediment + variable reward |
| 5 | scale | survive 10→100? | 📈 | 1.5 | deque FIFO + guard_judo tarpit |
| 6 | discoverability | can they FIND it? | 🗺️ | 1.1 | `sherpa --write` → CURATOR.md |
| 7 | cruelty | ships without deleting? | 💀 | 0.9 | humane_cannibal archive, never rm |

**CR** = market-weighted mean of 7 voids. **Boss** = highest CR. **MKT** = 0.34·TAM + 0.45·pain + 0.21·reach (Jerry bench = low TAM, pain 9 → still a boss).

## Dungeon deck (creative, reproducible)

- Same `seed` = same deck. `seed 42` is canon for MRD.tct.
- Each room is a project; clear rooms by closing the **loot void** (highest market-weighted gap).
- `atlas --quest N` poops a 15-min prompt for the Claude/Gemini app — paste-all, one step at a time.

## Market+scale (your ask)

Spelling lol — **scaleablity** is the spirit. Weights put 💰 and 📈 first. Reported in MRD.tct and HTML heat map. No Stripe/KYC — gift paths only (civiliter mortuus).

## Stay in terminal

```bash
atlas --seed 42 --max-projects 22              # dungeon (22 meaningful, filtered)
atlas ~/tools/jerry-hearing --seed 42 --quest 2  # Jerry lens
cat ~/tools/atlas/docs/atlas.seed42.html      # heat map
cat ~/tools/atlas/atlas.json | python3 -m json.tool | head -n 60
cat ~/MRD.tct | tail -n 30                     # meatsuit rundown forward log
```

Humane: archive not delete, hashed IPs, no push. Gamified like Odds of the Gods — every 3rd close = wheelie — but for code.

Generated 2026-09-10T22:22:53.002385 • seed 42 • `tools/atlas/atlas.py` 348L
