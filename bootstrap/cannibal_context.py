#!/usr/bin/env python3
"""
core_framework/bootstrap/cannibal_context.py

CannibalContext — the session bootstrap / "ring music" intro.

Goal: give every session (human or agent) a razor-thin, boardroom-aligned
operating context WITHOUT burning the token budget on narrative history.
It does four things, all offline and stdlib-only:

  1. CONTEXT    Loads the operator config (cannibal_context.json). Resolution
                order: $CANNIBAL_CONTEXT -> ~/.config/freebuff/cannibal_context.json
                -> the packaged default in bootstrap/cannibal_context.json.
                The packaged default is read-only; `install` copies it to the
                user path so it survives reboots and edits stay user-owned.

  2. KICKOFF    Renders a compact header banner + multiple-choice session menu
                (Tracks 1-3, Blue Sky, Custom Angle), suggests a first domino
                command for the chosen angle, and prints the auto-boot plan.
                The choice is appended to a JSONL session stream so the NEXT
                session resumes from it (`--auto` replays the last angle).
                This is the persistent-state / knowledge-graph anchor: the
                session stream (sessions.jsonl) plus the scout pheromone
                memory (output/adaptive_memory.json) are the two .jsonl/json
                streams that survive across reboots.

  3. HANDSHAKE  Emits the compressed one-line bridge primitive that gets pasted
                into ANY external chat (GLM, Claude, Gemini, novel web tools)
                so a brand-new agent knows the operating protocol instantly:
                [SYS_INIT]: Operator=Mikey | VCS=Nat | Output=cat<<'EOF' | ...

  4. AUTO-BOOT  Prints concrete boot actions for the configured auto_boot list
                (terminal targets, cron/workflow state, knowledge-graph
                streams). It deliberately does NOT spawn daemons: long-lived
                processes started from a sandbox die with the session, so the
                plan lists the exact commands for the operator to fire.

Safety: no network, no secrets, no writes outside the framework output paths
and the user's own config directory. Removing this package has zero effect on
any canonical source tree — same guarantee as the rest of core_framework.

CLI:
  python -m core_framework.bootstrap.cannibal_context kickoff            # menu (interactive if TTY)
  python -m core_framework.bootstrap.cannibal_context kickoff --track 2  # non-interactive pick
  python -m core_framework.bootstrap.cannibal_context kickoff --custom "..."
  python -m core_framework.bootstrap.cannibal_context kickoff --auto     # resume last angle
  python -m core_framework.bootstrap.cannibal_context handshake          # bridge primitive only
  python -m core_framework.bootstrap.cannibal_context menu | context | sessions | install | help

Shell hook (one line in ~/.bashrc -> auto ring music on every login):
  python3 -m core_framework.bootstrap.cannibal_context kickoff || true
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution — env override first, then user config, then packaged default
# ---------------------------------------------------------------------------
FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = FRAMEWORK_ROOT / "bootstrap" / "cannibal_context.json"

CONFIG_ENV = "CANNIBAL_CONTEXT"      # explicit config file override (tests/CI)
SESSIONS_ENV = "CANNIBAL_SESSIONS"   # explicit session-log override (tests/CI)
USER_CONFIG_DIR = Path.home() / ".config" / "freebuff"
USER_CONFIG_PATH = USER_CONFIG_DIR / "cannibal_context.json"
DEFAULT_SESSIONS_PATH = USER_CONFIG_DIR / "sessions.jsonl"

# Width of the header banner; kept narrow so it fits any terminal pane.
BANNER_WIDTH = 64


# ---------------------------------------------------------------------------
# Context loading
# ---------------------------------------------------------------------------
def resolve_config_path(explicit: str | Path | None = None) -> Path | None:
    """Return the config file to use, or None if nothing exists.

    Precedence: explicit arg > $CANNIBAL_CONTEXT > ~/.config/freebuff/ >
    packaged default. Returning None (instead of crashing) lets a stripped
    environment degrade gracefully to an empty context.
    """
    if explicit:
        return Path(explicit)
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env)
    if USER_CONFIG_PATH.exists():
        return USER_CONFIG_PATH
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    return None


def load_context(explicit: str | Path | None = None) -> tuple[dict, Path | None]:
    """Load the operator context. Returns (context_dict, resolved_path)."""
    path = resolve_config_path(explicit)
    if path is None:
        return {}, None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"cannibal context must be a JSON object: {path}")
    return data, path


def install_user_config(force: bool = False) -> Path:
    """Copy the packaged default config to ~/.config/freebuff/cannibal_context.json.

    Never overwrites an existing user config unless ``force`` is set — the
    user's own edits to operator identity/protocol outrank the packaged file.
    """
    if USER_CONFIG_PATH.exists() and not force:
        return USER_CONFIG_PATH
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(
        DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return USER_CONFIG_PATH


# ---------------------------------------------------------------------------
# Menu, banner, handshake
# ---------------------------------------------------------------------------
def menu_options(ctx: dict) -> list[str]:
    """Return the session menu, guaranteeing a Custom Angle escape hatch."""
    options = list((ctx.get("session_kickoff") or {}).get("menu_options") or [])
    if not any(o.strip().lower().startswith("custom") for o in options):
        options.append("Custom Angle")  # inspiration-proof by construction
    return options


def render_menu(ctx: dict) -> str:
    """Render the numbered multiple-choice menu as plain text."""
    lines = ["session angle (pick one):"]
    for i, option in enumerate(menu_options(ctx), start=1):
        lines.append(f"  {i}) {option}")
    return "\n".join(lines)


def render_banner(ctx: dict, log: "SessionLog | None" = None) -> str:
    """Compact header banner: identity, protocol, horizon, last session.

    Kept to ~6 lines on purpose — this prints on every login, so token weight
    and visual weight both stay near zero.
    """
    bar = "=" * BANNER_WIDTH
    lines = [
        bar,
        f"  CANNIBAL CONTEXT // {ctx.get('operator', 'operator')}"
        f" — {ctx.get('archetype', '')}",
        f"  mode: {ctx.get('mode', '')}",
        f"  deep-work horizon: {ctx.get('default_session_length', '2 to 10 hours')}",
    ]
    if log is not None:
        last = log.last()
        if last:
            label = (last.get("choice") or {}).get("label", "unknown")
            stamp = time.strftime(
                "%Y-%m-%d %H:%M UTC", time.gmtime(last.get("timestamp_utc", 0))
            )
            lines.append(f"  last session: {label} @ {stamp}")
    lines.append(bar)
    return "\n".join(lines)


def handshake(ctx: dict) -> str:
    """Build the one-line bridge primitive for external agents/models.

    Derived from execution_rules so the string can never drift from the
    declared protocol. Falls back to sane defaults when keys are missing so a
    truncated config still produces a valid handshake.
    """
    kickoff = ctx.get("session_kickoff") or {}
    template = (
        kickoff.get("handshake_template")
        or "[SYS_INIT]: Operator={operator} | VCS={vcs} | Output={output}"
        " | Arch=core_framework | Mode={mode}"
    )
    rules = ctx.get("execution_rules") or {}

    vcs = (rules.get("version_control") or "Nat").split()[0]
    write_fallback = rules.get("file_write_fallback") or ""
    # Compress the cat-heredoc fallback to its canonical short form; anything
    # else is passed through trimmed so the line stays one line.
    output = "cat<<'EOF'" if write_fallback.startswith("cat") else write_fallback

    return template.format(
        operator=ctx.get("operator", "operator"),
        archetype=ctx.get("archetype", ""),
        mode=ctx.get("mode", ""),
        vcs=vcs,
        output=output,
        session_length=ctx.get("default_session_length", ""),
    )


def track_hint(ctx: dict, choice: str) -> str | None:
    """Return the suggested first domino command for a chosen angle, if any.

    Matching is prefix-based on the track_hints keys so config authors can
    write "Track 1", "Blue Sky", etc. without duplicating full option labels.
    """
    hints = (ctx.get("session_kickoff") or {}).get("track_hints") or {}
    lowered = choice.strip().lower()
    for prefix, hint in hints.items():
        if lowered.startswith(str(prefix).strip().lower()):
            return hint
    return None


# ---------------------------------------------------------------------------
# Session history — the JSONL state stream (persistent across reboots)
# ---------------------------------------------------------------------------
class SessionLog:
    """Append-only JSONL session history.

    One JSON object per line: timestamp, chosen angle, handshake snapshot, and
    the auto-boot plan actually shown. JSONL (not JSON) so concurrent sessions
    and crash kills can never corrupt the whole history — at worst one line.
    """

    def __init__(self, path: str | Path | None = None, clock=time.time):
        env = os.environ.get(SESSIONS_ENV)
        self.path = Path(path or env or DEFAULT_SESSIONS_PATH)
        self._clock = clock

    def record(self, entry: dict) -> dict:
        """Append one session entry (timestamp added if absent)."""
        entry = {"timestamp_utc": self._clock(), **entry}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def last(self) -> dict | None:
        """Most recent session entry, or None when history is empty/corrupt.

        Delegates to ``tail(1)`` so a torn final line (crash mid-write) is
        skipped rather than taking the kickoff down with it.
        """
        entries = self.tail(1)
        return entries[-1] if entries else None

    def tail(self, n: int = 5) -> list[dict]:
        """Last ``n`` valid entries, oldest first (empty list when no history).

        Parsing happens BEFORE the ``n`` slice so torn lines can never displace
        a valid entry from the window.
        """
        if not self.path.exists():
            return []
        try:
            lines = [
                line
                for line in self.path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            return []
        out: list[dict] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip torn lines, keep the rest
        return out[-n:]


# ---------------------------------------------------------------------------
# Auto-boot plan
# ---------------------------------------------------------------------------
def boot_plan(ctx: dict, framework_root: Path = FRAMEWORK_ROOT) -> list[str]:
    """Resolve the auto_boot wishlist into concrete, copy-pasteable actions.

    Unknown keys pass through untouched (with an extension pointer) so the
    config can grow without code changes silently dropping entries.
    """
    plan: list[str] = []
    wanted = (ctx.get("session_kickoff") or {}).get("auto_boot") or []
    for key in wanted:
        if key == "terminal_windows":
            plan.append(
                "terminal_windows: tabs -> repo root / core_framework/output/"
                " / core_framework/logs/ (open + view aliases)"
            )
        elif key == "cron_monitors":
            workflow = framework_root / ".github/workflows/scout_cron.yml"
            state = (
                "template present (dispatch-first; schedule off until live"
                " ingestion is verified) — fire with: gh workflow run scout-cron"
                if workflow.exists()
                else "scout_cron.yml not found in this checkout"
            )
            plan.append(f"cron_monitors: {state}")
        elif key == "loom_knowledge_graph":
            plan.append(
                "loom_knowledge_graph: streams -> sessions.jsonl (this history)"
                " + output/adaptive_memory.json (pheromones); refresh: ./domino.sh plan"
            )
        else:
            plan.append(
                f"{key}: (no built-in handler — run manually or extend "
                f"boot_plan() in cannibal_context.py)"
            )
    return plan


# ---------------------------------------------------------------------------
# Kickoff flow
# ---------------------------------------------------------------------------
def kickoff(
    ctx: dict,
    *,
    choice_index: int | None = None,
    custom: str | None = None,
    auto: bool = False,
    log: SessionLog | None = None,
    interactive: bool | None = None,
) -> str:
    """Run one session kickoff and return the rendered block.

    Selection precedence: --custom > --track N > --auto (replay last angle) >
    interactive prompt (TTY only) > menu-only, no record. A session is only
    appended to the history when an actual angle was chosen — cron/CI runs
    never pollute the stream.
    """
    log = log or SessionLog()
    if interactive is None:
        interactive = sys.stdin.isatty()

    options = menu_options(ctx)
    choice: str | None = None

    if custom:
        choice = custom.strip() or "Custom Angle"
    elif choice_index is not None:
        if not 1 <= choice_index <= len(options):
            raise ValueError(
                f"--track must be 1..{len(options)}, got {choice_index}"
            )
        choice = options[choice_index - 1]
    elif auto:
        last = log.last()
        if last and (last.get("choice") or {}).get("label"):
            choice = last["choice"]["label"]  # resume the last angle

    if choice is None and interactive:
        sys.stdout.write(render_menu(ctx) + "\n> ")
        sys.stdout.flush()
        raw = sys.stdin.readline().strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            choice = options[int(raw) - 1]
        elif raw:
            choice = raw  # free-text angle = Custom Angle by definition

    parts = [render_banner(ctx, log)]
    if choice is None:
        # No angle chosen: show the menu as the suggestion, record nothing.
        parts.append(render_menu(ctx))
        parts.append("(no angle chosen — nothing recorded; pass --track/--custom/--auto)")
    else:
        parts.append(f"angle: {choice}")
        hint = track_hint(ctx, choice)
        if hint:
            parts.append(f"first domino: {hint}")
        entry = log.record(
            {
                "choice": {"label": choice, "custom": bool(custom)},
                "session_length": ctx.get("default_session_length", ""),
                "handshake": handshake(ctx),
                "auto_boot": (ctx.get("session_kickoff") or {}).get("auto_boot") or [],
            }
        )
        parts.append(f"logged: sessions.jsonl @ {entry['timestamp_utc']:.0f}")

    parts.append(f"bridge primitive: {handshake(ctx)}")
    for action in boot_plan(ctx):
        parts.append(f"boot: {action}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core_framework.bootstrap.cannibal_context",
        description="CannibalContext session bootstrap (ring music, minus the tokens).",
    )
    sub = parser.add_subparsers(dest="command")

    kick = sub.add_parser("kickoff", help="render banner + menu and log the chosen angle")
    kick.add_argument("--track", type=int, metavar="N", help="pick menu option N non-interactively")
    kick.add_argument("--custom", metavar="TEXT", help="free-text session angle (Custom Angle)")
    kick.add_argument("--auto", action="store_true", help="resume the last session's angle")
    kick.add_argument("--config", metavar="PATH", help="explicit context JSON override")
    kick.add_argument("--session-log", metavar="PATH", help="explicit sessions.jsonl override")

    sub.add_parser("menu", help="print the session menu only")
    sub.add_parser("handshake", help="print the [SYS_INIT] bridge primitive only")
    sub.add_parser("context", help="print the resolved context JSON")
    sub.add_parser("install", help="copy the packaged default config to ~/.config/freebuff/")
    sub.add_parser("sessions", help="print recent session history entries")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "kickoff"

    if command == "install":
        # Decide the message BEFORE installing: after the write the file
        # always exists, so checking afterwards would mislabel a fresh copy.
        existed = USER_CONFIG_PATH.exists()
        path = install_user_config()
        print(f"config at: {path}" + (" (existing left untouched)" if existed else " (default copied)"))
        return 0

    ctx, path = load_context(getattr(args, "config", None))
    if not ctx:
        print("[cannibal_context] no context config found", file=sys.stderr)
        return 1

    if command == "menu":
        print(render_menu(ctx))
    elif command == "handshake":
        print(handshake(ctx))
    elif command == "context":
        print(json.dumps(ctx, indent=2))
    elif command == "sessions":
        log = SessionLog(getattr(args, "session_log", None))
        entries = log.tail(10)
        if not entries:
            print("(no sessions logged yet)")
        for e in entries:
            label = (e.get("choice") or {}).get("label", "?")
            print(f"  {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(e.get('timestamp_utc', 0)))}  {label}")
    elif command == "kickoff":
        log = SessionLog(getattr(args, "session_log", None))
        print(
            kickoff(
                ctx,
                choice_index=getattr(args, "track", None),
                custom=getattr(args, "custom", None),
                auto=getattr(args, "auto", False),
                log=log,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
