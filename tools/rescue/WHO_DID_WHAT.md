# WHO_DID_WHAT — tools/rescue

| Date | Actor | Files | Action | Status |
|---|---|---|---|---|
| 2026-09-11 | Buffy (Codebuff) | `tools/rescue/a9_rescue.sh` | Emergency P0 kit: ADB→MTP→termux-tar fallback, 4 zones (termux_home/sdcard_root_2026/sdcard_r26/internal_RootBase), SD volume scan (/storage/<ID>/), SHA-256 manifests + integrity | committed 16e15e2 |
| 2026-09-11 | Buffy | `tools/rescue/drift_reconcile.py` | Reconciles prior intake (447/16MB, excluded .git/.env/.vault, r26=0) vs live Chromebook RootBase (584/39MB); verdict P0 + 446 prior-only suffix drift | committed 16e15e2 |
| 2026-09-11 | Buffy | `~/A9_RESCUE_PLAN.md` + `~/MRD_A9_RESCUE.md` + `tools/rescue/A9_RESCUE_PLAN.md` | Plain-English 2-page plan + meatsuit tick-box checklist; one `tar` inside Termux is the ONLY save for /data/data | committed 16e15e2 |
| 2026-09-11 | Buffy | `tools/rescue/QRD.md` + `tools/rescue/README.md` | Model→model gotchas (is_dir glob, SD volume IDs, MTP blind spots, fixtures_invalid) | committed 16e15e2 |
