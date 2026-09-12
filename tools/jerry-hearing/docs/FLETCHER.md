# Fletcher-Munson & Speech — Cheat Sheet for Jerry

> You don't need to understand curves to help him. This is the 2-minute version so you can twist knobs with confidence.

## Fletcher-Munson (equal-loudness) in one sentence

**At quiet, your ears are deaf to bass and sparkly treble. Loud, they hear everything.** So a quiet recording sounds thin unless you gently lift lows + highs. The "Fletcher-Munson knob" in Jerry's bench does that: `0 flat` = truth, `gentle 22` = sweet spot, `heavy` = boomy, not helpful for speech.

For Jerry: keep `gentle`. Speech clarity lives in the *middle*, not bass.

## Where speech lives

```
20 ───────────────────────────────── 16k Hz
      rumble  speech zone   sizzle    hiss
              ▓▓▓▓▓▓▓▓▓▓
              500 ── 4000 Hz  ← THIS is "can I understand words"
              1000–3000 is the consonant edge (S, T, F, CH)
```

- **500 Hz** — warmth / body of voice
- **1–1.5 kHz** — vowel power ("aah", "ooh")
- **2.5–3.5 kHz** — **intelligibility** (where "fine" vs "vine" lives) — **this is Jerry's money band**
- **6–8 kHz** — sizzle / "s" sound — lift a *little* for clarity, too much = harsh

Age-related drop (presbycusis) almost always starts **2k → 8k**, one ear worse. That's why he says "WHAT?" but hears the bass. The **audiogram** you're drawing will show dots diving down at 4k.

## What to do with 5 knobs

| Knob | Helps? | For Jerry start here |
|------|--------|----------------------|
| **LOW 60Hz** | Rumble, not speech. Keep flat or cut -2. Too much hides words. | **-2 dB** |
| **500 Hz** | Body. A touch helps, too much muddies. | **-1 dB** |
| **1.5 k** | Vowel power. Gentle lift helps. | **+2 dB** |
| **3.5 k** | **SPEECH CLARITY**. This is the dial that makes "human speech again." Nudge until he says "clearer." | **+3 → +5 dB** (tweak by ear) |
| **AIR 8k** | Sizzle: helps "s/f/th" distinction, harsh if over. | **+1 dB** |

Then: **Fletcher-Munson knob → `gentle (≈22)`**. Not heavy. You want words, not boomy music.

## How the test maps to EQ (auto)

1. Play beep → save threshold per freq (e.g., `R 4000Hz @ -14 dB` = needs louder).
2. The bench's `← apply test dots → EQ` looks at softest-heard frequency (reference = his best), then boosts worse frequencies proportionally (×0.55). It clamps to -6…+10 so you can't hurt him.
3. Check gold curve: peak in speech zone, not bass. Then **START MIC**, talk, fine-tune 3.5k by ear, **SAVE preset**.

## Why hearing aids "aren't working for whatever reason"

Common, not your fault:

- **Wax** — #1 killer. Muffles 2–8k exactly like age loss. Warm gentle, not picks. Clinic can flush free.
- **Fit / seal** — if not sealing, bass leaks, he cranks volume → squeal → he turns off.
- **Battery / charge** — weak battery = weak high freqs first.
- **Wrong program** — some aids have "music" vs "speech" vs "noise" — speech program is what he needs.
- **Needs re-programming** — after test, bring your CSV export to free screening (Costco often free) — "he drops at 3–4k, we lifted +5dB there" is gold to them.

## Safety ladder

1. Start earbuds volume **1/4**. Raise slowly.
2. Keep **LIMITER ON** (bench enforces ~85 dB ceiling, like a 1970s hardware limiter with VU).
3. Keep output VU in **gold**, not red. If `LIMIT` LED stays on, you're pushing too hard — back off.
4. If ringing/pressure/pain → `BYPASS` or `MUTE`, stop, try again tomorrow quieter.

## Quick presets

- **Speech +3dB (1–4k)** — the honest start, no audiogram needed.
- **Apply dots → EQ → save Jerry-Speech-1** — *his* curve, dialed for him.
- **Soft room** — gentle, less air, good for TV chatter in basement.

---

*One page. Pin this. When in doubt: nudge 3.5k, keep bass low, keep limiter on, let Jerry say "that's it."*
