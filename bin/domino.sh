#!/usr/bin/env bash
# ============================================================================
#  domino.sh — flick one domino, run the whole scout machine.
#
#  Canonical location: core_framework/bin/domino.sh
#  Run it from the repo root as:  ./domino.sh
#
#  One shot (default):  ./domino.sh            # preflight + serve + patrol
#                                              # + broadcast + status
#  Stages (modular):    ./domino.sh preflight | serve | stop | restart
#                       ./domino.sh patrol | broadcast | plan | status
#                       ./domino.sh sprawl | skill | help
#
#  Safe by default: offline fixtures, localhost backend, no secrets, no network
#  unless you pass DOMINO_LIVE=1 (which needs SEC_USER_AGENT). Nothing here is
#  destructive; `stop` only kills the backend pid it started.
#
#  Knobs (env vars):
#    DOMINO_PORT=8765     backend port
#    DOMINO_HOST=127.0.0.1 backend host
#    DOMINO_PYTHON=python3 interpreter
#    DOMINO_QUERY="..."    adaptive query pattern
#    DOMINO_SERVE=0        skip starting the backend in `all`
# ============================================================================
set -euo pipefail

# --- resolve repo root (the dir containing core_framework) -------------------
_self="${BASH_SOURCE[0]}"
while [ -L "$_self" ]; do _self="$(readlink "$_self")"; done
SCRIPT_DIR="$(cd "$(dirname "$_self")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FW="$ROOT/core_framework"
OUT="$FW/output"
LOGS="$FW/logs"
RUN_DIR="$FW/.domino"
PIDFILE="$RUN_DIR/backend.pid"

PORT="${DOMINO_PORT:-8765}"
HOST="${DOMINO_HOST:-127.0.0.1}"
PY="${DOMINO_PYTHON:-python3}"
QUERY="${DOMINO_QUERY:-debt covenant default risk}"
SEC_FIXTURE="$FW/fixtures/sec_filings.json"
NEWS_FIXTURE="$FW/fixtures/news_feed.json"

mkdir -p "$OUT" "$LOGS" "$RUN_DIR"

say()  { printf '\033[1;36m[domino]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[domino]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[domino]\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

port_state() {
  "$PY" - "$HOST" "$PORT" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(1)
try:
    s.connect((sys.argv[1], int(sys.argv[2]))); print("open")
except Exception:
    print("closed")
finally:
    s.close()
PY
}

backend_running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null
}

# --- stages ------------------------------------------------------------------
preflight() {
  say "preflight"
  have "$PY" || die "$PY not found (set DOMINO_PYTHON)"
  "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
    || die "python >= 3.10 required"
  [ -d "$ROOT/Code-City-Apocalypse/backend" ] || warn "backend dir missing; 'serve' will fail"
  [ -f "$SEC_FIXTURE" ] || warn "missing fixture: $SEC_FIXTURE"
  say "python: $("$PY" --version 2>&1)"
  say "repo root: $ROOT"
}

serve() {
  [ -d "$ROOT/Code-City-Apocalypse/backend" ] || die "backend dir missing"
  if backend_running; then
    say "backend already running (pid $(cat "$PIDFILE"))"
    return 0
  fi
  say "starting Code City backend on ${HOST}:${PORT} -> $LOGS/backend.log"
  ( cd "$ROOT/Code-City-Apocalypse/backend" \
      && exec env HOST="$HOST" PORT="$PORT" "$PY" server.py ) \
      >>"$LOGS/backend.log" 2>&1 &
  echo "$!" >"$PIDFILE"
  for _ in $(seq 1 20); do
    if [ "$(port_state)" = "open" ]; then say "backend is listening"; return 0; fi
    sleep 0.5
  done
  warn "backend did not open the port; see $LOGS/backend.log"
  return 1
}

stop() {
  if backend_running; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    sleep 0.5
    say "backend stopped"
  else
    say "backend not running"
  fi
  rm -f "$PIDFILE"
}

run_cycle() {
  local do_broadcast="${1:-}"
  local label="ingest -> score -> translate -> export"
  [ "$do_broadcast" = "broadcast" ] && label="$label -> broadcast"
  say "cycle: $label"

  local args=(
    --ingest "sec=$SEC_FIXTURE"
    --ingest "news=$NEWS_FIXTURE"
    --query "$QUERY"
    --export "$OUT"
    --plan
  )
  [ "$do_broadcast" = "broadcast" ] && args+=( --broadcast )

  ( cd "$ROOT" && "$PY" -m core_framework.bin.scout_vehicle "ws://$HOST:$PORT" "${args[@]}" )
}

patrol()    { preflight; run_cycle; }
broadcast() { preflight; run_cycle broadcast; }

plan() {
  say "adaptive plan (from learned pheromones)"
  ( cd "$ROOT" && "$PY" -m core_framework.bin.scout_vehicle \
      --ingest "sec=$SEC_FIXTURE" --ingest "news=$NEWS_FIXTURE" \
      --query "$QUERY" --export "$OUT" --plan )
}

sprawl() {
  say "regenerating the doc-sprawl index + triage plan"
  ( cd "$ROOT" && "$PY" -m core_framework.bin.sprawl_scan )
}

status() {
  say "status"
  if backend_running; then
    say "backend: running (pid $(cat "$PIDFILE"), ${HOST}:${PORT})"
  else
    say "backend: stopped"
  fi
  say "output dir: $OUT"
  for f in market_twin.json alpha_stream.csv adaptive_memory.json; do
    if [ -f "$OUT/$f" ]; then
      say "  - $f ($(wc -c <"$OUT/$f" | tr -d ' ') bytes)"
    else
      say "  - $f (missing)"
    fi
  done
}

skill() {
  say "scout-driven skill"
  for sk in "$ROOT/axescout-market-twin.skill" "$HOME/.gemini/skills/axescout-market-twin"; do
    [ -e "$sk" ] && say "found: $sk"
  done
  cat <<'TIP'
  CLI agent hint:
    invoke the axescout-market-twin skill, then feed findings with:
      python -m core_framework.bin.scout_vehicle \
        --ingest sec=core_framework/fixtures/sec_filings.json \
        --ingest news=core_framework/fixtures/news_feed.json --plan
    live (network): export SEC_USER_AGENT and add --live
TIP
}

all() {
  preflight
  if [ "${DOMINO_SERVE:-1}" = "1" ]; then serve || warn "continuing without backend"; fi
  run_cycle broadcast || true
  status
  say "done — backend viewport: http://localhost:${PORT}"
}

usage() {
  cat <<'USAGE'
domino.sh — flick one domino, run the whole scout machine.

Usage: ./domino.sh [command]
  all (default)  preflight -> serve -> patrol -> broadcast -> status
  preflight      check interpreter, paths, fixtures
  serve          start the Code City backend (background, logged)
  stop           stop the backend started by this script
  restart        stop, then serve
  patrol         ingest -> score -> translate -> export (offline fixtures)
  broadcast      patrol + push the market twin to the backend
  plan           show the adaptive query plan learned so far
  status         show backend + output artifact status
  sprawl         regenerate SPRAWL_INDEX.md + SPRAWL_TRIAGE.md at the repo root
  skill          surface the axescout-market-twin skill and a CLI hint
  help           this text

Env: DOMINO_PORT DOMINO_HOST DOMINO_PYTHON DOMINO_QUERY DOMINO_SERVE
Root wrapper: ~/domino.sh (execs this file).
USAGE
}

cmd="${1:-all}"
shift || true
case "$cmd" in
  all|up|go|run)      all ;;
  preflight)          preflight ;;
  serve)              preflight; serve ;;
  stop)               stop ;;
  restart)            stop; preflight; serve ;;
  status)             status ;;
  sprawl|index)       sprawl ;;
  patrol|scout)       patrol ;;
  broadcast|push)     broadcast ;;
  plan|adaptive)      plan ;;
  skill)              skill ;;
  help|-h|--help)     usage ;;
  *) die "unknown command: $cmd (try: all serve stop patrol broadcast plan status sprawl skill help)" ;;
esac
