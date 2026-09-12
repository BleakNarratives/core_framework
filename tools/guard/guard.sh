#!/bin/bash
# guard.sh — worktree snapshot + rollback + budget (worktree complement to ~/RootBase/canon_guard.py)
set -euo pipefail
GUARD_DIR="$(cd "$(dirname "$0")" && pwd)"
SNAP_DIR="$GUARD_DIR/snapshots"
LEDGER="$GUARD_DIR/guard.jsonl"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME")"
# Only snapshot what we ship (not the 70GB home)
SNAP_GLOBS=("src" "tools" "package.json" "package-lock.json" ".gitignore")

mkdir -p "$SNAP_DIR"

snap() {
  local label="${1:-snap-$(date +%Y%m%d_%H%M%S)}"
  local id; id="$(date +%Y%m%d_%H%M%S)_$(echo -n "$label" | tr -cs 'a-zA-Z0-9' '_')"
  local snap_path="$SNAP_DIR/${id}.tar.gz"
  local manifest="$SNAP_DIR/${id}.json"
  # Staged content hash (what WOULD be committed)
  local staged_sha
  staged_sha=$(git diff --cached --name-only 2>/dev/null | sort | tr '\n' ' ' | sha256sum | cut -d' ' -f1)
  if [[ -z "$staged_sha" ]] || [[ "$staged_sha" == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  # SHA256 of empty string — not a secret" ]]; then
    # no staged — hash working tree instead
    staged_sha=$(find src tools -type f 2>/dev/null | sort | xargs sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1)
  fi
  # Create tar of ship surface only
  tar czf "$snap_path" -C "$REPO_ROOT" --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' \
    "${SNAP_GLOBS[@]}" 2>/dev/null || tar czf "$snap_path" -C "$REPO_ROOT" src tools 2>/dev/null || true
  local tar_sha; tar_sha=$(sha256sum "$snap_path" 2>/dev/null | cut -d' ' -f1 || echo "no-tar")
  local prior; prior=$(tail -n1 "$LEDGER" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('sha256','0'*64))" 2>/dev/null || echo "0"*64)
  # chain: each entry hashes prior + staged_sha
  local chain_sha; chain_sha=$(echo -n "${prior}${staged_sha}${tar_sha}" | sha256sum | cut -d' ' -f1)
  python3 -c "
import json, datetime
e={'ts': datetime.datetime.now().astimezone().isoformat(), 'id': '$id', 'label': '$label', 'staged_sha': '$staged_sha', 'tar_sha': '$tar_sha', 'tar': '$snap_path', 'manifest': '$manifest', 'sha256': '$chain_sha', 'prior': '$prior'}
open('$LEDGER','a').write(json.dumps(e)+'\n')
json.dump(e, open('$manifest','w'), indent=2)
print('[guard:snap] ' + '$id' + '  staged=' + '$staged_sha'[:12] + '  tar=' + '$tar_sha'[:12] + '  chain=' + '$chain_sha'[:12])
print('[guard:snap] tar: $snap_path  manifest: $manifest')
"
}

verify() {
  if [[ ! -f "$LEDGER" ]] || [[ ! -s "$LEDGER" ]]; then echo "[guard:verify] no snapshots yet — run guard.sh snap first"; return 1; fi
  local last; last=$(tail -n1 "$LEDGER")
  local last_id; last_id=$(echo "$last" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  local last_manifest="$SNAP_DIR/${last_id}.json"
  if [[ ! -f "$last_manifest" ]]; then echo "[guard:verify] missing manifest for $last_id"; return 2; fi
  local expected_staged; expected_staged=$(python3 -c "import json; print(json.load(open('$last_manifest'))['staged_sha'])")
  local current_staged; current_staged=$(git diff --cached --name-only 2>/dev/null | sort | tr '\n' ' ' | sha256sum | cut -d' ' -f1)
  if [[ -z "$current_staged" ]]; then current_staged=$(find src tools -type f 2>/dev/null | sort | xargs sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1); fi
  echo "[guard:verify] snapshot $last_id"
  echo "[guard:verify]   expected staged: $expected_staged"
  echo "[guard:verify]   current  staged: $current_staged"
  if [[ "$expected_staged" == "$current_staged" ]]; then echo "[guard:verify] CLEAN — no drift"; return 0; else echo "[guard:verify] DRIFT — working tree moved since snap"; return 1; fi
}

rollback() {
  local id="${1:-}"
  if [[ -z "$id" ]]; then echo "usage: guard.sh rollback <id>"; echo "snapshots:"; ls -1 "$SNAP_DIR"/*.json 2>/dev/null | sed 's|.*/||;s|\.json||' || echo "  (none)"; return 1; fi
  local tar="$SNAP_DIR/${id}.tar.gz"
  if [[ ! -f "$tar" ]]; then echo "[guard:rollback] no such snapshot: $id"; ls -1 "$SNAP_DIR"/*.tar.gz 2>/dev/null | head; return 1; fi
  echo "[guard:rollback] restoring $id from $tar"
  # Safety: extract into repo root, overwriting only the ship globs — never touch home noise
  tar xzf "$tar" -C "$REPO_ROOT" 2>&1 | head -n 20
  echo "[guard:rollback] done — verify with: git status"
}

budget() {
  echo "[guard:budget] $(date)"
  # PSI (same signals MemGuard uses: cpu/io/mem stall)
  if [[ -f /proc/pressure/memory ]]; then cat /proc/pressure/memory | head -n 5 | sed 's/^/  mem PSI: /'; fi
  if [[ -f /proc/pressure/io ]]; then cat /proc/pressure/io | head -n 3 | sed 's/^/  io  PSI: /'; fi
  free -h 2>/dev/null | head -n 3 | sed 's/^/  /'
  df -h "$HOME" 2>/dev/null | head -n 2 | sed 's/^/  disk: /'
  # Verdict
  local free_mb; free_mb=$(free -m 2>/dev/null | awk '/Mem:/{print $7}')
  local avail_gb; avail_gb=$(df -k "$HOME" 2>/dev/null | awk 'NR==2{print $4/1024/1024}')
  if (( free_mb < 400 )); then echo "[guard:budget] WARN — free RAM ${free_mb}MB < 400MB (large Node/Rust builds will OOM)"; fi
  # shellcheck disable=SC2072
  if (( $(echo "$avail_gb < 2" | bc -l 2>/dev/null || echo 0) )); then echo "[guard:budget] WARN — disk ${avail_gb}G < 2G"; fi
  echo "[guard:budget] ok"
}

case "${1:-help}" in
  snap) snap "${2:-}" ;;
  verify) verify ;;
  rollback) rollback "${2:-}" ;;
  budget) budget ;;
  status) echo "=== Guard status ==="; ls -lh "$SNAP_DIR" 2>/dev/null | head -n 20; echo "---"; cat "$LEDGER" 2>/dev/null | tail -n 10 | python3 -m json.tool 2>/dev/null || cat "$LEDGER" 2>/dev/null | tail -n 10; echo "---"; budget ;;
  *) echo "usage: guard.sh {snap [label]|verify|rollback <id>|budget|status}"; exit 1 ;;
esac
