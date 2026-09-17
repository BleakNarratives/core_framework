# REPO_ROOT_MIGRATION — filing the root sprawl into `projects/`

Written 2026-09-17. This is a **plan, not a record**. The only moves executed so far
are `projects/lean` and `projects/herald`, which were created as new project folders
rather than carved out of anything.

The point of writing it first is that this repository has already lost work to an
unscoped sweep: a session that edited 150 mostly-untracked files with no way back.
Moving 180 directories is the same class of operation with a bigger blast radius.

---

## 1. Baseline — the numbers this plan is based on

Measured 2026-09-17, not estimated:

| Thing | Count |
|---|---|
| Top-level directories (non-hidden) | **180** |
| Top-level loose files | **274 visible + 35 hidden** |
| Directories carrying a project marker (`README.md`, `pyproject.toml`, `package.json`, `AGENTS.md`, `QRD.md`, `MRD.*`, `Cargo.toml`, `go.mod`) | **85** |
| Directories with no marker at all | **95** |
| systemd user unit files | **51** |
| Active crontab lines | **5** |
| Root entries pinned by an absolute path | **12** |

The last row is the one that decides everything. `168` of the 180 directories are
referenced by nothing, so moving them cannot break a running job. `12` are pinned,
and those are the only places where a move fails *silently* — a cron line that no
longer resolves does not shout, it just stops doing its job.

---

## 2. What pins what

Extracted from the live crontab, the 51 user unit files, and the shell config:

| Root entry | Refs | Referenced by |
|---|---|---|
| `RootBase` | 3 | `.bash_aliases`, `canon-guard.service`, `tunnel-harvest.service` |
| `bin` | 3 | `janusd.service`, `session-beacon.service`, `session-watchdog.service` |
| `MikeySwarm` | 2 | `codebuff-bridge.service`, `overseer-daemon.service` |
| `ConstraintOps` | 1 | **crontab** |
| `Whorl` | 1 | **crontab** |
| `whorl-automation` | 1 | **crontab** |
| `venv` | 1 | **crontab** (the interpreter) |
| `Kindred` | 1 | `.bash_aliases` |
| `The-Werkz` | 1 | `.bash_aliases` |
| `MemGuard` | 1 | `pressure-watch.service` |
| `MouthTape` | 1 | `mouthtape.service` |
| `.modmind` | 1 | `janusd.service` |

Everything else at the root — `MarketScout`, `ScholarScout`, `TabScout`, `AxeScout`,
`OutClaw`, `MemGuard`-siblings, the `vertical_*` family, all the white-paper and
document directories — has **no live reference at all**.

### The three reference types behave differently

| Kind | Count | Failure mode when stale | Fix |
|---|---|---|---|
| crontab | 3 entries | **Silent.** The job stops. Nothing logs a path error. | Edit the line in the same change as the move, then run the command body by hand |
| systemd user units | 8 entries | **Loud-ish.** The unit fails and `systemctl --user status` says so | Edit `WorkingDirectory=`/`ExecStart=`, then `systemctl --user daemon-reload` |
| `.bash_aliases` | 3 entries | **Immediate and obvious.** You type the alias and it isn't found | Edit, then re-source in the shell |

Only the first kind can rot unnoticed, which is why it goes first.

---

## 3. Update order — references before moves

The ask was which absolute paths have to be updated first. Concretely, in this order:

### Step 1 — the three crontab entries (highest risk, do these first)

```
*/5 * * * *        /home/bleaknarratives/ConstraintOps/scripts/serve.sh
0 15 14 9 *        /home/bleaknarratives/venv/bin/python …/ConstraintOps/scripts/thread_monitor.py
0 * * * *          bash /home/bleaknarratives/whorl-automation/staggered_trigger.sh
*/15 * * * *       /home/bleaknarratives/Whorl/scripts/guard_daemon.sh
0 0 * * *          cd /home/bleaknarratives/Whorl && python3 -m unittest discover -s tests
```

Note what this list reveals: **`/home/bleaknarratives/venv/bin/python` is the
interpreter for a scheduled job.** `venv` is therefore not a project, it is
infrastructure pretending to be a directory, and moving it breaks a cron job in a
way that reads as "python not found" in a log nobody reads.

Two defensible approaches, and the plan should pick one before touching anything:

- **(a) Move + edit together.** Simple, and each move is one reviewable commit.
- **(b) Introduce a `$REPO_ROOT` indirection first.** Add one env file or wrapper so
  every reference reads `$REPO_ROOT/ConstraintOps/…`, verified ahead of any move.
  More upfront work, but then *no* move can break a cron line again.

**Recommendation: (b) for the crontab entries only.** Cron has no variable that
means "this repo", so today every scheduled job hard-codes a path that this plan
exists to invalidate. Fixing the indirection once is cheaper than re-editing the
crontab on every future reorganisation — and this repository clearly reorganises.

### Step 2 — the eight systemd unit references

`RootBase` (canon-guard, tunnel-harvest), `bin` (janusd, session-beacon,
session-watchdog), `MikeySwarm` (codebuff-bridge, overseer-daemon), `MemGuard`
(pressure-watch), `MouthTape` (mouthtape), `.modmind` (janusd).

After editing: `systemctl --user daemon-reload`, then `systemctl --user status <unit>`
for each, and `systemctl --user list-timers` for the timer-driven ones.

`bin` deserves a warning of its own: it is pinned by three units **and** it is the
`bin/ai` that `projects/herald/outreach_agent.py` calls. It is also already inside
the root allowlist, so it is already safe from the working-tree problem. **Moving
`bin` buys tidiness and costs risk. Recommend leaving it where it is and
documenting why.** (For the record: `herald`'s upward `find_ai()` walk would still
locate it at `projects/bin/ai`, so the move would not be fatal — just unnecessary.)

### Step 3 — the three aliases

`RootBase`, `Kindred`, `The-Werkz` in `.bash_aliases`. Lowest risk: a stale alias is
noisy the moment it is used. Do them last, in the same pass as the moves.

---

## 4. Phase plan

**Phase 0 — freeze.** Ensure the working tree is clean or deliberately parked. Record
the baseline: `crontab -l > /tmp/cron.baseline`, `cp -a ~/.config/systemd/user
/tmp/units.baseline`. These two files are the *contract*; everything else is movable.

**Phase 1 — reference indirection.** Do §3 Step 1. Verify by executing each cron
command body manually and confirming the same result as before the change.

**Phase 2 — unpinned projects, in bulk.** The 85 marked directories with no
references. This is the large, safe, boring part. One project per commit, or one
batch per category. Destination is `projects/<kebab-case-name>/` — **flat, not
nested**, because AGENTS.md already says not to add a nesting layer just to organise
a category.

**Phase 3 — pinned projects.** Do §3 Steps 2–3, then move those entries. Each move
is one commit that contains both the move and the reference edit, so the pair is
reviewable as a unit.

**Phase 4 — `projects/whorl_ecosystem/`.** This workspace already exists and is
already reserved for exactly this. Its natural members are `Whorl`, `Whorl-Telegram`,
`Whorl_Phase2`, `Whorl_Phase3`, `whorl_verification`, `whorl-automation`, `whorl`,
`.whorl`. **Do it last**: two of them are crontab-pinned and one is a pyproject
project with tests, so it is the highest-coupling move in the set.

**Phase 5 — the loose files and the 95 unmarked directories.** Triage, then archive
under `._archive/` or delete — deletion only with explicit approval, per entry.

---

## 5. Do not move these

| Entry | Why |
|---|---|
| `venv`, `.venv` | A crontab interpreter path. Infrastructure, not a project. |
| `bin` | Three units plus `herald`'s model interface. Already tracked. Move buys nothing. |
| Anything in the credential list below | See §6. |
| `projects/` itself, `docs/`, `tools/`, `src/`, `tests/`, `templates/`, `rag_storage/` | These are the allowlist roots. Moving them changes what git tracks. |

---

## 6. The trap: the allowlist turns a careless move into a secret commit

`.gitignore` is `/*` plus an allowlist — `!/src/**`, `!/docs/**`, `!/projects/**`,
`!/tools/**`, `!/tests/**`, `!/templates/**`, `!/rag_storage/**`.

That means **a move into `projects/` is also a decision to start tracking the file.**
It is what made `herald` committable and it is a hazard for anything that is not code.

The root currently holds files whose *names* indicate credentials or key material.
They are listed here by name only — none was opened, and none should be:

```
keyseses.txt          mo_keys.txt           mo-keys.txt
mo_mo_keys.txt        mo_mo_mo_keys.txt     opernrouter_api_vault_valet_concierge.txt
.git-credentials      .env_vault_migration_backup_20260830_225019/
```

Today the `/*` rule keeps these out of git. **Move one into `projects/` and the next
`git add -A` stages it.** So, before Phase 2 begins:

1. Classify every credential-shaped root file: still needed, or disposable.
2. For anything that stays, the destination gets its own `.gitignore` **written first**
   (as `projects/herald/.gitignore` does for `LEADS.md`).
3. Never `git add -A` during a migration. Stage explicit paths.

The same caution applies to `LEADS.md`/`OUTREACH_DRAFTS.md`-style data: `.gitignore`
at the destination, before the move, not after.

---

## 7. Verification — re-run the map, don't trust it

Before and after every phase, re-derive the pin table rather than reading this
document. A plan that is verified by reading the plan is not verified.

```python
# reference_map.py — which root entries does a live job actually depend on?
import re, subprocess
from pathlib import Path

HOME = Path.home()
pinned = {}

def note(source, text):
    for m in re.finditer(r"/home/[A-Za-z0-9._-]+/([A-Za-z0-9._~-]+)", text):
        pinned.setdefault(m.group(1), set()).add(source)

cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
for line in cron.splitlines():
    if line.strip() and not line.strip().startswith("#"):
        note("crontab", line)

for path in sorted((HOME / ".config/systemd/user").iterdir()):
    if path.is_file() and not path.is_symlink():
        note(f"unit:{path.name}", path.read_text(errors="replace"))

for rel in (".bash_aliases", ".bashrc", ".profile", ".aider.conf.yml",
            ".config/ai/config.toml"):
    p = HOME / rel
    if p.is_file():
        note(rel, p.read_text(errors="replace"))

for seg, srcs in sorted(pinned.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    print(f"  {seg:<28} {len(srcs):>2}x  {', '.join(sorted(srcs))}")
```

Expected output after Phase 1: the `crontab` rows are gone from the table, because
nothing hard-codes the path any more. That is the check that proves Step 1 worked.

---

## 8. Rollback

- **A move** is reversible: `git mv` back, or `mv`, then re-run the map.
- **The crontab** is restored with `crontab /tmp/cron.baseline`.
- **The units** are restored with `cp -a /tmp/units.baseline/. ~/.config/systemd/user/`
  followed by `systemctl --user daemon-reload`.
- **A mistaken `git add`** of a credential file: `git restore --staged <path>`, then
  confirm `.gitignore` covers it before anything is committed. If it reached a commit
  and was pushed, the secret is burned and must be rotated — the same conclusion as
  the 9Router token incident.

Because every phase is verifiable and every step is one commit, no phase needs to be
all-or-nothing.

---

## 9. Decisions this plan needs before Phase 2

1. **Which directories count as projects?** The mechanical answer is the 85 with a
   marker, but that misclassifies in both directions: `venv`, `models`, `vault`,
   `parsed_output` and `recovery_staged` carry a `README.md` without being projects,
   while a marker-less directory can still be one.
2. **Go relative or keep absolute?** Cron jobs could instead be pointed at a wrapper
   in `bin/` that resolves its own path — one more indirection, one less class of
   future breakage.
3. **Delete anything?** 95 unmarked directories is a lot of archive. Archiving is
   reversible; deleting is not, and it needs per-entry approval.
