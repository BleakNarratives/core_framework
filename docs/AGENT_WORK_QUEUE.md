# Agent Work Queue

Ordered work derived from what the 2026-09-19 session actually found — not from
wishes. Each item names the command that proves it is done. Governed by
`docs/AGENT_AUTONOMY.md`.

Work top to bottom. One logical change per commit. Update the checkbox in the same
commit as the work, so the queue cannot drift from reality.

## Open

- [x] **1. Make `scripts/emergency_hardening.sh` parse.** *(done 2026-09-19)*
  Done: the class is now escaped, `bash -n` exits 0, and the function was run
  verbatim — `a&b`, `a|b`, `a*b`, `a:b` still hit the metacharacter rule and
  `../etc/passwd` still hits traversal. `session_start.sh` and `update-readme.sh`
  still parse.


- [x] **2. Cover `src/ui/visualizer.py`.** *(done 2026-09-19)*
  Done: `tests/test_visualizer.py`, **18 tests, OK**. Ten graceful cases
  (missing file, zero-byte file, last-entry-wins, partial keys, missing payload,
  non-string values, non-ASCII) and five that pin the raising paths as they are
  (malformed JSON, blank trailing line, top-level array, null payload, string
  payload), plus isolation cases proving no write to the render directory and no
  `.boardroom_history.jsonl` created in the repo root.
  Still open: the five raising cases are a real weakness for a status line — they
  turn a bad log entry into a traceback instead of `[Boardroom: ...]`. Left as a
  separate change on purpose.

- [x] **3. Test the degradation claim in `src/skill/whorl_polyglot_bridge.py`.** *(done 2026-09-19)*
  Done: `tests/test_whorl_bridge_degradation.py`, **12 tests, OK**. The claim is
  asserted in a subprocess where `src.skill.*` genuinely cannot be imported, with
  the premise checked (the repo must *not* be on `sys.path`) and the other
  direction checked too, so the flag cannot pass as a hardcoded constant. The stub
  fallback is exercised, not merely imported: five bus methods, `send`/`status`
  returns, and the frontmatter parser's declared keys.
  Found while writing it: a module loaded by `spec_from_file_location` must be
  registered in `sys.modules` **before** `exec_module`, or the first module-level
  `@dataclass` dies with `AttributeError: 'NoneType' object has no attribute
  '__dict__'` — a loader bug that looks like a bug in the loaded file.

- [x] **4. Document the herald suite invocation.** *(done 2026-09-19)*
  Judged the wrapper sufficient, so the contract was left alone: `AGENTS.md` §6
  needs no herald line because `python -m unittest discover -s tests` already runs
  those tests through `tests/test_herald_suite_offline.py`. The nearest doc,
  `docs/PROJECT_MAP.md`, now records that next to its `projects/lean/` entry
  together with the direct invocation and the deliberately ignored lead data.
  **Prove:** the documented root command reaches herald's suite.

- [x] **5. Commit the staged `docs/SYSTEM_DEPENDENCIES.md`.** *(done 2026-09-19)*
  The Herald system-dependencies doc, staged since before this session. Its claims
  were checked against this machine and hold: `python3 --version` is **3.13.5**;
  `bin/ai`, `bin/ai_lib.py`, `bin/ai_gateway.py`, `bin/vault-env` all exist; herald's
  imports are stdlib-only (no `requests`/`feedparser`); its own documented command
  `python3 -m pytest projects/herald/tests -q` reports **130 passed**; and
  `LEADS.md`, `OUTREACH_DRAFTS.md`, `.herald_state.json` are ignored at
  `projects/herald/.gitignore:3,4,7` as the doc states.
  Committed once the owner confirmed the decision was not one he wanted to hold —
  nothing in the file was contradicted by the tree, and `git revert` undoes it.

- [x] **6. Check the metrics generator's undeclared dependency.** *(done 2026-09-19)*
  Done both, not either: the dependency is recorded in the generator's docstring
  (pytest on `PATH`, installed here at `~/bin/pytest`, named in no manifest), and the
  failure mode is explicit. A missing pytest now returns `status: error` naming the
  cause instead of an unhandled `FileNotFoundError`, and `scripts/update-readme.sh`
  refuses to publish a badge from a failed run — it exits 1 with
  `README.md left unchanged`.
  **Proved:** with `PATH=/usr/bin:/bin` the workflow printed the named error, exited
  1, and left README byte-identical to a backup taken beforehand. With pytest
  present it reported `status: success, passing_tests: 182`.
  Note: the badge counts pytest (`182 passed`), while the root `unittest` command
  reports `Ran 181 tests` — different tools, and `integration_test.py` is collected
  only by pytest.

- [x] **7. Decide the shape of `src/skill/run_retry_task.py`.** *(done 2026-09-19)*
  Premise corrected: it never reads `/tmp/molt_task2/retry.txt`. `grep -rn` found
  that path only in the docstring (and in `.aider.chat.history.md`), so the code
  cannot fail for a missing file. Chosen shape: say in the docstring that it is a
  one-off — no arguments, hardcoded probe inputs, `dry_run=True` returning before
  any provider dispatch so it needs no key, and runtime state written under the
  Git-ignored `rag_storage/molt_state/`.
  **Proved:** `python3 -m src.skill.run_retry_task` exits 0 and prints `PASS`, and
  `git status --short` shows no tracked file changed by the run.

- [x] **8. Cover the sovereign engine's Governor gate.** *(done 2026-09-19)*
  `src/sovereign/recursive_engine.py` (628 lines) claimed "Security: Oracle +
  Governor gate every mutation … No clause in this loop bypasses that" with no test.
  Now `tests/test_sovereign_governor_gate.py`, **13 tests, OK**: a write plan under a
  non-elevated governor is `blocked`, applies nothing, and reaches no subprocess at
  all; elevation stages intent without rewriting the file; an unsupplied governor
  resolves a real one and denies (the default is **deny, not allow**); and a full
  `cycle()` rolls back to `HOLD` with its journal under `$HOME`, which the test
  redirects to a temp directory. Phase 4's `unittest discover` is mocked so the test
  cannot re-enter this suite — the call count is asserted instead (0 when blocked).

- [x] **9. Make the boardroom status line degrade instead of raising.** *(done 2026-09-19)*
  Done in `src/ui/visualizer.py`: a truncated entry or a non-object entry returns
  `[Boardroom: Unreadable]`; a null, absent, or non-object `sanitized_payload` falls
  back to `[Unknown: UNKNOWN]`; blank lines are dropped so a trailing newline or a
  whitespace-only file is no longer read as damage. A damaged final line deliberately
  does **not** fall back to an earlier entry — reporting a stale status as current
  would hide the damage rather than surface it.
  **Proved:** `tests/test_visualizer.py` **21 tests, OK** (was 18; the five raising
  cases became placeholder assertions), and `python3 src/ui/visualizer.py` from the
  repo root still prints `[Boardroom: Waiting...]` with exit 0.

- [ ] **10. Bound the sovereign engine's phase-4 test run.**
  Every `cycle()` shells out to `python3 -m unittest discover -s tests` with a 30s
  timeout: the whole suite per cycle, and it cannot see the nested herald suite.
  Make it targeted or configurable and record the choice in the cycle record.
  **Prove:** a cycle runs a named subset, proven by the mocked call arguments.

- [x] **11. Cover `src/sovereign/bridges.py` and `daemons.py`.** *(done 2026-09-19)*
  Done: `tests/test_sovereign_bridges.py`, **18 tests, OK**. Pinned: `endempts_gate`'s
  three verdicts (SHIP commits, HOLD caps recorded violations at five, KILL deletes
  the file it was handed and tolerates a missing one), the Akasha fallback store's
  content addressing, and the daemons' degraded paths.
  **Found while writing it, and worth the whole exercise:** redirecting `$HOME` is not
  enough to contain the Thoth bus. `thoth_orchestrator/motherbrain.py:36` inserts its
  own directory onto `sys.path` at import time, so a later top-level `import agent_bus`
  resolves against the real `~/thoth_orchestrator`; and `agent_bus` defaults
  `ROOTBASE_DIR` to a hardcoded `/home/bleaknarratives/RootBase` that ignores `$HOME`.
  The first draft of this test consequently appended one real `molt.merkaba.route`
  event to the live bus. The harness now overrides `ROOTBASE_DIR` /
  `ROOTBASE_BUS_DIR` and asserts the bus file lands under the redirected home; the
  live bus is unchanged across a run (1398 lines before and after).
- [x] **13. Make the Thoth bus honour `$HOME`.** *(done 2026-09-19)*
  `agent_bus.py` now defaults `ROOTBASE_DIR` to `$HOME/RootBase`, and an explicit
  `ROOTBASE_DIR` / `ROOTBASE_BUS_DIR` / `ROOTBASE_EVENT_FILE` still wins.
  **Proved:** `tests/test_thoth_bus_location.py`, **5 tests, OK** — the default lands
  under a redirected `$HOME` and emits there, an explicit override still wins, and on
  a normal `$HOME` the path is byte-identical to the old hardcoded one. Across two
  consecutive full-suite runs the live bus gained **0** events.
  **Caveat worth remembering:** `thoth_orchestrator/` is untracked, so the fix itself
  is in no commit. The tests are the durable part; see `docs/PROJECT_MAP.md`.
  Fixing this also exposed three leaks the session had been relying on the old default
  to contain: the gate test appended real `molt.recursive.*` events (measured: 12 over
  three runs — its in-process `_phase_execute` cases emit before HOME redirection can
  matter), and the bridges and bridge-degradation harnesses each wrote
  `~/.whorl/whorl.db` because `whorl.core.config` ignores `HOME`. All three now set
  `ROOTBASE_*` / `WHORL_HOME` and assert the live bus is unmoved.
- [ ] **14. Give the autoloop a quiet mode.**
  `RecursiveEngine.autoloop` calls `cycle(verbose=True)`, so `tick_instar_autoloop`
  writes progress to stdout unconditionally — a caller that wants machine-readable
  output has to strip it. Asserted in the bridges test rather than fixed there.
  **Prove:** a quiet run writes nothing to stdout, asserted in the same file.
- [ ] **16. Give the suite one shared runtime sandbox.**
  Containing runtime state is currently per-file and incomplete. Measured with mtime
  markers (`touch $MARK` before a run, then `find ~/.whorl ~/RootBase -newer $MARK`):
  `tests/test_providers_generated` writes 2 files under `~/.whorl` when run alone, and
  full-suite runs flicker between 0 and 1 because `test_molt_triad`'s process-wide
  `WHORL_HOME` masks later writers. The Thoth bus (`~/RootBase`) is now clean.
  The fix is one place that points `HOME` / `WHORL_HOME` / `ROOTBASE_*` at a temp root
  for the whole run, not more per-file patches.
  **Prove:** a full-suite run leaves both directories byte-stable, twice in a row.
- [ ] **15. Fix the mutation vault's misleading note.**
  With `store_last_cycle=False` the result carries `note: "journal absent"` even when
  the journal exists and the caller simply asked not to store. The message names the
  wrong cause. Pinned as-is by the new test.
  **Prove:** the note distinguishes "no journal" from "not asked to store".

- [ ] **12. Decide whether the engine's import-time `mkdir` under `$HOME` is acceptable.**
  `recursive_engine.py` creates `~/RootBase/logs/shared/` at import time, and
  `bridges.py` / `daemons.py` compute the same path. Importing a module should not
  write outside the repository without a written reason.
  **Prove:** the write moves to first use, or the reason is recorded next to it.

## Settled 2026-09-19

- `tests/fixtures/mock_responses.py` is committed **with** a 20-case test that uses
  it, so it is no longer orphaned code; `tests/fixtures/__init__.py` came with it.
- `tools/inference/syntaxbuff.py.bak` is versioned behind a `.gitignore` allowlist
  rather than deleted. Its blob was in no commit, so it was the only copy.

## Needs Michael — never done autonomously

- **Decide whether `thoth_orchestrator/` should be tracked.** It is ignored, yet
  imported by tracked sovereign code, and its state paths are machine-pinned. Left
  alone deliberately: allowlisting a whole ignored package is a boundary decision.
- **Parameterize `scripts/emergency_hardening.sh`'s target root.** 40 functional
  `/workspace` paths point at a different sandbox. Running it here would create
  `/workspace` and then `chown -R root:root` it, and it embeds a copy of itself
  under `/workspace/scripts/`, so it is not a find-and-replace. A scope warning now
  sits in its header; the rewrite changes a guardrail, so it stays a decision.

- **Vendor `projects/lean/`.** Its 3 commits are unrecoverable if `.git` is removed.
  Left untracked, ignored, and documented in `docs/PROJECT_MAP.md`.
- **Anything visual.** The ribbon MRD sign-off block still has five unchecked boxes.

## Out of scope for this repository

- ChromeOS-side settings, including Accessibility → Dictation. Not reachable from
  the container; see the session handoff for what was verified on the Linux side.
- `filter-chain.service`, a stock Debian user unit, currently running with no
  visible filter node. Host-level, not repo-level.
