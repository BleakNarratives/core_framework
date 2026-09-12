# Jerry's Ears — Vintage Hearing Bench

**Mic → your hands → his ears. Vintage Vegas / Audition soul, JBL wood cheeks, VU that bounces, hard limiter so you can't hurt him.**

One file: `jerry.html`. Double-click it on Chromebook. No install, no internet, no KYC, no push. Stays local.

---

## What it does (2 modes)

**1. Hearing Test** — like the old booth, but a game
- Beeps at 250 / 500 / 1000 / 2000 / 4000 / 6000 / 8000 Hz, one at a time
- You raise `Level`, Jerry raises hand / taps `SPACE` when he hears it
- Hit `💾 SAVE threshold for 1000Hz` → draws his audiogram live
- You *see* where speech drops (almost always 2–4 kHz with age)
- Surprise-friendly: "hey Jerry help me test my music thing?"

**2. Live Assist / Tuner** — the wave-mangler for his earbuds
- `Mic → EQ (5 bands) → Fletcher-Munson loudness knob → Limiter (85dB) → Earbuds`
- VU left=mic, right=out. Gold is good, red is limiter.
- 5 knobs: LOW / 500 / 1.5k / 3.5k / AIR 8k (+ Fletcher-Munson contour)
- Presets: `🗣 SPEECH +3dB`, `⭐ JERRY'S SAVE`, `soft`, `clear`, `← apply test dots → EQ`
- `BYPASS` / `MUTE` / `LIMITER ON` always there. Never call it medical — it's a lens.

---

## Hardware — any old headphones? YES

**Best (lowest delay, clearest):** *any* cheap **wired earbuds** with a **3.5mm plug**
- Dollar-store wired buds are perfect. Closed (in-ear, seals) beats open, but open still works.
- Plug into Chromebook **headphone jack**. In ChromeOS click clock → volume → output → pick `Headphones`.
- Chromebook built-in mic is fine to start. Better: $8 lavalier (clip-on) into the mic jack if you have one. No adapter needed if you have a headphone jack.
- If your Chromebook is **USB-C only** (no jack): use a **USB-C → 3.5mm dongle** ($5). Any works.

**Works too:** **Bluetooth earbuds / headphones**
- Pair: Settings → Bluetooth → pair. Then output → pick his buds.
- **Expect ~120–250ms delay.** Fine for the beep test, a little echoey for live talk but still usable. Jerry will still say "clearer!" — just don't chase 0ms, wired is king for live assist.

**Cords & splitters — only if you need them:**
- **One jack does both (TRRS):** Chromebook single hole = mic+headphone combo. If you plug a *headset* (earbuds + mic on one plug) it just works. If you want *separate* mic + earbuds on one hole, you need a **TRRS splitter** ( $3: 1× TRRS male → 2× female: mic + headphones). Most wired lav mics + wired buds need this. Without it, Chromebook may think the earbuds *are* the mic.
- **Two jacks:** If your Chromebook has separate mic + headphone holes (rare now), just plug directly.
- **USB mic + 3.5mm buds:** Works too — Chrome will list both. Pick mic = USB, output = headphones.

**TL;DR pick one:**
1. **Easiest:** Built-in mic + wired earbuds in jack → `START MIC` → talk
2. **Better:** $8 lapel mic (3.5mm) + wired earbuds + TRRS splitter if needed
3. **Bluetooth:** Built-in mic + Bluetooth buds (ok for test, slight lag for live)

Wipe earbuds with alcohol wipe before swapping ears. Start volume at 1/4. Let him adjust — "is this comfy?"

---

## 60-second surprise script (so it's not awkward)

1. Plug wired buds in, keep Chromebook volume low.
2. "Hey Jerry — I built this goofy vintage radio, help me test if you hear the beep?"
3. **Hearing Test tab:** pick `1000 Hz` → `PLAY TONE` continuous → slowly drag `Level` up from -48 until he taps `SPACE` → `SAVE threshold`. Do 1000 → 2000 → 4000 → 800 → 500 → 6000 → 8000 → 250.
4. Click `← apply test dots → EQ` (turns test into a speech lift)
5. Switch to **Live Assist tab:** `START MIC` → talk normal, read him tonight's silly shit between rounds → "a little brighter? lower?" nudge **3.5k** ±2 dB, not bass.
6. When he says "that's it" → name `Jerry-Speech-1` → `SAVE preset`. Done. Dog-approved 🐶

---

## Saving & privacy

- Everything saves to **this Chromebook only**: `localStorage jerry/eq`, `jerry/audiogram`, `jerry/preset_*`, `jerry/notes`. Never calls internet.
- `Export CSV` / `export .md` makes a file *you* choose to share. Nothing auto-uploads.
- Limiter is always on when mic is live. If you toggle `LIMITER ON` off, it barely limits — leave it on.

---

## Quick troubleshooting

- **No sound in buds:** ChromeOS output still on `Speakers` → change to `Headphones`. Or earbuds plugged before Chrome started — unplug/replug.
- **Mic blocked:** Lock icon in address bar → Site settings → Mic = Allow. Or `chrome://settings/content/microphone`.
- **Echo/feedback:** You're monitoring loud. Turn down `Earbuds vol` or toggle `monitor` off (you don't need to hear yourself, he does). Move mic away from buds.
- **One ear louder:** Save separate `L` vs `R` thresholds (ear selector), then save two presets `Jerry-R` / `Jerry-L`.
- **Hearing aids why not working:** Common: wax, fit, dead battery/recharge, wrong program, feedback squeal → needs cleaning/fit check, not louder. Bench helps you *see* where he needs lift (2–4k) to tell a clinic/show them the CSV later.
- **VU not moving:** `START MIC` not hit, or mic permission denied, or `MUTE` is on.
- **Knobs do nothing:** `BYPASS EQ` is on (gold = off). Click again.

---

## Vintage UI cheat sheet

- **Drag knob up/down** to turn. **Double-click** resets to 0. Gold = your EQ, teal = speech band (500–4k), red diamonds = Jerry's saved thresholds.
- **Fletcher-Munson knob** (`0 flat → heavy`): at quiet, ears hear less bass/treble — this adds it back so quiet speech feels fuller. For Jerry, keep `gentle` (22), speech clarity > boom.
- Top VU: **LEFT = input** (mic), **RIGHT = output** (to his ears). Top LEDs: `LIVE` = active, `LIMIT` = limiter catching a peak (good, means it's protecting).

---

## Launch

```bash
# in terminal so you don't have to hunt:
xdg-open ~/tools/jerry-hearing/jerry.html   # or double-click in Files
# stay in terminal:
# sherpa ~/tools/jerry-hearing
# pooper --glob fater  (if you saved a Jerry glob)
```

*Not medical advice. If pain/pressure/ringing — stop, bypass, seek free screening. Wax: warm gentle, not picks. Big fella to old fella, humane as always.*
