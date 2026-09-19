# QRD — A9 Rescue + Drift Reconciler (Quick Rundown, model → model)

## What this is
Emergency kit that closes the hole in the 2026-08-21 MTP intake. That intake got
447 files / 16.7 MB from the Samsung A9 over `jmtpfs -o ro`, EXCLUDED `.git/.env/.vault`,
and never walked `/r26` or `/data/data/com.termux/files/home`. The operator's A9 holds
a quarter-year of primary-device work in 3 places MTP is blind to.

## Where things live
- PRIOR INTAKE: `~/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/` + `INTAKE_MANIFEST.json` + `INTEGRITY_CHECK.json` — read this first.
- RESCUE KIT: `tools/rescue/a9_rescue.sh` (ADB→MTP→termux-tar fallback, auto-detected, SHA-256 manifests + chained ledger mirror of canon_guard)
- DRIFT: `tools/rescue/drift_reconcile.py` → `~/RESCUE_DRIFT_REPORT.md|json` — SUFFIX overlap (last 2 path comps) because prior paths are `Internal storage/RootBase/...` vs live `RootBase/...`. 446 prior-only is the P0 signal.
- MEATSUIT: `~/MRD_A9_RESCUE.md` — the 1-line `tar` that must happen INSIDE Termux before access dies. No model can run it.
- OUTPUT: `~/RESCUE_A9_YYYYMMDD_HHMM/` — 4 zones + manifests. The drift report globs these as `RESCUE_A9_*`; grep is filtered to `is_dir()` so report files don't fake a rescue.

## Gotchas you will hit
1. `~/RESCUE_A9_*` glob WILL match `~/RESCUE_DRIFT_REPORT.*` if you forget `is_dir()`. Patched — keep it.
2. `a9_rescue.sh --check` creates `~/RESCUE_A9_$TIMESTAMP/rescue.log` even when no device is present. Clean test dirs after drills so drift doesn't think a rescue happened.
3. `r26` and `root_2026` live on SD volumes under `/storage/<ID>/` (e.g. `/storage/XXXX-XXXX/`), exposed as `SD card` over MTP — not `/sdcard/` directly. The script scans both.
4. Termux `~` is `/data/data/com.termux/files/home` — MTP blind, ADB usually permission-denied without root. The fallback is the on-device `tar -C /data/data/com.termux/files home` to `/sdcard/termux_home_*.tar.gz` then re-run MTP. Don't retry ADB 10 times — tell the operator to do the tar.
5. The validator's `fixtures/empty.json` is INTENTIONALLY invalid (ribons must be non-empty). It lives in `fixtures_invalid/` so `validate.py` stays green in CI while still proving the guard trips.
6. Guard snapshot only tars `src+tools+package.json+.gitignore` — not the 70GB home. Don't `tar -czf ~`.

## How to continue
- If A9 is still present: `a9_rescue.sh --check` → `--dry-run` → full run → `drift_reconcile.py` → `rclone copy`.
- If A9 is gone but `/sdcard/termux_home_*.tar.gz` is on Internal storage: MTP pull still works (the script sweeps `/sdcard/termux_home_*.tar.gz`).
- If A9 is gone with no tar: the Termux home is gone. Document that in `RESCUE_REPORT.md` and archive what you do have; don't pretend MTP would have caught it.

## What success looks like
`drift_reconcile.py` Verdict flips from `PRIOR INTAKE WAS PARTIAL — rescue required (P0)` to something else, `prior_only_suffix` drops from 446 toward 0, rescue dir has `INTAKE_MANIFEST.json` with `file_count` >> 447, `INTEGRITY_CHECK.json` is `pass`.

---

# QRD — Guard (worktree canon mirror)

`tools/guard/guard.sh` + `tools/guard/README.md` + `guard.jsonl` + `snapshots/*.tar.gz|.json`.
Mirrors `~/RootBase/canon_guard.py` pattern (SHA-256 chain, snapshot restore) but scoped to the worktree (`src+tools`).
Commands: `snap "label"` / `verify` / `rollback <id>` / `budget` (PSI/RAM/disk) / `status`.
Integrate into every `recompile` entrypoint: snap → build → verify → rollback on non-zero (75 for schema, 1 for test).
Snapshots must stay out of the busy loop — tar only the ship globs, never `~`.

---

# QRD — Ribbon (spec-bound animation)

`src/ui/ribbon/` — `spec.schema.json` + `ribbon.spec.json` (canonical bundle) + `ribbon.css` + `ribbon.js` + `validate.py` + `fixtures/` + `fixtures_invalid/` + `demo.html`.
Contract is `ribbon.v1` (hand-rolled validator, no `jsonschema` dep): duplicate ids, stroke `#RRGGBB`, width 0.5..32, ≥2 points, easing enum, opacity 0..1, `dash` numeric array, `closed` boolean, `direction` enum, `loop` boolean — all enforced. Malformed shapes are reported as errors, not raised, so failures always reach `analysis_report.json` (companion); the bundle is never touched.
`ribbon.css` is the fallback (`@keyframes ribbon-draw` + `prefers-reduced-motion`); `ribbon.js` upgrades to `getTotalLength()` → `--len/--dur/--easing` for exact loops. `demo.html` is file://-safe.
`fixtures/empty.json` is knowingly invalid in `fixtures_invalid/` — proves the guard trips.
