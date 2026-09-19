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

- [ ] **5. Commit the staged `docs/SYSTEM_DEPENDENCIES.md`.**
  317 lines, staged and uncommitted since before this session. It is a doc; commit
  it as its own docs commit unless it contradicts the tree.
  **Prove:** file content matches what is documented as installed.

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
