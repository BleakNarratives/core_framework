# Guard — Snapshot + Rollback + Budget Watch

One demon, three jobs: snapshot before you ship, roll back when it breaks,
and cut the session before you starve the box.

Mirrors `~/RootBase/canon_guard.py` (the 3.0 PILLAR) but for the *worktree*
(`src/` + `tools/` + `package.json` + `.gitignore`). RootBase already has
its own `.canon_snapshots/` ledger — Guard extends the pattern here.

## Why this exists

Chromebook is 2.6GB RAM + 92GB disk, 77% full. One bad `npm i` or a hard DOM
recompile can OOM or fill the disk. Every other tool re-scanned the whole
53GB tree on every run and choked. Guard snapshots only what we ship.

## What it does

1. **SNAP** — `./tools/guard/guard.sh snap "pre-ribbon"` → content-hash
   snapshot in `tools/guard/snapshots/` (manifest JSON + tar of staged area).
2. **VERIFY** — `./tools/guard/guard.sh verify` → re-hashes current stage,
   fails if any drift vs snapshot (deployed by `recompile`).
3. **ROLLBACK** — `./tools/guard/guard.sh rollback <id>` → restores staged
   area from snapshot tar (called automatically on schema/test failure).
4. **BUDGET** — `guard.sh budget` → PSI + free RAM + disk avail (same MemGuard
   signals the round engine uses). Called at session start and pre-build.

Snapshots are cheap: we only tar `src/ + tools/ + package files`, not the
70GB home. Manifests are SHA-256 chained (same ledger trick as
`~/RootBase/canon_guard.jsonl`).

```
                                                          ┌─ schema fail ──▶ rollback + EXIT 75
commit intent ──▶ snap ──▶ recompile/validate ──▶ budget ──┤
                                                          └─ tests fail ──▶ rollback + EXIT 1
```

