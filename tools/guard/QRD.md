# QRD — Guard (worktree canon mirror)

**What it is:** Worktree-scoped clone of `~/RootBase/canon_guard.py` (PILLAR 3.0). Snapshots only `src+tools+package.json+.gitignore`, never `~`.

**Where:** `tools/guard/guard.sh` (bash, 0 deps) + `tools/guard/README.md` + `snapshots/*.tar.gz|.json` + `guard.jsonl` (SHA-256 chain, same ledger pattern as `~/RootBase/canon_guard.jsonl`).

**Commands:**
- `guard.sh snap "pre-ribbon"` — tar the ship, hash staged+tar, chain to `guard.jsonl`
- `guard.sh verify` — compares staged hash vs last snap, exits 1 on drift
- `guard.sh rollback <id>` — `tar xzf` back into repo root (ship globs only)
- `guard.sh budget` — PSI (`/proc/pressure/*`) + `free -h` + `df -h ~`, warns <400MB RAM or <2GB disk
- `guard.sh status` — ls + last 10 ledger entries + budget

**Chain:** `prior_sha + staged_sha + tar_sha → chain_sha` per entry. Verify with `cat guard.jsonl | python3 -m json.tool`.

**Integrate into recompile:** `guard.sh snap "pre-$intent" && recompile && guard.sh verify || guard.sh rollback <id> && exit 75`

**Gotcha:** `find src tools -type f | xargs sha256sum` hashes working tree when nothing is staged — that's correct for untracked builds but don't confuse staged vs working.

**Probe:** `./tools/guard/guard.sh budget` (live PSI on this Chromebook: avg10 8.77 mem, 28.41 io at 21:26 — not stalled, 548MB avail)
