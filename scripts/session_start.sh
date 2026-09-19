#!/usr/bin/env bash
# session_start.sh — one-command grounding for any agent (or human) opening
# this workspace. Force multiplier: the whole handoff protocol (ledger,
# tests, health, bus, lockout) in ~5 seconds, so no agent ever starts from
# vibes. Idempotent and read-only.
set -uo pipefail
cd "$(dirname "$0")/.."

echo "═══ SESSION START $(date -u +%Y-%m-%dT%H:%MZ) ═══"

echo "── 1. Handoff ledger ──"
if [ -f SESSION_HANDOFF.md ]; then
  grep -n "^## Entry" SESSION_HANDOFF.md | tail -3
  echo "   (read SESSION_HANDOFF.md before touching anything)"
else
  echo "   ⚠ no ledger found — you may be the first"
fi

echo "── 2. Whorl suite ──"
SUITE_OK=0
if (cd Whorl && python3 -m unittest discover -s tests 2>&1 | tail -1) | grep -q "^OK"; then
  SUITE_OK=1
  echo "OK"
else
  echo "FAILING — fix the weave before adding threads"
fi

# 🪢 the knot (an Easter egg earns its place by being true):
# green suite = every fiber woven, nothing unraveling.
if [ "$SUITE_OK" = "1" ]; then
  cat <<'KNOT'
     ╭───────╮
     │ ·  ◯  │   the weave holds
     │  ╲│╱  │   (suite green — every fiber knotted)
     ╰───────╯
KNOT
fi

echo "── 3. Whorl git state ──"
git -C Whorl log --oneline -1 2>/dev/null
git -C Whorl status --short 2>/dev/null | grep -cv "^??" | xargs -I{} echo "   {} tracked files modified"

echo "── 4. System health ──"
(cd Whorl && PYTHONPATH=. python3 -c "
import sys
sys.argv = ['whorl', 'health']
from whorl.cli import main
try: main()
except SystemExit: pass
" 2>/dev/null | head -8)

echo "── 5. Coordination bus ──"
python3 scripts/agent_state.py show 2>/dev/null | python3 -c "
import json, sys
try:
    s = json.load(sys.stdin)
    live = len(s.get('claims', {}))
    print(f'   {live} active claim(s), {len(s.get(\"completions\", []))} recent completion(s)')
except Exception:
    print('   bus empty or unreadable')
"

echo "── 6. Protected state ──"
[ -f FISH-VAG-SOS/DELETION_LOCKOUT.md ] && echo "   🔒 deletion lockout ACTIVE (45 projects)"
[ -f FISH-VAG-SOS/DISCARD_MANIFEST.md ] && echo "   📋 56 discard candidates PENDING approval"

echo "═══ Grounded. Verify before trusting; append when leaving. ═══"
