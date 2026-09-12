# ROADMAP — Worktree (src + tools)
# Home repo `feature/ribbon-animation` — the ship, not the museum.
# Museum lives in RootBase/NAT-Recovery-Kernel/etc (70GB) and is NOT tracked here.

## P0 — Rescue (A9 imminent loss)

- [x] 2026-09-11 — `.gitignore = *` fixed (venv nuked home repo; no file could be added)
- [x] 2026-09-11 — `tools/rescue/a9_rescue.sh` P0 kit: ADB+MTP+termux-tar fallback, 4 zones, SHA-256 manifests
- [x] 2026-09-11 — `tools/rescue/drift_reconcile.py` — prior intake (447 files/16MB, MTP-only, excluded .git/.env/.vault) vs Chromebook RootBase drift
- [ ] **MEATSUIT REQUIRED**: on A9 inside Termux BEFORE you lose it:
      `tar -czf /sdcard/termux_home_$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home`
      then on Chromebook: `./tools/rescue/a9_rescue.sh` (plug A9, Files → Share with Linux)
- [ ] **VERIFY**: `cat ~/RESCUE_DRIFT_REPORT.md` must say rescue closed the 446 prior-only gap
- [ ] **BACKUP**: `rclone copy ~/RESCUE_A9_* cloud:RESCUE_A9 --progress` (both remotes: cloud: + faggot:)

Gap proof (drift_reconcile latest):
- Prior intake: 447 files / 16.7 MB — .git/.env/.vault EXCLUDED, r26=0, termux=2, root_2026=204 (partial)
- Live Chromebook RootBase: 584 files / 39.4 MB
- Verdict: PRIOR INTAKE WAS PARTIAL — rescue required (P0) — 446 A9-unique suffixes missing on Chromebook

## P1 — Guard (so one bad build doesn't brick the bus)

- [x] 2026-09-11 — `tools/guard/guard.sh` — snap/verify/rollback + budget (PSI/disk/RAM), SHA-256 chained ledger, mirrors `~/RootBase/canon_guard.py`
- [x] 2026-09-11 — `tools/guard/README.md` + `guard.sh snap/verify/rollback/budget/status`
- [ ] Wire `guard.sh snap` into every `recompile` entrypoint (pre-build snap, verify post-build, rollback on exit≠0)

## P1 — Harden (before any push)

- [x] 2026-09-11 — `tools/boundary/airlock.py` 27 rules: critical scan CLEAN (0 files leak), medium hit is only the well-known empty-SHA constant
- [x] 2026-09-11 — `tools/introspection/ariadne.py` zones warm: canon=30,357 files — the only ship surface
- [ ] Re-run `airlock scan --index --min-tier critical` before every push (GH protection already blocked 3 live secrets once)

## P1 — Ribbon (zero-dep, spec-bound)

- [x] 2026-09-11 — `src/ui/ribbon/` — ribbon.v1 spec (CSS fallback + JS progressive enhancement), fixtures, validator, demo
- [x] 2026-09-11 — Validator: bundle + 3 fixtures PASS, fixtures_invalid/empty.json FAIL proves the guard trips, analysis_report.json companion-only
- [ ] Recompile entrypoint that maps natural-language commit intent → AST diff and validates against ribbon.spec.v1 (see `src/ui/ribbon/spec.schema.json`)

## Next session

1. Run the meatsuit line above with the A9 in hand (5 min), then `drift_reconcile.py` — that one tar saves the quarter.
2. With rescue closed, recompile + snapshot the home repo commit cleanly and open the MR.

**Human plan:** `~/A9_RESCUE_PLAN.md` (plain-English, 2 pages) — `~/MRD_A9_RESCUE.md` is the hands-only checklist.
