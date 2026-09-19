# Agent Autonomy Contract

**Granted:** 2026-09-19 by Michael (repo owner), on branch `feature/ribbon-animation`.
**Scope:** this repository only.
**Relationship to AGENTS.md:** this file *extends* `AGENTS.md`, it does not replace it.
Where the two disagree, `AGENTS.md` wins and this file is wrong and should be fixed.

`AGENTS.md` §3 says consequential writes need human approval. This file records a
standing approval for a bounded set of them, so a session does not have to
re-litigate permission every message.

---

## 1. Standing approval — may be done without asking

- **Read anything** in the repository, and read-only state outside it (processes,
  services, audio devices, file listings).
- **Edit, create, and commit** files inside the repository, on the current branch.
- **Run the test suites** documented in `AGENTS.md` §6 and the nested-repo suites
  (`Whorl/`, `projects/herald/`, `projects/lean/`).
- **Run read-only diagnostics** (`git status`, `git log`, `git diff`,
  `git check-ignore`, `bash -n`, `py_compile`, `unittest`, `pytest`).
- **Snapshot before risky work** with `./tools/guard/guard.sh snap "<intent>"`, and
  roll back my own change with `guard.sh rollback <id>` if it regresses.
- **Revert my own work** if the relevant suite regresses and the fix is not
  obvious within the same unit of work.
- **Write tests and docs** for behaviour I just changed, in the same commit.
- **One logical change per commit**, with the `🤖 Generated with Codebuff` footer the
  repository already uses.

## 2. Never without an explicit, specific instruction

- `git push`, or any write to a remote.
- Rewriting history: `rebase`, `filter-branch`, `commit --amend` on a commit that
  is not mine-and-unpushed, force-push, `reset --hard`.
- Deleting a file I did not create in this session. Ignoring it is the default.
- Touching anything outside the repository — no `$HOME` dotfile edits, no systemd
  units, no system settings. The repo *is* the working directory; outside it stops.
- Reading, copying, printing, or committing secrets, tokens, keys, vault contents,
  or anyone's personal data. If such content appears, stop and report it.
- Network calls to external services, installing packages, or anything that spends
  credits or money.
- Merging or deleting the nested repositories (`Whorl/`, `projects/lean/`) — these
  are separate repositories and their boundaries are recorded in `docs/PROJECT_MAP.md`.

## 3. Stop and report instead of guessing

- A test regresses and the cause is not obvious.
- A change spans more than ~15 files, or more than one logical concern.
- The instruction is ambiguous about *what* is wanted (not merely about *how*).
- The change alters a security guardrail, a public signature, or a documented exit
  code. Improvement is fine; silent alteration is not.
- A file contains something that looks like a credential.
- Two sources in the repo contradict each other.

## 4. Verification bar

- Run the narrowest relevant test first, then the affected suite.
- State the exact command and the exact result count in the handoff. "Tests pass" is
  not a result; the exact `Ran <n> tests` / `OK` output is. (Deliberately not a
  literal count: this line has gone stale twice already.)
- If a dependency is missing, report that as a limitation. Do not substitute a
  different environment and call it equivalent.
- Never claim a file changed, a test ran, or an integration exists without
  command output in the same session proving it.

## 5. Handoff

Every run ends with the `AGENTS.md` §8 handoff: repository root and branch, files
changed or deliberately left unchanged, commands run with exact counts, known
failures, stale claims I made earlier in the session, and the next smallest
verified action.

## 6. What this contract cannot grant

Honest limits, so nobody plans around them:

- **I only run when messaged.** I cannot wake on a schedule, watch for a file, or
  continue after a turn ends. "Turned loose" means one long run per message.
- **I cannot see the screen.** Anything visual (a ribbon's motion, a ChromeOS
  setting, a rendered page) needs a human eye. I can only test the wiring under it.
- **I cannot reach outside this container.** ChromeOS settings, the browser, and the
  host system are outside my reach. `docs/` records what that leaves to Michael.
