# MRD — A9 Rescue: What Mike MUST Do With His Hands
# The only step a model cannot do for you. No tar, no capture. Do this before access dies.

## 1 minute inside Termux ON THE A9 (do this NOW)

Open Termux on the A9. Run exactly:

```bash
tar -czf /sdcard/termux_home_$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home 2>/dev/null
termux-info > /sdcard/termux_info.txt 2>&1; env > /sdcard/termux_env.txt 2>&1
ls -la /sdcard/root_2026 /sdcard/r26 2>&1 > /sdcard/sd_inventory.txt
ls -la /storage/*/root_2026 /storage/*/r26 2>&1 >> /sdcard/sd_inventory.txt
echo DONE — check: ls -lh /sdcard/termux_home_*.tar.gz /sdcard/termux_info.txt
```

Why: `/data/data/com.termux/files/home` (your Termux `~`) is invisible over MTP and
blocked from ADB without root. The ONLY way to save the quarter-year of primary-device
work is to tar it to `/sdcard` while you still have Termux open.

## 2 minutes on the Chromebook (plug the A9 in)

On the Chromebook (this box):

```bash
# 1. Preflight — are we plugged + shareable + enough disk?
./tools/rescue/a9_rescue.sh --check

# 2. Full pull — ADB (if authorized) + MTP (Internal + SD volume scan)
./tools/rescue/a9_rescue.sh

# 3. Prove the gap closed
python3 tools/rescue/drift_reconcile.py
cat ~/RESCUE_DRIFT_REPORT.md

# 4. Backup to Drive (belt and suspenders — you have two remotes)
rclone copy ~/RESCUE_A9_* cloud:RESCUE_A9 --progress
rclone copy ~/RESCUE_A9_* faggot:RESCUE_A9 --progress
```

What lands: `~/RESCUE_A9_YYYYMMDD_HHMM/` with:
- `termux_home/` or `termux_home_*.tar.gz`  (your Termux ~ — the prize)
- `sdcard_root_2026/` / `sdcard_r26/` / `internal_RootBase/`
- `INTAKE_MANIFEST.json` + `INTEGRITY_CHECK.json` + `RESCUE_REPORT.md` + `rescue.log`

Verify with: `cat ~/RESCUE_A9_*/INTEGRITY_CHECK.json` — must say `pass`.

## If you skip the Termux tar

ADB cannot pull `/data/data/com.termux/files/home` without root, and MTP cannot see it
at all. You will lose every `.zshrc`, script, key, and note you wrote on the A9 as primary.

The prior intake (2026-08-21) deliberately excluded `.git/.env/.vault` (47, excluded
list in `~/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/INTAKE_MANIFEST.json`).
Re-running that intake cannot save you — only the rescue with the tar can.

## Checklist

- [ ] Ran `tar` inside A9 Termux (saw `termux_home_*.tar.gz` on /sdcard)
- [ ] Plugged A9 → Chromebook (Files → Share with Linux), ran `a9_rescue.sh`
- [ ] `RESCUE_DRIFT_REPORT.md` no longer says 446 prior-only
- [ ] `rclone copy` to `cloud:` AND `faggot:` both succeeded
- [ ] Delete NOTHING on the A9 until `INTEGRITY_CHECK.json` says pass
