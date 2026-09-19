#!/bin/bash
# a9_rescue.sh — Emergency A9 capture before access loss
#
# P0: Pull everything that was MISSED in the 2026-08-21 intake (which only got
# 447 files / 16MB via jmtpfs -o ro and EXCLUDED .git/.env/.vault + never saw
# Termux home or SD card partitions).
#
# Targets (per operator 2026-09-11):
#   1. Termux home      → /data/data/com.termux/files/home  (a.k.a. ~ inside Termux)
#      NOT visible over MTP — requires ADB or on-device tar to /sdcard first.
#   2. SD /root_2026     → /storage/<ID>/root_2026  or  /sdcard/root_2026
#   3. SD /r26           → /storage/<ID>/r26        or  /sdcard/r26
#   4. RootBase (internal) → /sdcard/RootBase  /storage/emulated/0/RootBase
#      (Internal storage/RootBase in MTP parlance)
#
# Transports (auto-detected, tried in order):
#   ADB  → captures Termux + SD even when MTP is blind (needs USB + authorize)
#   MTP  → jmtpfs / simple-mtpfs at ~/mnt/mtp (captures sdcard + internal only)
#   TERMUX_TAR → on-device fallback: user runs tar inside Termux itself
#
# Output: ~/RESCUE_A9_YYYYMMDD_HHMM/  with SHA-256 manifests + integrity check
#
# Usage:
#   ./tools/rescue/a9_rescue.sh              # full rescue (auto-detect)
#   ./tools/rescue/a9_rescue.sh --dry-run    # explain what WOULD run
#   ./tools/rescue/a9_rescue.sh --check      # device + disk preflight only
#   ./tools/rescue/a9_rescue.sh --mtp-only   # skip ADB, only MTP pull
#   ./tools/rescue/a9_rescue.sh --manifest-only  # (re)hash existing RESCUE dir
#   ./tools/rescue/a9_rescue.sh --rclone cloud:  # also push to rclone remote
#
# DNA_TAG: ORIGIN=BleakNarratives/RootBase | ROLE=a9-rescue | TIER=P0
# LAST_SYNC: 2026-09-11

set -euo pipefail

# ── config ──
RESCUE_PARENT="$HOME"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RESCUE_DIR="${RESCUE_DIR:-$RESCUE_PARENT/RESCUE_A9_$TIMESTAMP}"
MTP_MOUNT="${MTP_MOUNT:-$HOME/mnt/mtp}"
LOG_FILE="$RESCUE_DIR/rescue.log"
MANIFEST="$RESCUE_DIR/INTAKE_MANIFEST.json"
INTEGRITY="$RESCUE_DIR/INTEGRITY_CHECK.json"
REPORT="$RESCUE_DIR/RESCUE_REPORT.md"

DRY_RUN=0
MTP_ONLY=0
MANIFEST_ONLY=0
RCLONE_REMOTE=""
CHECK_ONLY=0

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; CYN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GRN}[rescue]${NC} $*" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "${GRN}[rescue]${NC} $*"; }
warn() { echo -e "${YEL}[rescue]${NC} $*" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "${YEL}[rescue]${NC} $*"; }
err()  { echo -e "${RED}[rescue]${NC} $*" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "${RED}[rescue]${NC} $*"; }
info() { echo -e "${CYN}[rescue]${NC} $*" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "${CYN}[rescue]${NC} $*"; }

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --mtp-only) MTP_ONLY=1 ;;
    --manifest-only) MANIFEST_ONLY=1 ;;
    --check) CHECK_ONLY=1 ;;
    --rclone) RCLONE_REMOTE="__NEXT__" ;;
    *) if [[ "${RCLONE_REMOTE:-}" == "__NEXT__" ]]; then RCLONE_REMOTE="$arg"; else
         [[ "$arg" == --rclone* ]] && RCLONE_REMOTE="${arg#--rclone=}"
       fi ;;
  esac
  # handle --rclone cloud: (value as next arg)
  if [[ "$arg" == "--rclone" ]]; then RCLONE_REMOTE="__NEXT__"; fi
done
# Normalize rclone remote if passed as --rclone=cloud:
if [[ "${RCLONE_REMOTE:-}" == "__NEXT__" ]]; then RCLONE_REMOTE=""; fi

mkdir -p "$RESCUE_DIR"
touch "$LOG_FILE"

usage() {
  sed -n '2,40p' "$0" | sed 's/^# \?//'
}

# ── helpers ──
disk_ok() {
  local avail_kb avail_gb
  avail_kb=$(df -k "$HOME" | awk 'NR==2{print $4}')
  avail_gb=$((avail_kb/1024/1024))
  echo "$avail_gb"
}

have() { command -v "$1" &>/dev/null; }

adb_state() {
  if have adb; then
    adb devices 2>&1 | awk 'NR>1 && NF>=2{print $1, $2}' | head -n 20
  else
    echo "(adb not installed)"
  fi
}

mtp_state() {
  if have jmtpfs || have simple-mtpfs; then
    if mountpoint -q "$MTP_MOUNT" 2>/dev/null; then echo "mounted at $MTP_MOUNT"
    else echo "not mounted (run: jmtpfs $MTP_MOUNT)"
    fi
    if have mtp-detect; then timeout 5 mtp-detect 2>&1 | head -n 5 || true; fi
  else
    echo "(jmtpfs not installed)"
  fi
}

lsusb_a9() { lsusb 2>&1 | grep -vi "Linux Foundation\|root hub" | head -n 20 || true; }

# ── preflight ──
do_preflight() {
  log "=== A9 RESCUE PREFLIGHT  $TIMESTAMP ==="
  log "Rescue dir: $RESCUE_DIR"
  log ""

  local gb
  gb=$(disk_ok)
  if (( gb < 2 )); then err "LOW DISK: ${gb}G free — free space before pulling! (need ~5-10G headroom)"; else log "Disk free: ${gb}G "; fi

  log ""
  info "USB (lsusb, shared into Crostini):"
  local usb
  usb=$(lsusb_a9)
  if [[ -z "$usb" ]]; then warn "  (none visible — share device to Linux: ChromeOS Files → right-click device → Share with Linux)"; else echo "$usb" | sed 's/^/  /' | tee -a "$LOG_FILE"; fi

  log ""
  info "ADB:"
  adb_state | sed 's/^/  /' | tee -a "$LOG_FILE"

  log ""
  info "MTP:"
  mtp_state | sed 's/^/  /' | tee -a "$LOG_FILE"

  log ""
  info "Prior intake (2026-08-21):"
  if [[ -f "$HOME/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/INTAKE_MANIFEST.json" ]]; then
    python3 -c "
import json,pathlib
m=json.load(open('$HOME/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001/INTAKE_MANIFEST.json'))
print(f\"  files={m['file_count']}  bytes={m['total_bytes']/1e6:.1f}MB  via={m['connection_mode']}\")
print(f\"  excluded={m['excluded']}\")
# gap analysis
paths=set(f['relative_path'] for f in m['files'])
for k in ['root_2026','r26','com.termux','data/data','sdcard']:
    n=sum(1 for p in paths if k.lower() in p.lower())
    print(f\"  {k}: {n} hits (in prior intake)\")
" | tee -a "$LOG_FILE"
  else
    warn "  (no prior intake manifest found)"
  fi

  log ""
  warn "KNOWN GAPS in prior intake (WHY this rescue is P0):"
  warn "  • Termux home (/data/data/com.termux/files/home): 0 files — MTP is blind to it"
  warn "  • /r26 on SD: 0 files — never scanned"
  warn "  • /root_2026 on SD: only 204 of its tree was seen (ModMind subset), SD partitions not walked"
  warn "  • .git / .env / .vault: deliberately EXCLUDED (your quarterly work holds real config)"

  log ""
  info "What this rescue WILL capture (4 zones):"
  info "  1. termux_home/      — via ADB (or on-device tar fallback)"
  info "  2. sdcard_root_2026/ — via ADB + MTP"
  info "  3. sdcard_r26/       — via ADB + MTP"
  info "  4. internal_RootBase/— via ADB + MTP"

  log ""
  if (( DRY_RUN )); then warn "DRY RUN — no pull executed. Re-run without --dry-run to capture."; fi

  if have rclone && rclone listremotes 2>&1 | grep -q .; then
    log "rclone remotes:"
    rclone listremotes 2>&1 | sed 's/^/  /' | tee -a "$LOG_FILE"
  fi
}

# ── install adb if missing ──
ensure_adb() {
  if have adb; then return 0; fi
  warn "adb not found — installing android-tools-adb..."
  if (( DRY_RUN )); then log "[dry-run] sudo apt-get install -y android-tools-adb"; return 0; fi
  sudo apt-get update -qq && sudo apt-get install -y android-tools-adb 2>&1 | tail -n 10 | tee -a "$LOG_FILE" || warn "adb install failed — MTP fallback only"
}

# ── ADB captures ──
adb_pull() {
  local src="$1" dst="$2" label="$3"
  mkdir -p "$dst"
  log "ADB pull  $label  ::  $src  →  $dst"
  if (( DRY_RUN )); then log "[dry-run] adb pull \"$src\" \"$dst\""; return 0; fi
  if ! have adb; then warn "  skip — no adb"; return 1; fi
  # check device is there
  if ! adb devices 2>&1 | grep -q "device$"; then warn "  no authorized ADB device — skip (authorize on phone: allow USB debugging)"; return 1; fi
  # list-first probe
  if ! adb shell ls -d "$src" 2>&1 | grep -qv "No such"; then warn "  source not found on device: $src"; return 1; fi
  # actual pull
  if adb pull "$src" "$dst" 2>&1 | tee -a "$LOG_FILE"; then log " $label pulled"; return 0; else warn " pull failed for $label"; return 1; fi
}

adb_pull_termux() {
  log "--- Zone 1: Termux home (/data/data/com.termux/files/home) ---"
  warn "  MTP cannot see this path. ADB is the only wire."
  local ok=0
  # Direct pull if device is rooted / adb has shell access
  adb_pull "/data/data/com.termux/files/home" "$RESCUE_DIR/termux_home" "termux_home(direct)" && ok=1
  if (( ok==0 )); then
    # Fallback probe: some builds expose Termux home via /data/data link
    adb_pull "/data/data/com.termux/files/usr" "$RESCUE_DIR/termux_usr" "termux_usr" || true
  fi
  if (( ok==0 )); then
    warn ""
    warn "  TERMUX_TAR FALLBACK (run ON the A9 inside Termux):"
    warn "    tar -czf /sdcard/termux_home_\$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home 2>/dev/null"
    warn "    # then pull via ADB/MTP:"
    warn "    adb pull /sdcard/termux_home_*.tar.gz $RESCUE_DIR/"
    warn "    # or: jmtpfs ~/mnt/mtp && cp ~/mnt/mtp/Internal\\ storage/termux_home_*.tar.gz $RESCUE_DIR/"
    warn ""
    warn "  If the A9 is not rooted and adb pull is blocked, the SD tar is the ONLY path."
    warn "  On the A9 Termux, also capture busybox env for evidence:"
    warn "    termux-info > /sdcard/termux_info.txt 2>&1; env > /sdcard/termux_env.txt 2>&1"
  fi
}

adb_pull_sd() {
  log "--- Zone 2+3: SD card /root_2026 and /r26 ---"
  for p in "/sdcard/root_2026" "/storage/emulated/0/root_2026" "/sdcard/r26" "/storage/emulated/0/r26"; do
    local base; base=$(basename "$p")
    adb_pull "$p" "$RESCUE_DIR/sdcard_$base" "sdcard/$base" || true
  done
  # SD card with volume ID (e.g. /storage/XXXX-XXXX/root_2026)
  if have adb && adb devices 2>&1 | grep -q "device$"; then
    log "  probing SD volumes..."
    if (( ! DRY_RUN )); then
      local vols
      vols=$(adb shell ls /storage 2>&1 | tr -d '\r' || true)
      echo "$vols" | tee -a "$LOG_FILE"
      while IFS= read -r vol; do
        vol=$(echo "$vol" | xargs)
        [[ -z "$vol" || "$vol" == "emulated" || "$vol" == "self" ]] && continue
        for sub in root_2026 r26 RootBase; do
          adb_pull "/storage/$vol/$sub" "$RESCUE_DIR/sdcard_${vol}_$sub" "sd_vol:$vol/$sub" || true
        done
      done <<< "$vols"
    fi
  fi
  log "--- Zone 4: RootBase (internal) ---"
  for p in "/sdcard/RootBase" "/storage/emulated/0/RootBase"; do
    adb_pull "$p" "$RESCUE_DIR/internal_RootBase" "internal/RootBase" && break || true
  done
}

# ── MTP captures ──
mtp_mount() {
  if mountpoint -q "$MTP_MOUNT" 2>/dev/null; then log "MTP already mounted at $MTP_MOUNT"; return 0; fi
  if ! have jmtpfs && ! have simple-mtpfs; then warn "no jmtpfs/simple-mtpfs"; return 1; fi
  mkdir -p "$MTP_MOUNT"
  if have jmtpfs; then
    log "Mounting MTP via jmtpfs..."
    if (( DRY_RUN )); then log "[dry-run] jmtpfs $MTP_MOUNT"; return 0; fi
    jmtpfs "$MTP_MOUNT" 2>&1 | tee -a "$LOG_FILE" || true
    sleep 2
    if mountpoint -q "$MTP_MOUNT" 2>/dev/null; then log "MTP mounted"; ls "$MTP_MOUNT" 2>&1 | head -n 20 | sed 's/^/  /' | tee -a "$LOG_FILE"; return 0; fi
  fi
  if have simple-mtpfs; then
    log "Retrying via simple-mtpfs..."
    if (( DRY_RUN )); then log "[dry-run] simple-mtpfs $MTP_MOUNT"; return 0; fi
    simple-mtpfs "$MTP_MOUNT" 2>&1 | tee -a "$LOG_FILE" || true
    sleep 2
    mountpoint -q "$MTP_MOUNT" 2>/dev/null && return 0 || true
  fi
  warn "MTP mount failed — share device to Linux first (Files → right-click → Share with Linux)"
  return 1
}

mtp_pull() {
  local src="$1" dst="$2" label="$3"
  if [[ ! -e "$src" && ! -d "$src" ]]; then warn "  MTP miss: $src (not on mount)"; return 1; fi
  mkdir -p "$dst"
  log "MTP copy  $label  ::  $src  →  $dst"
  if (( DRY_RUN )); then log "[dry-run] rsync -a \"$src/\" \"$dst/\""; return 0; fi
  # Use rsync if available (resume-safe), else cp -a
  if have rsync; then
    rsync -a --info=progress2 "$src/" "$dst/" 2>&1 | tee -a "$LOG_FILE" || cp -a "$src/." "$dst/" 2>&1 | tee -a "$LOG_FILE" || warn "  copy failed for $label"
  else
    cp -a "$src/." "$dst/" 2>&1 | tee -a "$LOG_FILE" || warn "  copy failed for $label"
  fi
  local n; n=$(find "$dst" -type f 2>/dev/null | wc -l)
  log "  → $n files in $dst"
}

mtp_pull_all() {
  log "--- MTP pull (sdcard + internal visible over MTP) ---"
  if ! mtp_mount; then warn "  MTP unavailable — ADB path only"; return 1; fi
  # Discover mount layout
  log "MTP layout:"
  ls -R "$MTP_MOUNT" 2>&1 | head -n 100 | sed 's/^/  /' | tee -a "$LOG_FILE" || true
  # Common MTP names: "Internal storage" / "Internal Storage" / "Phone" / "SD card"
  for base in "$MTP_MOUNT" "$MTP_MOUNT/Internal storage" "$MTP_MOUNT/Internal Storage" "$MTP_MOUNT/Phone" "$MTP_MOUNT/SD card" "$MTP_MOUNT/SD Card"; do
    [[ -d "$base" ]] || continue
    for sub in root_2026 r26 RootBase; do
      if [[ -e "$base/$sub" ]]; then mtp_pull "$base/$sub" "$RESCUE_DIR/mtp_$(basename "$base")_$sub" "mtp:$(basename "$base")/$sub" || true
      fi
      # probe case-variant without brace expansion that chokes bash -n
      upper=$(echo "$sub" | tr 'a-z' 'A-Z')
      for hit in "$base/$upper"*; do
        [ -e "$hit" ] || continue
        [ "$hit" = "$base/$sub" ] && continue
        mtp_pull "$hit" "$RESCUE_DIR/mtp_ci_$(basename "$hit")" "mtp:$(basename "$base")/$(basename "$hit")" || true
      done
    done
  done
  # Also pull any termux tar that user created on /sdcard per fallback
  for base in "$MTP_MOUNT" "$MTP_MOUNT/Internal storage" "$MTP_MOUNT/Internal Storage"; do
    [[ -d "$base" ]] || continue
    for pat in termux_info.txt termux_env.txt; do
      if [ -e "$base/$pat" ]; then mtp_pull "$base/$pat" "$RESCUE_DIR/" "mtp:fallback/$pat" || true; fi
    done
    for f in "$base"/termux_home_*.tar.gz; do
      [ -e "$f" ] || continue
      mtp_pull "$f" "$RESCUE_DIR/" "mtp:fallback/$(basename "$f")" || true
    done
  done
}

# ── manifest / integrity ──
build_manifest() {
  log "=== Building SHA-256 manifest ==="
  if (( DRY_RUN )); then log "[dry-run] python hash walk of $RESCUE_DIR"; return 0; fi
  python3 << PY | tee -a "$LOG_FILE"
import hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

root = Path("$RESCUE_DIR")
out_manifest = root / "INTAKE_MANIFEST.json"
out_integrity = root / "INTEGRITY_CHECK.json"

# Walk RESCUE_DIR excluding the manifest files themselves and rescue.log
files = []
for p in root.rglob("*"):
    if p.is_dir(): continue
    rel = str(p.relative_to(root))
    if rel in ("INTAKE_MANIFEST.json","INTEGRITY_CHECK.json","rescue.log","RESCUE_REPORT.md"):
        continue
    if rel.startswith("."): continue
    try:
        h = hashlib.sha256()
        with open(p,"rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        sha = h.hexdigest()
        size = p.stat().st_size
    except Exception as e:
        sha = f"UNREADABLE:{e}"
        try: size = p.stat().st_size
        except: size = 0
    files.append({"relative_path": rel, "size_bytes": size, "sha256": sha})

files.sort(key=lambda x: x["relative_path"])
total = sum(f["size_bytes"] for f in files if isinstance(f["size_bytes"],int))

manifest = {
    "manifest_version": "a9-rescue-1.0",
    "source_id": "source:samsung-a9",
    "source_label": "Samsung A9 — emergency rescue 2026-09-11",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "rescue_dir": str(root),
    "connection_modes": "ADB + MTP (auto)",
    "prior_intake": "2026-08-21-samsung-a9-001 (447 files, 16.7MB, MTP-only, excluded .git/.env/.vault)",
    "zones": ["termux_home","sdcard_root_2026","sdcard_r26","internal_RootBase","mtp_full"],
    "file_count": len(files),
    "total_bytes": total,
    "files": files,
}
with open(out_manifest,"w") as f:
    json.dump(manifest, f, indent=2)
print(f"[manifest] {len(files)} files, {total/1e6:.1f} MB → {out_manifest}")

# Integrity: verify no UNREADABLEs
bad = [f for f in files if f["sha256"].startswith("UNREADABLE")]
integrity = {
    "report_version": "a9-integrity-1.0",
    "source_id": "source:samsung-a9",
    "checked_files": len(files),
    "mismatch_count": len(bad),
    "status": "pass" if not bad else "fail",
    "mismatches": bad[:50],
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
with open(out_integrity,"w") as f:
    json.dump(integrity, f, indent=2)
print(f"[integrity] status={integrity['status']} checked={len(files)} mismatches={len(bad)} → {out_integrity}")

# Zone breakdown
from collections import Counter
zones = Counter(f["relative_path"].split("/")[0] for f in files)
print("[zones]")
for z,n in zones.most_common():
    zb = sum(f["size_bytes"] for f in files if f["relative_path"].startswith(z+"/") and isinstance(f["size_bytes"],int))
    print(f"  {z}: {n} files, {zb/1e6:.1f} MB")
PY
}

build_report() {
  if (( DRY_RUN )); then return 0; fi
  cat > "$REPORT" << RPT
# A9 Emergency Rescue — $(date -u +%Y-%m-%dT%H:%M:%SZ)

**Rescue dir:** \`$RESCUE_DIR\`
**Prior intake:** \`~/NAT-Recovery-Kernel/intake/2026-08-21-samsung-a9-001\` — 447 files / 16.7 MB, MTP-only, excluded .git/.env/.vault
**This rescue:** $(python3 -c "import json,pathlib; m=json.load(open('$MANIFEST')); print(f\"{m['file_count']} files / {m['total_bytes']/1e6:.1f} MB\")" 2>/dev/null || echo "(manifest pending)")
**Integrity:** $(python3 -c "import json; print(json.load(open('$INTEGRITY'))['status'])" 2>/dev/null || echo "pending")

## Zones captured

- \`termux_home/\` — /data/data/com.termux/files/home (requires ADB or on-device tar)
- \`sdcard_root_2026/\` — SD card /root_2026 (ADB + MTP)
- \`sdcard_r26/\` — SD card /r26 (ADB + MTP)
- \`internal_RootBase/\` — Internal storage/RootBase (ADB + MTP)
- \`mtp_*/\` — raw MTP copies (deduped by content hash later)

## Gaps closed vs 2026-08-21

Prior intake saw: root_2026=204 hits (partial ModMind), r26=0, com.termux=0, data/data=0.
This rescue explicitly hunts all four zones including Termux home and SD volumes.

## If device was not connected

1. On the A9, inside Termux, run:
   \`\`\`bash
   tar -czf /sdcard/termux_home_\$(date +%Y%m%d).tar.gz -C /data/data/com.termux/files home 2>/dev/null
   termux-info > /sdcard/termux_info.txt 2>&1; env > /sdcard/termux_env.txt 2>&1
   ls -la /sdcard/root_2026 /sdcard/r26 /storage/*/root_2026 /storage/*/r26 2>&1 > /sdcard/sd_inventory.txt
   \`\`\`
2. Then re-run this script — it will pick up \`/sdcard/termux_home_*.tar.gz\` over MTP.

## Backup to cloud (optional)

\`\`\`bash
rclone copy "$RESCUE_DIR" cloud:RESCUE_A9_$(basename "$RESCUE_DIR") --progress
rclone copy "$RESCUE_DIR" faggot:RESCUE_A9_$(basename "$RESCUE_DIR") --progress
\`\`\`

## Restore

\`\`\`bash
# Integrity check
python3 -c "import json; print(json.load(open('$INTEGRITY')))"
# Manifest
cat "$MANIFEST" | python3 -m json.tool | head -n 100
# Copy back to Chromebook canon
rsync -a "$RESCUE_DIR/termux_home/" ~/tmp_restore_termux/  # inspect first!
\`\`\`

---
Generated by \`tools/rescue/a9_rescue.sh\` — $(date)
Log: \`$LOG_FILE\`
Manifest: \`$MANIFEST\`
RPT
  log "Report → $REPORT"
  cat "$REPORT" | tee -a "$LOG_FILE"
}

push_rclone() {
  local remote="$1"
  [[ -z "$remote" ]] && return 0
  # Normalize trailing colon
  [[ "$remote" != *:* ]] && remote="${remote}:"
  local target="${remote}RESCUE_A9_$(basename "$RESCUE_DIR")"
  log "Pushing rescue to rclone → $target"
  if (( DRY_RUN )); then log "[dry-run] rclone copy \"$RESCUE_DIR\" \"$target\" --progress"; return 0; fi
  if ! have rclone; then warn "rclone not installed"; return 1; fi
  rclone copy "$RESCUE_DIR" "$target" --progress 2>&1 | tee -a "$LOG_FILE" || warn "rclone push failed"
  log "rclone push done → $target"
}

# ── main ──
main() {
  if (( MANIFEST_ONLY )); then build_manifest; build_report; exit 0; fi

  do_preflight
  if (( CHECK_ONLY )); then exit 0; fi

  log ""
  log "=== CAPTURE START ==="
  log "Rescue dir: $RESCUE_DIR"
  log ""

  ensure_adb || true

  if (( MTP_ONLY )); then
    warn "MTP-only mode — Termux home will be MISSED (needs ADB or on-device tar)"
  else
    adb_pull_termux || true
    adb_pull_sd || true
  fi
  mtp_pull_all || true

  log ""
  log "=== CAPTURE COMPLETE — building manifest ==="
  build_manifest
  build_report

  if [[ -n "${RCLONE_REMOTE:-}" && "$RCLONE_REMOTE" != "__NEXT__" ]]; then push_rclone "$RCLONE_REMOTE"; fi

  log ""
  log "=== DONE ==="
  log "Rescue dir: $RESCUE_DIR"
  log "Files: $(find "$RESCUE_DIR" -type f 2>/dev/null | wc -l)   Size: $(du -sh "$RESCUE_DIR" 2>/dev/null | cut -f1)"
  log "Next: cat $REPORT"
  log "Next: ls -R $RESCUE_DIR | head -n 100"
  log "Next (cloud): rclone copy $RESCUE_DIR cloud:RESCUE_A9_$(basename "$RESCUE_DIR") --progress"
}

main "$@"
