#!/usr/bin/env python3
# ROLE: taps — a tender burial for a broken streak (obituary log + gambit tombstone + salute page)
# DEPS: pathlib,argparse,json,datetime
# OFFLINE: yes — no network, no credentials, no writes outside --root
"""taps — the kingdom's funeral detail.

A streak that reaches 3 or more passes buys exactly one extra day of grace in
`src/skill/gambit.py`: `next_due_at` becomes 48h instead of 24h. When the count
resets, everything the streak earned collapses into that single day. That is the
whole estate, and it deserves a record rather than a silent zero.

So this tool buries it the way this repository asks for — tenderly. From
`tools/jerry-hearing/docs/ODDS_BRIDGE.md`:

    No streak shaming. Miss = cactus wobble "listen close..." not "you failed."
    Show is tender.

What a burial leaves behind:

  <root>/obituary.jsonl                         append-only, one line per loss
  <root>/graves/<user>__<skill>.jsonl           gambit-shaped tombstone, append-only
  <root>/rites/<user>__<skill>.html             optional 21-ribbon salute page
  <root>/audio_notes.jsonl                      append-only, what a browser did with the sound

Usage:

    python tools/taps/taps.py --skill med-triage-copilot --user bubba \
        --streak 4 --unit weeks

    python tools/taps/taps.py --skill med-triage-copilot --user bubba \
        --streak 4 --unit weeks --gambit-store rag_storage/instars \
        --html /tmp/rite.html --speak

Read-only on purpose: `--gambit-store` lets taps *read* the last streak gambit
recorded and cite it in the obituary. taps never writes there. `InstarEngine._load`
persists a fresh state file when it cannot find one, so calling the engine to
inspect a grave would plant a fake one; taps reads the JSON itself instead.

It also reconstructs the run the miss ended, from the history gambit appends, so
the obituary names what the streak earned — passes, instar path, points, fastest
answer, the date the call did not land — instead of only how long it lasted. When
there is no state file, the obituary says so and stands on the self-reported count.

Exit codes: 0 buried, 2 usage error (bad root, bad count, missing html template).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

RITE = "taps"
SALUTE_COUNT = 21  # ribbons raised for a finished run of passes; taps.html mirrors this

# Mirrors src/skill/gambit.py submit(): streak >= 3 -> 48h, else 24h.
GRACE_THRESHOLD = 3
GRACE_HOURS_LONG = 48
GRACE_HOURS_SHORT = 24
GRACE_RULE = "gambit: streak >= 3 -> 48h, else 24h"

UNIT_DAYS = {"days": 1, "weeks": 7, "months": 30}

# Audio is a runtime fact of a browser, so a record written at Render time cannot know
# it. These are the values a listener can report back with --audio-status.
AUDIO_UNVERIFIED = "unverified"
AUDIO_STATUSES = (AUDIO_UNVERIFIED, "ok", "unavailable")

# Invariant, not decoration: the eulogy is read by the person who just missed.
# Anything here is streak shaming, which ODDS_BRIDGE.md forbids. Tested.
SHAMING_TOKENS = ("failed", "failure", "lazy", "shame", "disappoint", "excuses")

# The page reads its obituary with JSON.parse, so the slot is a JSON *string
# literal*: valid JS whether or not anything has been injected. A raw object
# dropped into a quoted slot parses as a string and the page would quietly show
# its demo obituary instead of the real one.
OBIT_PLACEHOLDER = "TAPS_OBIT_PLACEHOLDER"
OBIT_SLOT = f'"{OBIT_PLACEHOLDER}"'
DEFAULT_ROOT = Path.home() / ".taps"
HTML_TEMPLATE = Path(__file__).resolve().parent / "taps.html"


# ── the gambit rule, restated in one place ───────────────────────
def grace_hours(streak: int) -> int:
    """Hours of spaced-repetition grace a streak at this length earned."""
    return GRACE_HOURS_LONG if streak >= GRACE_THRESHOLD else GRACE_HOURS_SHORT


def grace_until(ended_on: datetime, streak: int) -> datetime:
    return ended_on + timedelta(hours=grace_hours(streak))


def streak_days(streak: int, unit: str) -> int:
    return streak * UNIT_DAYS.get(unit, 1)


def _safe_id(value: str, limit: int) -> str:
    """Same filename scrubbing gambit uses, so taps can find its state files."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:limit]


def _stamp(ts: Any) -> Optional[str]:
    """Epoch seconds -> date, tolerating whatever a hand-edited ledger holds."""
    if not isinstance(ts, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def streak_run(history: Any) -> Optional[Dict[str, Any]]:
    """The run of passes that a miss ended — what the streak actually earned.

    gambit appends one entry per challenge: a pass extends the streak, a miss
    resets it to 0. So the broken streak is the run of passes immediately before
    the most recent miss, and that is what a burial should be able to name instead
    of a bare zero.

    Returns None when there is nothing buried (empty or malformed history) or when
    the run is still standing (the latest entry passed), because a living streak
    has no obituary to write.
    """
    entries = [
        e for e in (history or [])
        if isinstance(e, dict) and e.get("type") == "challenge"
    ]
    if not entries or entries[-1].get("passed"):
        return None

    run: list = []
    for entry in reversed(entries[:-1]):
        if not entry.get("passed"):
            break
        run.append(entry)
    if not run:
        return None
    run.reverse()

    speeds = [e["elapsed_ms"] for e in run if isinstance(e.get("elapsed_ms"), (int, float))]
    missed = entries[-1]
    return {
        "passes": len(run),
        "points": sum(int(e.get("points") or 0) for e in run),
        "fastest_ms": min(speeds) if speeds else None,
        "instar_first": run[0].get("instar"),
        "instar_last": run[-1].get("instar"),
        "started": _stamp(run[0].get("ts")),
        "ended": _stamp(run[-1].get("ts")),
        "last_call": {
            "question": (missed.get("q") or "")[:80],
            "ratio": missed.get("ratio"),
            "at": _stamp(missed.get("ts")),
        },
    }


def _seconds(ms: Any) -> Optional[str]:
    return f"{ms / 1000:.1f}" if isinstance(ms, (int, float)) else None


# ── the record ───────────────────────────────────────────────────
def build_obituary(
    *,
    skill: str,
    user: str,
    streak: int,
    unit: str,
    ended_on: datetime,
    recorded_at: datetime,
    gambit_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    days = streak_days(streak, unit)
    find = grace_until(ended_on, streak)
    record: Dict[str, Any] = {
        "type": "obituary",
        "rite": RITE,
        "recorded_at": recorded_at.isoformat(),
        "ended_on": ended_on.date().isoformat(),
        "user": user,
        "skill": skill,
        "streak": {"value": streak, "unit": unit, "days": days},
        "grace": {
            "hours": grace_hours(streak),
            "rule": GRACE_RULE,
            "spent_until": find.isoformat(),
        },
        "salute": SALUTE_COUNT,
        # Honest by default: nothing has heard this rite yet.
        "audio": {
            "status": AUDIO_UNVERIFIED,
            "verified": False,
            "note": "no browser runs when a record is written; the salute page reports its own audio state",
        },
        "provenance": {
            "source": "self-reported",
            "verified": False,
            "reported_by": user,
            "recorded_via": "tools/taps/taps.py",
        },
    }
    if gambit_state is not None:
        record["gambit"] = {
            "found": True,
            "path": gambit_state.get("path"),
            "instar": gambit_state.get("instar"),
            "streak": gambit_state.get("streak"),
            "history_len": gambit_state.get("history_len"),
            "run": gambit_state.get("run"),
            "note": "read-only; taps did not touch this file",
        }
    else:
        # No state file, so the obituary stands on the self-reported count alone.
        # Recorded as absence rather than silence, and never invented.
        record["gambit"] = {
            "found": False,
            "streak": None,
            "run": None,
            "note": "no instar file at --gambit-store; count is self-reported",
        }
    return record


def read_gambit_state(store_dir: Path, user: str, skill: str) -> Optional[Dict[str, Any]]:
    """Read a gambit instar file without loading InstarEngine (which writes)."""
    path = store_dir / f"{_safe_id(user, 24)}__{_safe_id(skill, 40)}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {
        "path": str(path),
        "instar": data.get("instar"),
        "streak": data.get("streak"),
        "history_len": len(data.get("history") or []),
        "run": streak_run(data.get("history")),
    }


def ledger_lines(run: Dict[str, Any]) -> list:
    """What the run earned, in its own numbers, so the burial can name it.

    Reads as testimony, not as a scorecard: the count, the instar path, the points,
    the fastest answer. The last call is stated once and not graded.
    """
    lines = [f"    {run['passes']} consecutive passes"]
    first, last = run.get("instar_first"), run.get("instar_last")
    if first is not None:
        path = f"instar {first}" if first == last else f"instar {first} → {last}"
        lines.append(f"    {path}")
    if run.get("points"):
        lines.append(f"    {run['points']} points")
    fast = _seconds(run.get("fastest_ms"))
    if fast:
        lines.append(f"    fastest answer {fast}s")
    if run.get("started"):
        span = run["started"] if run.get("ended") in (None, run["started"]) else f"{run['started']} → {run['ended']}"
        lines.append(f"    {span}")
    return lines


def eulogy(obit: Dict[str, Any]) -> str:
    """Tender by contract. No verdicts, no rebuke — the record, said plainly."""
    streak = obit["streak"]["value"]
    unit = obit["streak"]["unit"]
    days = obit["streak"]["days"]
    grace = obit["grace"]["hours"]
    skill = obit["skill"]
    user = obit["user"]
    gambit = obit.get("gambit") or {}

    lines = [
        f"TAPS — for the {streak}-{unit} streak ({days} days) on {skill}",
        "",
        f"  {user}, the count stopped here — the way every count stops:",
        "  at the edge of being a person with other work to do.",
        "",
        f"  What it earned was one day of grace ({grace}h, the rule restated from",
        "  src/skill/gambit.py), and that day is spent.",
    ]

    run = gambit.get("run")
    if run:
        lines += ["", "  What the run left in the ledger:", *ledger_lines(run)]
        last = run.get("last_call") or {}
        if last.get("at"):
            lines.append(f"    the call on {last['at']} did not land; the count went back to zero")

    instar = gambit.get("instar")
    lines += [
        "",
        f"  The instar did not move. It is still standing{(' at ' + str(instar)) if instar else ''}.",
        "",
        "  Twenty-one ribbons, raised one at a time.",
        "  Hands in brown work gloves, because this was work.",
        "  The cactus wobbles instead of pointing. Listen close.",
        "",
        "  Nothing is owed. When you come back, the doc hydrates at the same",
        "  instar, and the next challenge is a first challenge, not a debt.",
        "",
        "  When the bugle stops, the prairie keeps humming.",
    ]
    return "\n".join(lines)


def append_jsonl(path: Path, record: Dict[str, Any]) -> int:
    """Append-only by construction: open 'a', never 'w'. Returns new line count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def grave_path(root: Path, user: str, skill: str) -> Path:
    return root / "graves" / f"{_safe_id(user, 24)}__{_safe_id(skill, 40)}.jsonl"


def matching_obituaries(root: Path, skill: str, user: str) -> int:
    """How many recorded burials a note like this one belongs to.

    A note that matches nothing is a stale record, and stale records are how a log
    quietly stops meaning anything. Counted rather than assumed, and surfaced in the
    note itself.
    """
    path = root / "obituary.jsonl"
    if not path.is_file():
        return 0
    found = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("skill") == skill and entry.get("user") == user:
                found += 1
    return found


def append_audio_note(
    root: Path,
    obit: Dict[str, Any],
    status: str,
    reason: Optional[str] = None,
) -> int:
    """Record what the browser actually did with the sound.

    A separate append-only file rather than an edit, because the obituary is the
    durable record and rewriting it to add a later fact would make the first line a
    lie. `obituary_lines` ties the note back to the burial it belongs to.
    """
    if status not in AUDIO_STATUSES:
        raise ValueError(f"unknown audio status {status!r}; expected one of {AUDIO_STATUSES}")
    obituaries = root / "obituary.jsonl"
    lines = 0
    if obituaries.is_file():
        with obituaries.open(encoding="utf-8") as fh:
            lines = sum(1 for _ in fh)
    matched = matching_obituaries(root, obit["skill"], obit["user"])
    note = {
        "type": "audio_note",
        "rite": RITE,
        "status": status,
        "reason": reason,
        "skill": obit["skill"],
        "user": obit["user"],
        "ended_on": obit["ended_on"],
        "obituary_lines": lines,
        "matched_obituaries": matched,
        "provenance": {
            "source": "self-reported",
            "verified": False,
            "reported_by": obit["user"],
            "recorded_via": "tools/taps/taps.py",
        },
        "note": "the obituary itself is never rewritten with a later finding",
    }
    return append_jsonl(root / "audio_notes.jsonl", note)


def render_rite(template_path: Path, obit: Dict[str, Any]) -> str:
    """Inject the obituary into the self-contained salute page.

    Double-encoded on purpose: the payload is a JSON string literal holding JSON,
    which is what `JSON.parse` wants and what keeps the unrendered template valid.
    """
    if not template_path.is_file():
        raise FileNotFoundError(f"rite template missing; expected {template_path}")
    template = template_path.read_text(encoding="utf-8")
    if OBIT_SLOT not in template:
        raise ValueError(f"template has no {OBIT_SLOT} slot")
    payload = json.dumps(json.dumps(obit, sort_keys=True))
    rendered = template.replace(OBIT_SLOT, payload)
    if OBIT_PLACEHOLDER in rendered:
        raise ValueError(f"template still holds a bare {OBIT_PLACEHOLDER}")
    return rendered


def speak(text: str) -> str:
    """Best-effort TTS. Prints instead of failing when no voice is installed."""
    for cmd in (["say"], ["spd-say"]):
        exe = shutil.which(cmd[0])
        if exe:
            try:
                subprocess.run(
                    [exe, *cmd[1:], text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                    check=False,
                )
                return exe
            except (OSError, subprocess.SubprocessError):
                continue
    print(text)
    return ""


def parse_at(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not an ISO timestamp: {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Bury a broken streak tenderly.")
    p.add_argument("--skill", default="unknown-skill")
    p.add_argument("--user", default="anon")
    p.add_argument("--streak", type=int, default=0)
    p.add_argument("--unit", choices=sorted(UNIT_DAYS), default="days")
    p.add_argument("--root", default=str(DEFAULT_ROOT), help="where the grave goes")
    p.add_argument("--gambit-store", default=None, help="read-only: cite gambit's last streak")
    p.add_argument("--at", default=None, help="ISO time to pin the record (tests, backfill)")
    p.add_argument("--html", default=None, help="write the salute page here")
    p.add_argument("--speak", action="store_true", help="read the eulogy aloud if a voice exists")
    p.add_argument(
        "--audio-status",
        choices=AUDIO_STATUSES,
        default=None,
        help="record what the salute page's sound did in your browser; note only, no second burial",
    )
    p.add_argument("--audio-reason", default=None, help="the page's own words for the silence")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    if args.streak < 0:
        p.error("--streak cannot be negative; there is no anti-streak to bury")

    root = Path(args.root).expanduser()
    at = parse_at(args.at)
    gambit = (
        read_gambit_state(Path(args.gambit_store).expanduser(), args.user, args.skill)
        if args.gambit_store
        else None
    )

    obit = build_obituary(
        skill=args.skill,
        user=args.user,
        streak=args.streak,
        unit=args.unit,
        ended_on=at,
        recorded_at=at,
        gambit_state=gambit,
    )

    if args.audio_status:
        notes = append_audio_note(root, obit, args.audio_status, args.audio_reason)
        if not args.quiet:
            print(f"audio status '{args.audio_status}' recorded as note #{notes}: {root / 'audio_notes.jsonl'}")
            print("  no new burial written — the obituary is never rewritten")
            if matching_obituaries(root, args.skill, args.user) == 0:
                print(
                    "  warning: no obituary in this root matches "
                    f"skill={args.skill!r} user={args.user!r} — the note stands alone"
                )
        return 0

    n = append_jsonl(root / "obituary.jsonl", obit)
    append_jsonl(grave_path(root, args.user, args.skill), obit)

    if args.html:
        out = Path(args.html).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_rite(HTML_TEMPLATE, obit), encoding="utf-8")

    text = eulogy(obit)
    if args.speak:
        speak(text)
    if not args.quiet:
        print(text)
        print(f"\n  obituary #{n}: {root / 'obituary.jsonl'}")
        if args.html:
            print(f"  salute page: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
