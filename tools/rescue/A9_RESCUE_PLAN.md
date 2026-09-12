# A9 Rescue Plan — Read This First
# You lose access to the Samsung A9 soon. It holds a quarter of this
# year's primary-device work. This is the ONLY plan that can save it.

## Why this is red-alert (in plain English)

On 2026-08-21 we did a careful copy of the A9. It got 447 files (16 MB) over
USB file-transfer. It had to skip three places that matter:

1. Your Termux home folder (`/data/data/com.termux/files/home` — your `~` inside Termux)
   — invisible over normal USB file transfer, almost never reachable over developer cable
2. The SD card folder `/r26` — never walked
3. The SD card folder `/root_2026` — only partly walked

We also skipped `.git` and secret folders on purpose that day. So your quarter-year
of real work was not actually copied.

This plan fixes all four holes. One command captures all four places, hashes
every file so you can prove it later, and optionally backs up to Drive.

## What you will do (your hands, 2 minutes)

### Option A — You still have the A9 (BEST)

**On the A9 itself**, open Termux (the black terminal app) and paste this ONE line:

```
tar -czf /sdcard/termux_home_$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home
```

Then check it worked:
```
ls -lh /sdcard/termux_home_*.tar.gz
```
You should see a new `.tar.gz` file, probably tens or hundreds of MB. That
single file IS your Termux home saved. Nothing else can do it — not a USB copy,
not a cloud sync. Make that file while you still can.

That one line buys you the whole quarter. Do it today.

### Then on the Chromebook (plug the A9 in)

Plug the A9 into the Chromebook with USB. On the Chromebook, share it to Linux:

- Open the Files app → find the A9 on the left → right-click → "Share with Linux"

Then in the Chromebook terminal:

```
./tools/rescue/a9_rescue.sh --check
```

That says whether the cable + sharing actually worked, how much disk you have,
and what we already know about the gaps.

If it says the device is visible:

```
./tools/rescue/a9_rescue.sh
```

That pulls the four places that were missed, through whatever cable works
(developer ADB if allowed, otherwise normal USB file-transfer, plus it digs
through SD card volume folders like `SD card/` and `XXXX-XXXX/` automatically).

Then verify:

```
python3 tools/rescue/drift_reconcile.py
cat ~/RESCUE_DRIFT_REPORT.md
```

You want the Verdict to stop saying `PRIOR INTAKE WAS PARTIAL — rescue required (P0)`
and the `prior_only` number to drop from ~446.

Optional backup to Drive (we have two Drive accounts — either works):

```
rclone copy ~/RESCUE_A9_* cloud:RESCUE_A9 --progress
rclone copy ~/RESCUE_A9_* faggot:RESCUE_A9 --progress
```

### Option B — You already lost the A9 but you made the tar above first

You are still okay. The tar on `/sdcard/` is visible over normal USB file transfer,
unlike the Termux folder itself. Plug the A9 in one last time and the script will
sweep `/sdcard/termux_home_*.tar.gz` automatically.

### Option C — You lost the A9 without the tar

The Termux home folder is gone. MTP and ADB cannot go back in time. We will
save whatever USB could see (`/root_2026`, `/r26`, `RootBase`), document what
was lost in the rescue log, and not pretend we got it.

## Where to find everything

- `~/A9_RESCUE_PLAN.md` — this file (short, human)
- `~/MRD_A9_RESCUE.md` — the meatsuit checklist (hands-only steps, tick boxes)
- `~/RESCUE_DRIFT_REPORT.md` (after you run reconcile) — what the old copy missed vs what we have now on the Chromebook
- `~/RESCUE_A9_YYYYMMDD_HHMM/` — the actual rescue (four zone folders + `INTAKE_MANIFEST.json` + `INTEGRITY_CHECK.json` + `RESCUE_REPORT.md` + `rescue.log`)
- `tools/rescue/a9_rescue.sh` — the robot that pulls
- `tools/rescue/drift_reconcile.py` — the robot that proves gaps
- `tools/rescue/QRD.md` — the quick rundown for the next model
- `tools/rescue/README.md` — technical how-it-works

## How the robot works (one sentence per zone)

- **Termux home** — only the on-device tar above can reliably get it; direct developer cable is tried first but usually blocked
- **SD /root_2026** — developer cable plus normal USB, scanning both `/sdcard/` and `/storage/XXXX-XXXX/` volume IDs
- **SD /r26** — same as above
- **Internal RootBase** — `Internal storage/RootBase` over normal USB file transfer

Everything is hashed with SHA-256 in `INTAKE_MANIFEST.json` and double-checked in `INTEGRITY_CHECK.json` (`pass` = no unreadable files).

## Two scripts, three commands you need

```
./tools/rescue/a9_rescue.sh --check          # are we plugged in + enough space?
./tools/rescue/a9_rescue.sh --dry-run        # what would it pull (no write)
./tools/rescue/a9_rescue.sh                  # pull all four zones + write hashes
python3 tools/rescue/drift_reconcile.py      # prove the gap closed
```

That is the whole plan. Start with the one `tar` line on the A9.

---
Written 2026-09-11 on `feature/ribbon-animation` alongside Guard + Hardened + Ribbon.
The plan and the rescue code share the same commit so you can recover the instructions
even if you lose everything else — `git show` brings them back.
