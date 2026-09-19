#!/usr/bin/env python3
"""
agent_state.py — lightweight concurrent shared state for side-by-side CLI agents.

Implements the .agent_state.json pattern from the handoff protocol:
agents announce what they are touching (claims) and what they finished
(completions); other agents poll before touching shared paths.

Design constraints:
  - stdlib only, single file, no daemon
  - atomic state writes (tmp + rename) so concurrent readers never see a
    torn file
  - claims carry a TTL (default 900s): a crashed agent's stale lock
    expires instead of deadlocking the workspace
  - claims are advisory: this is coordination, not security

Usage:
  python3 scripts/agent_state.py claim  <agent> <path> [--ttl 900]
  python3 scripts/agent_state.py release <agent> <path>
  python3 scripts/agent_state.py done    <agent> <summary...>   # log completion
  python3 scripts/agent_state.py check   <path>                  # is it claimed?
  python3 scripts/agent_state.py show                            # full state
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path("/home/bleaknarratives/.agent_state.json")
DEFAULT_TTL = 900  # seconds


def _load():
    if not STATE_FILE.exists():
        return {"claims": {}, "completions": [], "updated": None}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable state: back it up and start clean rather
        # than wedge every agent on one bad write.
        try:
            STATE_FILE.replace(STATE_FILE.with_suffix(".json.corrupt"))
        except OSError:
            pass
        return {"claims": {}, "completions": [], "updated": None}


def _save(state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_FILE)  # atomic on POSIX


def _purge_expired(state):
    now = time.time()
    state["claims"] = {
        path: claim for path, claim in state["claims"].items()
        if claim.get("expires_at", 0) > now
    }


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def cmd_claim(agent, path, ttl):
    state = _load()
    _purge_expired(state)
    key = str(Path(path).absolute())
    existing = state["claims"].get(key)
    if existing and existing["agent"] != agent:
        print(f"BUSY: {key} claimed by {existing['agent']} "
              f"(expires {datetime.fromtimestamp(existing['expires_at'], tz=timezone.utc).isoformat()})")
        return 1
    state["claims"][key] = {
        "agent": agent,
        "claimed_at": _now_iso(),
        "expires_at": time.time() + ttl,
    }
    _save(state)
    print(f"CLAIMED: {key} by {agent} (ttl {ttl}s)")
    return 0


def cmd_release(agent, path):
    state = _load()
    _purge_expired(state)
    key = str(Path(path).absolute())
    claim = state["claims"].get(key)
    if claim and claim["agent"] != agent:
        print(f"REFUSED: {key} is claimed by {claim['agent']}, not {agent}")
        return 1
    state["claims"].pop(key, None)
    _save(state)
    print(f"RELEASED: {key} by {agent}")
    return 0


def cmd_done(agent, summary):
    state = _load()
    _purge_expired(state)
    state["completions"].append({
        "agent": agent,
        "summary": " ".join(summary)[:500],
        "ts": _now_iso(),
    })
    state["completions"] = state["completions"][-100:]  # rolling window
    _save(state)
    print(f"DONE logged: {agent}")
    return 0


def cmd_check(path):
    state = _load()
    _purge_expired(state)
    key = str(Path(path).absolute())
    claim = state["claims"].get(key)
    if claim:
        print(f"BUSY: {key} claimed by {claim['agent']} since {claim['claimed_at']}")
        return 1
    print(f"FREE: {key}")
    return 0


def cmd_show():
    state = _load()
    _purge_expired(state)
    print(json.dumps(state, indent=2))
    return 0


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "claim":
        ttl = DEFAULT_TTL
        if "--ttl" in args:
            i = args.index("--ttl")
            ttl = int(args[i + 1])
            args = args[:i] + args[i + 2:]
        return cmd_claim(args[1], args[2], ttl)
    if len(args) >= 3 and args[0] == "release":
        return cmd_release(args[1], args[2])
    if len(args) >= 3 and args[0] == "done":
        return cmd_done(args[1], args[2:])
    if len(args) >= 2 and args[0] == "check":
        return cmd_check(args[1])
    if args[:1] == ["show"]:
        return cmd_show()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
