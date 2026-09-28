# BLUE SKY MEETING — ROUND 1 (open critique)

You are one seat at a Blue Sky Meeting. Other independent models are getting this
exact same brief. You cannot see their answers. Be concrete, be adversarial, and
call out anything you think is hand-waving.

## THE PROPOSAL (verbatim, authored by a human, v0.1.0-alpha)

```
# ScoutDaemon: Socratic-Fallibilistic Runtime Specification
## Version: v0.1.0-alpha
## Purpose: Autonomous, Hydrated, Zero-Bloat Runtime Scouting

### 1. Architectural Model (The "ScoutDaemon" Convention)
This skill replaces reactive tool-calling with a pro-active "Scout daemon" runtime.
- **Hydration**: Pro-active pre-fetching on schedule.
- **Zero-Bloat**: Prompt already hydrated at IDE/Session open.
- **Interface**: Consumes `sidecar.json` for immediate state awareness.

### 2. Priority Hierarchy (Execution Logic)
1.  **Caching (P1 - Immediate)**: Trust local state. `sidecar.json` is the ground truth.
2.  **Verification (P2 - RAG)**: Syphoning/Disprove projection. If projected state != current state, re-index.
3.  **Simulations (P3/P4 - ML/Native)**: Invoke native engines (`iWarship`, `Poncho`) to populate `prediction_stream`.
4.  **Fallback (P5 - Final)**: Scraping/Agg/Lurking (Only triggered if sidecar is stale).

### 3. Distributed Model Input Interface (Multi-Model Feedback)
To mature this agent, the following endpoints are defined for continuous cross-model audit/verification:
- **`audit_log`**: Structured feedback from `Gemma`, `DeepSeek-V4-Flash`, `GPT-6-Luna`.
- **`reasoning_stream`**: Contradictory policy analysis from `StepFun`, `Solar-4`, `MiMo-2.6`, `GLM-5.3`.
- **`native_consensus`**: Synthesis layer from `Ox/SageOx`, `Puter-AI`, `Qwen`.
- **`adversarial_veto`**: Direct injection path for `Meta` models to force re-evaluation of high-risk decisions.

### 4. Maturity Milestones
- [ ] **Test**: Mock `daemon/scout.py` to generate `sidecar.json`.
- [ ] **Mold**: Integrate feed consumption in `inference_bridge`.
- [ ] **Grow**: Hook `iWarship`/`Poncho` into native simulation stream.
- [ ] **Mature**: Automated verification of multi-model feedback weights.
- [ ] **Complete**: Zero-tool-call hydration on initialization.
```

## WHAT I ACTUALLY FOUND IN THE REPO (verified, treat as ground truth)

I went and read the code before bringing this to you. Here is the real state:

**Already exists (most of §3 is already built, just not wired to models):**
- `src/skill/whorl_bus.py` (536 lines) — filesystem-backed transport. Has
  `send_sidecar()`, `send_mutation()`, `read()`, `poll_inbox()`, `acknowledge()`,
  `dead_letters()`, `emit_score()`, an agent registry, atomic writes, a logical clock.
  This is a working message bus already.
- `src/skill/arena_gladiator.py` (262 lines) — `combat()` pits two variants and scores
  them; `evolve()` does round-robin over N variants with win/loss/draw and an ELO-ish
  leaderboard. Oracle verdicts are **disqualifying**. This is a voting primitive.
- `src/skill/oracle.py` (260 lines) — content audit gate, `audit_text()` returns a verdict.
- `src/skill/governor.py` (463 lines) — scoped read/write/network/exec elevation + audit trail.
- `src/skill/inference_bridge.py` (300 lines) — `molt_one_shot()`, one-shot model call with
  no tool loop. Already has a "Bitchwork" output contract forcing each model to emit a JSON
  block `{persona, status, code, patch}` via `sanitize_persona_output()`. Writes to
  `.boardroom_history.jsonl`.

**The actual gap — exactly one adapter:** `inference_bridge` dispatches to
`tools/inference/syntaxbuff.py` or OpenRouter. It **never shells out to local agent CLIs.**
And `bin/model_router.py` knows the CLI names but every route is a stub —
`route_mistral_api()` returns the string `"Mistral API not configured."`, and
`route_fallback()` literally runs a shell command that charges $1 as a joke.

**`src/skill/scout.py` is a 95-line stub.** `run()` at `depth>=2` returns immediately:
no fetch, no sidecar written, `self.sidecar_dir` is a constructor kwarg that is never
read. So P1 "trust local state" currently has **no state to trust**, and milestone
"Test: mock `daemon/scout.py`" has **no daemon to mock**.

**§3's roster is fictional.** No `Gemma`, `DeepSeek-V4-Flash`, `GPT-6-Luna`, `StepFun`,
`Solar-4`, `MiMo-2.6`, `GLM-5.3`, `Ox/SageOx`, or `Meta` model is reachable on this box.
Likewise **§2 P3/P4 references `iWarship` and `Poncho`** — no such Python module exists.
The only `poncho` artifact is `MikeySwarm/poncho_lineup.sh`, a shell script, not an
engine you can call to fill a `prediction_stream`.

**The real roster** (verified installed, headless-capable):
`ox` (OpenRouter/Groq, has `--free-models`, personas mikey/architect/coder/skeptic),
`codex exec`, `gemini -p`, `puter`, `aider --dry-run --exit --yes-always`,
`kilo run` / `kilocode` / `opencode run` (all the same opencode v7.5.16 binary),
`vibe`. Also `ox-adapter-*` shims exist for aider/amp/claude-code/codex/droid/gemini/
goose/omp/opencode/pi. `qwen` is a stub that prints "Qwen Cloud Shim standing by...".
`ollama`, `openhands`, `kimi`, `modmind`, `molt`, `thoth`, `hermes` are NOT installed.

**Repo security posture (this is a hard constraint, not a suggestion):** the project's
AGENTS.md treats Scout documents as untrusted input, requires Oracle approval before
mutation, states explicitly that "Oracle approval does not grant Governor privileges"
and "a capability declaration is not permission." Any design you propose must not
let model output become executable instruction without passing the policy gate.

## THE 5 QUESTIONS — answer these specifically

1. **Sidecar ownership.** P1 says `sidecar.json` is "the ground truth." But scout.py never
   writes one. Who writes it, on what schedule, and what happens when two writers race?
   Is "ground truth" even the right framing when a fallback (P5) exists that re-scrapes?
2. **Priority hierarchy correctness.** P1 (trust cache) comes *before* P2 (verify). A
   cache-first ordering means a poisoned sidecar is trusted until something else catches
   it. Argue this ordering either way.
3. **Vote weighting.** §3 defines four channels with different models but says nothing
   about weights, quorum, or conflict resolution. `arena_gladiator` already does
   round-robin + ELO. Should the four channels be folded into that, or kept separate?
   What happens when `adversarial_veto` disagrees with a 4-0 `native_consensus`?
4. **What replaces the fictional roster.** Given only ~6 real agent surfaces, do we
   redefine §3 around *capability* (audit / contradict / synthesize / veto) rather than
   *model name*? Argue for or against.
5. **Sequencing.** The 5 milestones: which is genuinely first? "Complete: zero-tool-call
   hydration" is last as written, but "Mold: integrate feed consumption in
   `inference_bridge`" requires the bus to already carry something. Is the order wrong?

## OUTPUT FORMAT

Plain markdown. Keep it under ~700 words. Structure it as:

- **VERDICT**: one of SHIP_AS_IS / SHIP_WITH_CHANGES / DO_NOT_SHIP
- **THE 3 BEST IDEAS** (things the proposal gets right — be fair, not just critical)
- **THE 3 BIGGEST PROBLEMS** (ranked, most severe first)
- **ANSWERS** — one short paragraph per numbered question above
- **CUTTING ROOM FLOOR** — what you'd explicitly delete from the spec, and why
- **THE PATCH** — if 3+ of us would agree on a specific concrete change to the spec or
  code, state it precisely enough that someone could implement it. Be specific about
  file paths and function names. If you have no confident change, say so — do not invent one.

You are advisory. Nothing you write gets applied automatically.
