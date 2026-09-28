# Taps — the burial detail for a broken streak

**A missed day resets the count. This writes the note the reset leaves out: an append-only obituary, a gambit-shaped tombstone, and a 21-ribbon salute page.**

```bash
python tools/taps/taps.py --skill med-triage-copilot --user bubba --streak 4 --unit weeks
python tools/taps/taps.py --skill med-triage-copilot --streak 4 --unit weeks \
    --gambit-store rag_storage/instars --html /tmp/rite.html --speak
```

Offline, stdlib only, no credentials, nothing written outside `--root` (default `~/.taps`).

## Why it exists

A streak of 3 in `src/skill/gambit.py` buys exactly one thing: `next_due_at` becomes 48h instead of 24h. Miss, and that is the whole estate — one day, gone — while the record shows a bare `streak: 0` with nothing about what stood there. A tool that tracks progress should remember the progress it took back.

And this repository already decided how a miss should feel. From `tools/jerry-hearing/docs/ODDS_BRIDGE.md`:

> No streak shaming. Miss = cactus wobble "listen close..." not "you failed." Show is tender.

So the eulogy is under test: `SHAMING_TOKENS` is a constant, and the suite fails if any appear in it. Tender is an invariant here, not a style preference.

## What a burial leaves behind

| path | shape | on a second burial |
|---|---|---|
| `<root>/obituary.jsonl` | one JSON line per loss, all skills | appends |
| `<root>/graves/<user>__<skill>.jsonl` | tombstone per skill | appends |
| `<root>/rites/<user>__<skill>.html` | the salute page (`--html`) | re-rendered |
| `<root>/audio_notes.jsonl` | what a browser did with the sound (`--audio-status`) | appends |

Append-only is structural, not policy: both writers open in `"a"` mode, so a second burial cannot erase the first one's line.

## Reading gambit's ledger

`--gambit-store` reconstructs the run that the miss ended — consecutive passes, instar path, points, fastest answer, the date the last call did not land — and the eulogy names it:

```
  What the run left in the ledger:
    4 consecutive passes
    instar 2 → 3
    62 points
    fastest answer 11.8s
    2026-08-25 → 2026-09-21
    the call on 2026-09-22 did not land; the count went back to zero
```

No state file, or a run still standing, means no ledger block: the obituary records `"found": false` rather than inventing a history.

## What taps will not do

- **It will not touch live gambit state.** `--gambit-store` is a read. `InstarEngine._load` persists a fresh state file when it cannot find one, so asking the engine to inspect a grave would plant a fake one; `read_gambit_state` reads the JSON itself. The suite asserts the file's hash is unchanged.
- It will not contact the network, ask for credentials, or speak unless `--speak`.
- It will not decide the streak was your fault.

## The salute page

`taps.html` is one file with no CDN, no fonts, and no fetch. Open it directly, or let `taps.py --html` inject the obituary into its slot. Click `SALUTE`, the prairie, or press `space`: 21 ribbons rise, one drum thud each, brown gloves up, cactus wobbling, tumbleweed slow-rolling. On the twenty-first the bugle sounds taps, the ribbons fold, and the eulogy fades in.

Keyboard-first, because a rite you cannot reach is not one you can hold: `space` or `enter` salutes from anywhere, the count is an `aria-live` region, focus is visible, and the button relabels itself to "start the rite over" at twenty-one. Space *with the button focused* salutes once, not twice — the window handler stands down when a button already handled the key — and held keys do not repeat.

`prefers-reduced-motion: reduce` is honored, not approximated: no animation frame is requested at all, the prairie is drawn as a single settled frame, the ribbons fold at once, and the eulogy arrives promptly instead of fading. The preference is watched at runtime, so changing it mid-rite works too.

Sound waits for a gesture because browsers refuse autoplay — and because ringing a bugle at someone uninvited is not this tool's idea of tender. The page reads its obituary with `JSON.parse` from a JSON string literal, so an un-injected template still runs and falls back to a demo record.

Silence is explained rather than left mysterious. A context can be created in the `suspended` state, so the page resumes it before scheduling any note; if the browser has no Web Audio, blocks the resume, or has no output, a line under the button says which one happened and the ribbons keep counting.

**Audio here has never been *heard*.** The machine that ran these checks has no browser, so the sound path is inspected and exercised under a JavaScript shim only — enough to know the calls are ordered right, not enough to know it sounds good.

### Recording what a browser did

The obituary is written before any browser opens, so it starts with `"audio": {"status": "unverified"}` and never guesses. When the page finds it cannot make a sound, it says so on screen *and* prints the command that puts the fact in the record:

```bash
python tools/taps/taps.py --audio-status unavailable --audio-reason "no Web Audio" \
    --skill med-triage-copilot --user bubba --root ~/.taps
```

That appends to `audio_notes.jsonl` and writes **no second obituary** — the burial is the durable record, and rewriting it to add something learned later would make its first line a lie. Each note carries `obituary_lines`, which ties it to the burial it belongs to.

`RIBBONS` in the page and `SALUTE_COUNT` in the Python both equal 21; a test asserts they have not drifted apart.

## Verification

```bash
python -m unittest tests.test_taps_offline -v
```

Offline and deterministic: `tempfile` roots, `--at` for timestamps, no TTS process. One test drives a real `InstarEngine` in a temp store and checks that the 48h constant in `taps.py` still matches the rule gambit actually applies, so the restated rule cannot drift silently.

Three tests run `taps.html` in a JavaScript engine (`node`) under a DOM shim, skipped when node is absent so the suite still passes without one. They drive the whole 21-salute rite and assert what cannot be seen by reading the file: one keypress raising exactly one ribbon, no key repeat, exactly one animation frame requested when motion is allowed and **zero** when `prefers-reduced-motion` is set, the eulogy landing promptly under reduced motion, and a silent rite leaving `audio: unavailable` in the page's own record.

There is no browser on the machine this was built on, and none was installed to check a decoration. The look of the prairie, the sound of the bugle, and anything pixel-level are therefore **unverified by design** rather than merely untested, and are claimed nowhere.
