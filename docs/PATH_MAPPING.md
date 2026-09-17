# PATH_MAPPING — every absolute path that has to be updated before a folder moves

Measured 2026-09-17 by scanning the live machine, not by reading the plan. Companion
to `docs/REPO_ROOT_MIGRATION.md`, which decides *whether and how* to move things;
this file is the *exhaustive list of what breaks*.

**Read §12 first if you have already read `REPO_ROOT_MIGRATION.md`.** That document
undercounted the pins — it reported 12 and missed an entire reference class.

---

## 1. Method, and the blind spot this file exists to fix

Four scans, all read-only:

| Scan | What it looked for |
|---|---|
| crontab | `crontab -l`, every non-comment line |
| systemd | every `*.service` in `~/.config/systemd/user/` and `/etc/systemd/system/` |
| shell | `.bashrc`, `.bash_aliases`, `.profile`, `.bash_profile`, `.gitconfig` |
| in-repo | literal `/home/bleaknarratives/...` strings in code, scripts and docs under `$HOME` |

**The first pass was wrong, and the way it was wrong is the important part.** It
matched the literal string `/home/bleaknarratives` in unit files, and reported 10
units pinning a path. Re-scanning with the systemd specifier `%h` expanded — `%h`
*is* `/home/bleaknarratives` for a user unit — the real number is **35 units**.

> A literal-string scan of systemd units is not a partial answer, it is a
> misleading one: the units that look clean are the ones written with `%h`, and
> they are pinned just as hard. Anyone re-running the original scan would have
> concluded that 25 units were safe to ignore.

That correction is why this file also records **17 pinned root entries from systemd
alone**, against the 12 the earlier plan reported for all reference types combined.

Not scanned, and therefore not covered: `~/.config/autostart/*.desktop`, shell
`ENV`/`BASH_ENV` chains, `~/.ssh/config`, editor task runners, and anything invoked
only by hand. Treat absence from this file as *"not verified"*, not *"safe"*.

---

## 2. Headline counts

| Thing | Count |
|---|---|
| Active crontab lines | **5** |
| systemd user units (real files) | **34** |
| systemd units in `/etc/systemd/system` | **5** |
| `.wants` symlinks (enabled state, not separate units) | 16 |
| **Units pinning a `$HOME` path** | **35 of 39** |
| Root entries pinned by systemd | **17** |
| Root entries pinned by crontab | **4** |
| Root entries pinned by shell config | 1 new (`Kindred`) |
| **Distinct pinned root entries (union)** | **22** |
| ConstraintOps files carrying a *live* code/exec path | **4** |
| Whorl files carrying a *live* code/exec path | **2** |
| Files under `tools/` carrying a path as **data** (safe) | 33 |

---

## 3. The three reference classes fail differently

| Class | If stale | Detectable? |
|---|---|---|
| **crontab** | Job silently stops. No error is logged anywhere. | **No** — this is the dangerous one |
| **systemd** | Unit enters `failed`; `systemctl --user status <unit>` shows it | Mostly yes |
| **shell aliases** | Immediate — you type the alias and get `command not found` | Yes, on first use |

Everything in §4 must be fixed **before** anything moves. Cron is the only class
where a mistake is indistinguishable from nothing having happened.

---

## 4. Crontab — fix these first

Verbatim, all 5 lines:

```cron
*/5 * * * * /home/bleaknarratives/ConstraintOps/scripts/serve.sh >> /home/bleaknarratives/ConstraintOps/state/cron.log 2>&1
0 15 14 9 * /home/bleaknarratives/venv/bin/python /home/bleaknarratives/ConstraintOps/scripts/thread_monitor.py --source hn --days 14 > /home/bleaknarratives/ConstraintOps/drafts/scan_20260914.md 2>&1
0 * * * * bash /home/bleaknarratives/whorl-automation/staggered_trigger.sh
*/15 * * * * /home/bleaknarratives/Whorl/scripts/guard_daemon.sh
0 0 * * * cd /home/bleaknarratives/Whorl && python3 -m unittest discover -s tests >> /home/bleaknarratives/Whorl/logs/daily_guard_sweep.log 2>&1
```

| Line | Pinned root entry | Note |
|---|---|---|
| 1 | `ConstraintOps` | Fires every 5 minutes — the highest-frequency job here |
| 2 | `venv`, `ConstraintOps` | **Annual** (`0 15 14 9 *` = 14 September). Moving it does not fail until next September |
| 3 | `whorl-automation` | Hourly |
| 4 | `Whorl` | Every 15 minutes |
| 5 | `Whorl` | Daily test sweep; the only line that is already `cd`-relative after the `cd` |

**Two things worth separating from the path question:**

- `venv/bin/python` is an *interpreter*, not a project. `venv`, `Implore-env` and
  `passive_income_swarm-env` all appear in this file as interpreters. They must be
  treated as infrastructure and never filed into `projects/`.
- Line 2 has already fired this year (annual on 14 September), so a broken move
  would not surface until 2027.

**The fix, before any move:** introduce one indirection so the crontab stops
hard-coding a directory that this plan exists to change.

```cron
CONSTRAINTOPS=/home/bleaknarratives/projects/ConstraintOps
WHORL=/home/bleaknarratives/projects/Whorl
```

Cron does support variable assignment at the top of a crontab. Whatever mechanism
is chosen, the crontab must be re-read and re-verified line by line afterwards —
there is no error to catch.

---

## 5. Systemd — 35 units pin a `$HOME` path

Resolved with `%h` expanded. Root entry → units:

| Root entry | Units | Pinned path example |
|---|---|---|
| **`bin`** | **15** | `ai-gateway.service` → `bin/ai_gateway.py`, `bin/vault-env` |
| **`RootBase`** | **8** | `canon-guard.service` → `RootBase/canon_guard.py` |
| **`MikeySwarm`** | **5** | `overseer-daemon.service` → `MikeySwarm/overseer_daemon.py` |
| `The-Werkz` | 3 | `swarm-orch.service` → `The-Werkz/SwarmOrch/run.sh` |
| `passive_income_swarm` | 3 | `dvm-worker.service` → `passive_income_swarm/nostr_dvm/dvm_worker.py` |
| `MemGuard` | 2 | `pressure-watch.service` → `MemGuard/pressure_watch.py` |
| `Code-City-Apocalypse` | 2 | `city-api.service`, `crash-feeder.service` |
| `.npm-global` | 2 | `9router.service` → `.npm-global/bin/9router` |
| `.local` | 2 | `airlock-scan.service`, `drift-report.service` |
| `MouthTape` | 1 | `mouthtape.service` → `MouthTape/server.py` |
| `Implore` + `Implore-env` | 1 | `implore-research.service` |
| `payment_system` | 1 | `payment-engine.service` → `payment_system/main.py` |
| `passive_income_swarm-env` | 1 | interpreter for `dvm-worker.service` |
| `.modmind` | 1 | `janusd.service` → `bin/janusd`, logs to `.modmind/logs` |
| `.agents` | 1 | `truthsleuth-audit.service` → `.agents/skills/internal-affairs/truthsleuth.py` |
| `.config` | 1 | `nostr-telemetry.service` → `.config/nostr/env` |

**`bin` is pinned by 15 units.** That is the single most load-bearing directory at
the root, and it is already tracked by git. The plan's decision to leave it in place
is not caution, it is arithmetic.

### Full unit → path listing

<details>
<summary>35 units, resolved (click to expand)</summary>

```
9router.service                 .npm-global/bin/9router
agent-asset-snapshot.service    MikeySwarm/archive/agent_assets, RootBase/agent_asset_snapshot.py
ai-gateway.service              bin/ai_gateway.py, bin/vault-env
airlock-scan.service            .local/share/airlock, bin/airlock
arena-bridge.service            RootBase, RootBase/arena_bridge.py
canon-guard.service             RootBase/canon_guard.py
city-api.service                Code-City-Apocalypse, Code-City-Apocalypse/code_city_api.py
codebuff-bridge.service         MikeySwarm/codebuff_bridge.py
crash-feeder.service            Code-City-Apocalypse, Code-City-Apocalypse/crash_feeder.py
dpo-collector.service           MikeySwarm/brown_team/collect_dpo_pairs.py, bin/vault-env
drift-report.service            .local/state/ai, bin/handoff_check
dvm-worker.service              bin/vault-env, passive_income_swarm/nostr_dvm/dvm_worker.py,
                                passive_income_swarm-env/bin/python
fleet-dashboard.service         RootBase/fleet_data/dashboard.log
freebuff-doctor.service         bin/freebuff_doctor.sh
higgins-kindred.service         The-Werkz/Higgins/front_office_canonical/...
hutch-clutch.service            RootBase/comb/run_all_tractors.py
implore-research.service        Implore/app, Implore-env/bin/python
janusd.service                  .modmind/logs, bin/janusd
kilo-dvm-health.service         .npm-global/bin/kilo, RootBase/fleet_data/kilo_health.log,
                                bin/vault-env, passive_income_swarm/nostr_dvm/dvm_worker.py
market-scanner.service          MikeySwarm/telemetry, bin/market_scan.sh
memguard.service                MemGuard/memguardd.py
mouthtape.service               MouthTape/server.py
nostr-telemetry.service         .config/nostr/env, RootBase/fleet_telemetry/...,
                                bin/vault-env, passive_income_swarm/nostr_dvm/dvm.env
overseer-daemon.service         MikeySwarm/overseer_daemon.py
payment-engine.service          payment_system, payment_system/main.py
pressure-watch.service          MemGuard/pressure_watch.py
round-engine.service            bin/round.sh
router-health.service           bin/router_health
session-beacon.service          bin/session_beacon.sh
session-watchdog.service        bin/session_watchdog.sh
swarm-orch.service              The-Werkz/SwarmOrch/run.sh
swarm-prune.service             The-Werkz/SwarmOrch/prune.sh
truthsleuth-audit.service       .agents/skills/internal-affairs/truthsleuth.py
tunnel-harvest.service          RootBase/tunnel_harvest.py
session-shield.service          bin/session_shield.py          [/etc/systemd/system]
```

</details>

The 4 units that pin nothing under `$HOME` are all system units and are not
candidates for any of this: `code-server.service` (`/usr/bin/code-server`),
`sshd.service` (`/usr/sbin/sshd`), `dbus-org.freedesktop.timesync1.service`, and
`packagekit-offline-update.service`. Every one of the 34 *user* units pins a
`$HOME` path — there is no user unit that this exercise can safely ignore.

---

## 6. Shell config

`.bash_aliases` pins four paths:

| Alias target | Root entry |
|---|---|
| `Kindred/kindred_cli.py` | **`Kindred`** |
| `RootBase/bin/start_swarm_tmux.sh` | `RootBase` |
| `The-Werkz/.env.vault` | `The-Werkz` |
| `The-Werkz/Official-Vertical-AI-Boardroom/vertical_ai.py` | `The-Werkz` |

`Kindred` appears **nowhere else** — it is pinned only by an alias, so a scan that
covered cron and systemd would have called it unreferenced.

---

## 7. In-repo hard-coded paths

Literal paths inside files. These matter even when the job list does not mention
them, because a moved directory turns each into a runtime failure.

### ConstraintOps — 4 live code/exec files

| File | Hard-coded path | Severity |
|---|---|---|
| `ConstraintOps/TrustLeash/hooks/trustleash-pre-commit` | `venv/bin/python` | **Git hook.** Breaks commits, silently, in whatever repo it is installed into |
| `ConstraintOps/scripts/capillary_router.py` | `ConstraintOps/staging` | Writes to a path that no longer exists |
| `ConstraintOps/scripts/critic_adapter.py` | `ConstraintOps/TrustLeash/trustleash/__main__.py` | Subprocess invocation |
| `ConstraintOps/TrustLeash/tests/test_adapters.py` | `.codex/sessions`, `.gemini/tmp/x/...` | Test fixture paths |

Plus **8 doc/data files** (not code): `QRD.md`, `README.md`, `runbook.txt` (all cite
`venv/bin/python`), `REPO_STRATEGY.md`, `portfolio/LIVE_SPRAWL_SELF.md`,
`portfolio/live_triage_self.md`, `site/audit_status.json`, `task_arch_auditor.txt`,
`task_design_lead.txt`. These need their text updated, not their behaviour.

### Whorl — 2 live files

| File | Hard-coded path |
|---|---|
| `Whorl/scripts/converge_ingest.py` | `$HOME`, `ConstraintOps`, `Whorl`, `Whorl/state/ecosystem_execution_pyramid.json` |
| `Whorl/scripts/guard_daemon.sh` | `Whorl`, `Whorl/logs/guard_audit.log` |

`Whorl/state/ecosystem_execution_pyramid.json` is a **data record** containing ~130
paths from a past sweep (including `UNPACKED/`, `p_recovery/`, `MRD.txt` files). It
is a historical inventory, not a live reference — do not "fix" it.

### Root scripts

| File | Hard-coded path |
|---|---|
| `scripts/agent_state.py` | `.agent_state.json` |
| `scripts/emergency_hardening.sh` | `.security/emergency.log` |
| `scripts/root2025_triage.py` | `NAT-Recovery-Kernel/intake/...` |
| `whorl-automation/survival_mode.py` | `.SLaSHdotHIDEfiles/SURVIVAL_HARDENED` |
| `bin/agentfork.sh` | `.local/bin/{aider,ox,qwen}`, `RootBase/bin/codex`, `bin/goose` |

---

## 8. Data versus live references — why `tools/` is safe

33 files under `tools/` contain the string `/home/bleaknarratives`. None of them is
a live reference. They are records:

- `tools/atlas/atlas.json`, `tools/atlas/docs/atlas.seed42.json` — ~22 root paths as inventory
- `tools/lookingglass/chains/*.json`, `theater/theater.json` — concept chains
- `tools/guard/snapshots/*.json` — **named by the paths inside them**; renaming the paths would corrupt the snapshot's own filename key
- `tools/ruberg/{1-spark,2-spec,3-patch,4-theater,inbox}/*` — spec/theater pipeline records
- `tools/coding/*.md`, `tools/archive_cannibal_dryrun_*.json` — prose and dry-run logs

**Rule: a path inside a snapshot, ledger or inventory is evidence of the past, not a
dependency on the present.** Rewriting them to match a move destroys the record of
what was measured. Leave them; they are the reason you can tell what moved.

---

## 9. The do-not-move list — 22 root entries

Union of all three reference classes. Moving any of these breaks something live:

| Root entry | Pinned by | Count |
|---|---|---|
| `bin` | systemd ×15 | 15 |
| `RootBase` | systemd ×8, `.bash_aliases` | 9 |
| `MikeySwarm` | systemd ×5 | 5 |
| `ConstraintOps` | **crontab** ×2 lines, in-repo code | silent |
| `Whorl` | **crontab** ×2 lines, in-repo code | silent |
| `whorl-automation` | **crontab** ×1 | silent |
| `The-Werkz` | systemd ×3, `.bash_aliases` | 4 |
| `passive_income_swarm` | systemd ×3 | 3 |
| `MemGuard` | systemd ×2 | 2 |
| `Code-City-Apocalypse` | systemd ×2 | 2 |
| `.npm-global`, `.local`, `.modmind`, `.agents`, `.config` | systemd | hidden dirs |
| `MouthTape`, `Implore`, `payment_system`, `Kindred` | systemd / aliases | 1 each |
| `venv` | **crontab** (interpreter) | silent |
| `Implore-env`, `passive_income_swarm-env` | systemd (interpreters) | infrastructure, not projects |

**Three of the four crontab-pinned entries are in this list, and cron is the class
that fails silently.** That is the whole argument for doing §4 first.

---

## 10. Order of operations

1. **Rewrite the crontab with one indirection** (§4) and confirm every job still
   resolves. Nothing moves until this is done, because this is the only step whose
   failure is invisible.
2. **Update the 4 ConstraintOps live files** (§7) and the `trustleash-pre-commit`
   interpreter path — a git hook that fails during a migration makes the migration
   look like the cause of unrelated breakage.
3. **Update the 2 Whorl live files** (§7).
4. **Leave §9 alone.** Filing them into `projects/` is the highest-risk, lowest-reward
   part of this entire exercise; the plan should move the *unpinned* 168 and stop.
5. **Write destination `.gitignore` files before moving anything into `projects/`.**
   `.gitignore` is `/*` plus an allowlist, so moving a root file into
   `projects/` is simultaneously a decision to start tracking it. That is correct
   for code and dangerous for the root files whose names indicate key material.
   Never use `git add -A` during a migration.
6. Re-run §11 after each phase.

---

## 11. Verification — run this, do not eyeball it

Extract and execute; it reproduces every number above. Exits non-zero if a pinned
path no longer exists.

```python
import re, subprocess
from pathlib import Path
HOME = Path.home()
FIELDS = ("ExecStart","ExecStartPre","ExecStartPost","ExecStop","ExecReload",
          "WorkingDirectory","EnvironmentFile","StandardOutput","StandardError",
          "ReadWritePaths","BindPaths")
pat = re.compile(r"^(%s)=(.+)$" % "|".join(FIELDS), re.M)

broken, pinned = [], set()
units = [u for d in (HOME/".config/systemd/user", Path("/etc/systemd/system"))
         if d.is_dir() for u in sorted(d.glob("*.service"))]
for u in units:
    text = u.read_text(errors="replace").replace("%h", str(HOME))
    for m in pat.finditer(text):
        for tok in m.group(2).split():
            tok = tok.strip("\"'")
            tok = tok.split(":")[0].lstrip("-+!@:")
            if "$" in tok or "(" in tok or "%" in tok:
                continue      # shell substitution -- not a static path, see §13
            if tok.startswith(str(HOME)) and not Path(tok).exists():
                broken.append((u.name, tok))

for line in subprocess.run(["crontab","-l"],capture_output=True,text=True).stdout.splitlines():
    if line.strip() and not line.strip().startswith("#"):
        for tok in re.findall(r"/(?:home|Users)/[^\s;&|>'\"$]+", line):
            pinned.add(tok)
            if not Path(tok).exists() and not tok.endswith((".log",".md",".txt")):
                broken.append(("crontab", tok))

print(f"units scanned: {len(units)}")
print(f"crontab paths pinned: {len(pinned)}")
for where, tok in broken:
    print(f"BROKEN  {where:34} {tok}")
print("OK" if not broken else f"{len(broken)} broken")
raise SystemExit(1 if broken else 0)
```

Note it excludes `.log`, `.md` and `.txt` targets: cron redirects create those, so
their absence before the first run is correct rather than broken.

---

## 12. Corrections to `docs/REPO_ROOT_MIGRATION.md`

That document was written before the `%h` scan and two of its numbers are wrong.
Both errors are in the safe direction for the *count*, and the unsafe direction for
the *plan*, because they omitted directories from the pinned set.

| Claim in `REPO_ROOT_MIGRATION.md` | Actual | Cause |
|---|---|---|
| "Root entries pinned by an absolute path: **12**" | **22** | `%h` in unit files was not expanded; only literal `/home/bleaknarratives` strings matched |
| Implied "10 units pin a path" | **35 of 39 units** | Same cause |
| "Active crontab lines: 5" | **5** — correct | — |
| "systemd user unit files: 51" | **34 real + 16 `.wants` symlinks + 5 system** | `.wants` symlinks were counted as units |

The plan's core judgement survives: the *unpinned* directories are still the safe
ones to move, and `bin` is still correctly left in place — now for a stronger reason
(15 units, not 3). What changes is the size of the frozen set. It is **22 entries,
not 12**, and three of the additions (`Kindred`, `.agents`, `payment_system`) appear
in exactly one reference type each, which is precisely the kind of singleton a
partial scan misses.

Unchanged and still required: the three decisions in §9 of that document — which
directories are genuinely projects, relative versus absolute cron, and what to
delete or archive.

---

## 13. Pre-existing breakage this audit found

Two units point at paths that do not exist **today**, before anything has moved:

| Unit | Missing target | State at scan |
|---|---|---|
| `nostr-telemetry.service` | `.config/nostr/env` — only `env.example` exists | inactive |
| `truthsleuth-audit.service` | `.agents/skills/internal-affairs/truthsleuth.py` — the whole directory is absent | inactive |

And one unit is currently **failed**, for a reason this audit does not diagnose:

| Unit | State | ExecStart |
|---|---|---|
| `canon-guard.service` | **failed** | `RootBase/canon_guard.py` — the file *does* exist, so the cause is elsewhere |

Active at the time of the scan: `ai-gateway`, `janusd`, `overseer-daemon`,
`pressure-watch`, `session-watchdog`.

Neither missing path is caused by a move — both predate this plan, and both units
are inactive rather than crash-looping. They are recorded because §11 exits non-zero
on them, and a future run must be able to tell *"the migration broke something new"*
from *"the two that were already broken"*. **Expected output of §11 today is exactly
those two lines and nothing else.** Fix them or accept them deliberately; what must
not happen is that they become background noise which hides a real regression.

### Two targets the snippet deliberately skips

`airlock-scan.service`, `janusd.service` and `kilo-dvm-health.service` contain paths
the static scan cannot resolve, because they are built at runtime:

- `/home/bleaknarratives/.local/share/airlock/report-$(date +%F).txt` — command substitution
- `/home/bleaknarratives/.modmind/logs'` and `.../kilo_health.log'` — a quote character inside the field

The parent directories all exist and were verified by hand. §11 skips any token
containing `$`, `(` or `%` rather than pretending to check it.
