#!/bin/bash
set -u

SCRIPT="$(dirname "$0")/../bin/master_control.sh"

if sed 's/[[:space:]]*#.*$//' "$SCRIPT" | grep -Eq '(^|[[:space:]])(pkill|killall)([[:space:]]|$)|pkill[[:space:]]+-f'; then
    echo "FAIL: unsafe pattern-kill command remains"
    exit 1
fi

grep -q 'DRY_RUN=0' "$SCRIPT" || { echo "FAIL: dry-run state missing"; exit 1; }
grep -q 'legacy_pid' "$SCRIPT" || { echo "FAIL: PID-scoped legacy guard missing"; exit 1; }
grep -q 'systemctl --user' "$SCRIPT" || { echo "FAIL: unit-aware systemd path missing"; exit 1; }

echo "master_control static safety audit: PASS"
