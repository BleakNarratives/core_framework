> **START HERE: `~/A9_RESCUE_PLAN.md`** — the 2-minute human plan. `~/MRD_A9_RESCUE.md` is the tick-box checklist.

# A9 Emergency Rescue — `tools/rescue/`

**If you are losing access to the Samsung A9, run this NOW.**

The 2026-08-21 intake got only 447 files (16MB) over MTP and deliberately
excluded `.git/.env/.vault` and could not see Termux home at all. Your A9 holds
a quarter-year of primary-device work in three places that intake missed:

- `~` inside Termux = `/data/data/com.termux/files/home` (invisible over MTP)
- SD card `/root_2026`
- SD card `/r26`

This kit pulls all three plus `RootBase` in one command, hashes everything, and
writes `INTAKE_MANIFEST.json` + `INTEGRITY_CHECK.json` so you can prove the
capture later.

## 10-second start

```bash
./tools/rescue/a9_rescue.sh --check      # do I have space + device?
./tools/rescue/a9_rescue.sh --dry-run    # what would it pull?
./tools/rescue/a9_rescue.sh              # DO IT (plug A9, share to Linux)
```

## If the A9 is not rooted (most common)

ADB cannot `pull /data/data/com.termux/files/home` without root. Run INSIDE
Termux on the A9 itself before you lose it:

```bash
tar -czf /sdcard/termux_home_$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home 2>/dev/null
termux-info > /sdcard/termux_info.txt 2>&1; env > /sdcard/termux_env.txt 2>&1
ls -la /sdcard/root_2026 /sdcard/r26 /storage/*/root_2026 /storage/*/r26 2>&1 > /sdcard/sd_inventory.txt
```

Then re-run `a9_rescue.sh` — it sweeps `/sdcard/termux_home_*.tar.gz` over MTP.

## What lands where

`~/RESCUE_A9_20260911_HHMM/` contains:

- `termux_home/` or `termux_home_*.tar.gz` — full Termux home
- `sdcard_root_2026/` — SD /root_2026
- `sdcard_r26/` — SD /r26
- `internal_RootBase/` — Internal storage/RootBase
- `mtp_*/` — raw MTP copies (for dedup later)
- `INTAKE_MANIFEST.json` / `INTEGRITY_CHECK.json` / `RESCUE_REPORT.md` / `rescue.log`

## Push to Drive as backup

```bash
rclone copy ~/RESCUE_A9_20260911_HHMM cloud:RESCUE_A9 --progress
./tools/rescue/a9_rescue.sh --rclone cloud:
```

## Prove drift

```bash
python3 tools/rescue/drift_reconcile.py
cat ~/RESCUE_A9_DRIFT_REPORT.md
```

## Files

- `a9_rescue.sh` — the pull (ADB → MTP → on-device tar fallback, SHA-256 manifests)
- `drift_reconcile.py` — reconciles prior intake vs live Chromebook (uses `fleet_telemetry/scanner.py`)
- `README.md` — this file
