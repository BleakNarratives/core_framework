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


- [ ] **2. Cover `src/ui/visualizer.py`.**
  24 lines, no test. It renders the last boardroom entry from
  `.boardroom_history.jsonl` and guards missing/empty/malformed input. Pure
  string-in/string-out, so it is cheap to pin — including the malformed-JSON case,
  which currently raises rather than degrading.
  **Prove:** new test in `tests/` passes and the case count is reported.

- [ ] **3. Test the degradation claim in `src/skill/whorl_polyglot_bridge.py`.**
  1006 lines and no test. Its docstring promises "zero-network, degrades gracefully
  if Whorl/MOLT missing". That is a testable import-time property, not a runtime
  hope.
  **Prove:** importing it with Whorl/MOLT absent succeeds, and the suite stays green.

- [ ] **4. Document the herald suite invocation in `AGENTS.md` §6.**
  `tests/test_herald_suite_offline.py` now runs it, but §6 lists only the root and
  Whorl commands, so the direct invocation still lives in a docstring comment.
  Update the nearest doc, not the contract, if the wrapper is judged sufficient.
  **Prove:** the documented command runs the 130 herald tests.

- [ ] **5. Commit the staged `docs/SYSTEM_DEPENDENCIES.md`.**
  317 lines, staged and uncommitted since before this session. It is a doc; commit
  it as its own docs commit unless it contradicts the tree.
  **Prove:** file content matches what is documented as installed.

- [ ] **6. Check the metrics generator's undeclared dependency.**
  `tools/README_metrics_generator.py` shells out to `pytest`, which is not in
  `package.json` or any requirements file. It works here because pytest 9.1.1 is
  installed by hand. Record that, or make the failure mode explicit.
  **Prove:** the documented install path can run the badge workflow, or the
  limitation is written down.

- [ ] **7. Decide the shape of `src/skill/run_retry_task.py`.**
  It reads its task from `/tmp/molt_task2/retry.txt`, so it only works where that
  file exists — a one-off dressed as a utility. Either take a path argument, or say
  in its docstring that it is a one-off.
  **Prove:** running it without the /tmp file produces a clear message, not a traceback.

## Needs Michael — never done autonomously

- **Vendor `projects/lean/`.** Its 3 commits are unrecoverable if `.git` is removed.
  Left untracked, ignored, and documented in `docs/PROJECT_MAP.md`.
- **Delete `tools/inference/syntaxbuff.py.bak`.** Its blob is in no commit; the copy
  on disk is the only one. One `rm` if that is what you want.
- **`tests/fixtures/mock_responses.py`** (staged, 484 lines) is imported by nothing.
  Committing it lands code no test exercises.
- **Anything visual.** The ribbon MRD sign-off block still has five unchecked boxes.

## Out of scope for this repository

- ChromeOS-side settings, including Accessibility → Dictation. Not reachable from
  the container; see the session handoff for what was verified on the Linux side.
- `filter-chain.service`, a stock Debian user unit, currently running with no
  visible filter node. Host-level, not repo-level.
