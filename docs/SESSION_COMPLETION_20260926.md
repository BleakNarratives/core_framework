# Session completion — 2026-09-26

Every claim below is backed by a command run in this session. Where something
was **not** verified, it says so.

## Test results

```
python -m pytest tests/ -q          -> 540 passed, 160 subtests, 0 failed
cd Whorl && python -m pytest tests/ -q
                                    -> 163 passed, 4 skipped, 13 subtests
```

Starting point was 513 passed / **1 failed**. The suite is now fully green.

## What changed

### 1. Pre-existing test failure fixed

`tests/integration_test.py::test_full_pipeline` asserted
`len(discover_topics()) == 1` and got 2.

**The engine was correct; the test was wrong.** `discover_topics()` has two
channels — insight-derived topics, and a MOLT channel that surfaces living
`SKILL.md` trees from the working directory. The second channel was returning
`Living skill: snark-reader` (a real skill, `scout.depth >= 3`), so the hard
total of 1 broke whenever the repo had a qualifying skill. The assertion is now
scoped to the insight-derived channel, which is what the pipeline guarantees.
Verified still-correct with an extra synthetic MOLT topic present (3 total,
solution channel still 1).

### 2. Whorl cascade arbitration

New: `Whorl/whorl/core/cascade.py` (pure, offline, no I/O).

Gates local inference on **task shape and token budget**, not on provider
preference. Classification, routing, extraction, dedup and short summarization
may run local; generation, reasoning and code authoring escalate. Every
escalation carries a reason — a decision that cannot be justified after the
fact is not one to act on.

`HostProfile.local_usable` keys off **measured resident MB** (`llama-server`
RSS), not on-disk size. That distinction is load-bearing: `llama3.2:1b` is
1.3GB on disk but 505MB resident, which is exactly why it runs here and
`gemma:2b` (~1.6GB resident) does not. An unmeasured model size fails closed.

New: `Whorl/tests/test_cascade.py` — 21 passed, 8 subtests.

### 3. Router fixes (3 copies: Werkz, SyntaxIntelligence, buffface)

- Removed a dead `provider_health(co_varnames)` first branch that fed the
  function's own local variable *names* into scoring.
- **SyntaxIntelligence `_KEY_POOL` capture bug** — found by the new tests, not
  by inspection. Its allowlist listed `GROQ_API_KEY_POOL` and
  `CEREBRAS_API_KEY_POOL`, but the vault capture filter was
  `endswith(("_API_KEY","_KEY"))`, so those vars could never be captured and
  rotation silently degraded to a single key. Same bug as Werkz; now fixed in
  both.
- SyntaxIntelligence: `cerebras` was declared in `DEFAULT_PROVIDER_ORDER` but
  missing from `_get_telemetry_order`, so telemetry ordering dropped it.
- Removed two `# demo:` hacks: a 5s `Retry-After` cap and a 5s 429 cooldown.
- `_call_ollama` now pins `num_thread=2, num_ctx=1024` and raises the timeout to
  180s, with the measurements that justify each value in the comment.

New: `tests/test_boardroom_router.py` — 13 passed, 11 subtests. Network-free
(every provider call is intercepted); the vault bootstrap is short-circuited by
setting `GROQ_API_KEY` before import, with a test asserting that seam holds.

### 4. Scout: real crawl + P2-before-P1 sidecar

`src/skill/scout.py` — depth ≥2 now performs a real Governor-gated crawl.
Sidecar reads verify the content hash **before** returning the payload; tampered,
malformed, digest-less and wrong-algorithm sidecars all return `ok=False` with
the payload withheld. No fetcher injected ⇒ no network, even with elevation —
the fetcher is the transport, the Governor is the permission.

`tests/test_scout_sidecar.py` — 13 passed.

### 5. Code City scanner

New: `Code-City-Apocalypse/Code_City/repo_scanner.py` + `tests/test_repo_scanner.py`
(21 passed, deterministic, offline). The claimed `repo_scanner.py` /
`city_mapper.py` in the source brief **did not exist**; `build_city.py` invented
buildings by hashing names in a hand-made `Codeshitty.txt` and never read any
code. The replacement measures real lines, nesting, TODO markers and flaw
signals.

### 6. Code smell sniff test

New: `tests/test_code_smell.py` — 13 passed, 21 subtests. AST-based (a regex
cannot distinguish a bare `except:` from one in a docstring). Detectors: bare
except, silent swallow, mutable defaults, oversized functions, deep nesting,
print/sleep in library code, unresolved markers. Scoped to the modules changed
this session — a repo-wide gate would be buried under pre-existing findings in
the archived dumps and tell us nothing.

**It found real problems in my own code**, which is the point:
- `scout.py` had an `except Exception: pass` around the bus emit. Now records
  into `self.warnings` — best-effort semantics preserved, silence removed.
- The print-detector's own allowlist went stale (line 127→130 after an edit).
  Rewritten to key on enclosing *function* rather than line number, with a test
  that fails if an allowlisted function disappears or stops printing.
- Marker detector flagged its own prose (`# ... 500-TODO file ...`). Tightened
  so a marker must stand alone.

### 7. System

Ollama 0.34.4 installed and tuned (`/etc/systemd/system/ollama.service.d/limit.conf`):
`KEEP_ALIVE=60s`, `MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1`, `CONTEXT_LENGTH=1024`
— each value justified by a measurement recorded in the file. `zstd` installed
as an ollama installer dependency. `gemma:2b` removed. `zram-tools` installed,
found unusable, then disabled with its config restored to packaged state.

## NOT verified — read this part

**Speculative decoding is not implemented and not tested.** Two independent
blockers, both verified:

1. `ollama 0.34.4` exposes **no** speculative/draft flags — confirmed against
   `ollama serve --help`.
2. No `llama.cpp` binary is present, and building it would need to hold the
   target model (505MB resident) *plus* a draft model *plus* a C++ link on a box
   with 546MiB available. It would OOM.

It remains the single highest-value inference win available (2–3x on CPU with a
small draft model). To test it, on a host with more RAM:

```
git clone https://github.com/ggml-org/llama.cpp && cd llama.cpp
cmake -B build -DGGML_NATIVE=ON -DLLAMA_ENABLE_SPECULATIVE=ON && cmake --build build -j
# draft model must be small; target + draft must both stay resident
./build/bin/llama-speculative --model target.gguf --draft draft.gguf
```

I have not run that and am not claiming a speedup.

**Also unverified:** whether the router's patched `_call_ollama` completes a live
call on *this* host. The payload shape and timeout are tested against a fake
`requests.post`, and the endpoint contract is real, but a live request timed out
at 180s during this session because the box was saturated. The patch is
correct-by-test, not correct-by-measurement on this host.
