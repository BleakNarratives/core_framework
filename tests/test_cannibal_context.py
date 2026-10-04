#!/usr/bin/env python3
"""
core_framework/tests/test_cannibal_context.py

Deterministic, offline tests for the CannibalContext session bootstrap.
All filesystem effects are redirected into tmp_path via the env overrides and
the injectable SessionLog path, so the user's real ~/.config/freebuff is never
touched and no session stream is polluted by CI runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core_framework.bootstrap import cannibal_context as cc

from core_framework.bootstrap.cannibal_context import (
    DEFAULT_CONFIG_PATH,
    SessionLog,
    boot_plan,
    handshake,
    install_user_config,
    kickoff,
    load_context,
    menu_options,
    render_banner,
    render_menu,
    track_hint,
)


class FakeClock:
    """Injected clock so session timestamps are fully deterministic."""

    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def ctx():
    """The packaged default context (read-only)."""
    context, path = load_context(DEFAULT_CONFIG_PATH)
    assert path == DEFAULT_CONFIG_PATH
    return context


def _log(tmp_path, clock) -> SessionLog:
    return SessionLog(path=tmp_path / "sessions.jsonl", clock=clock)


# ---------------------------------------------------------------------------
# Context + protocol surfaces
# ---------------------------------------------------------------------------
def test_default_config_has_required_keys(ctx):
    assert ctx["operator"] == "Mikey"
    assert "execution_rules" in ctx and "session_kickoff" in ctx
    rules = ctx["execution_rules"]
    assert rules["version_control"].startswith("Nat")
    assert rules["file_write_fallback"].startswith("cat << 'EOF'")
    options = ctx["session_kickoff"]["menu_options"]
    assert len(options) == 5
    assert any(o.startswith("Track 1") for o in options)
    assert any("Blue Sky" in o for o in options)


def test_menu_options_guarantees_custom_angle(ctx):
    options = menu_options(ctx)
    assert options[-1].lower().startswith("custom")
    # A config without one still gets the escape hatch appended, exactly once.
    stripped = dict(ctx)
    stripped["session_kickoff"] = {"menu_options": ["Track 1: X"]}
    assert menu_options(stripped).count("Custom Angle") == 1


def test_handshake_matches_declared_protocol(ctx):
    expected = (
        "[SYS_INIT]: Operator=Mikey | VCS=Nat | Output=cat<<'EOF'"
        " | Arch=core_framework | Mode=Goal-Oriented / Profit-Minded / Boardroom Approved"
    )
    assert handshake(ctx) == expected


def test_handshake_degrades_gracefully_on_empty_context():
    assert handshake({}).startswith("[SYS_INIT]: Operator=operator")


def test_track_hint_matches_by_prefix(ctx):
    assert track_hint(ctx, "Track 2: Core Framework Adapter Hardening") == (
        "./domino.sh preflight && python3 -m pytest tests/ -q"
    )
    assert track_hint(ctx, "Blue Sky Meeting (Iterative Architecture)") == "./domino.sh sprawl"
    assert track_hint(ctx, "Something Unmapped") is None


def test_banner_and_menu_render(ctx, tmp_path):
    clock = FakeClock()
    log = _log(tmp_path, clock)
    log.record({"choice": {"label": "Track 1: Monetization Ledger & Signal SKU"}})
    banner = render_banner(ctx, log)
    assert "Mikey" in banner and "last session: Track 1" in banner
    assert render_menu(ctx).count("Track 2: Core Framework Adapter Hardening") == 1


# ---------------------------------------------------------------------------
# Session stream
# ---------------------------------------------------------------------------
def test_session_log_record_last_tail(tmp_path):
    clock = FakeClock()
    log = _log(tmp_path, clock)

    assert log.last() is None and log.tail() == []

    log.record({"choice": {"label": "A"}})
    clock.advance(10)
    log.record({"choice": {"label": "B"}})

    last = log.last()
    assert last["choice"]["label"] == "B"
    assert last["timestamp_utc"] == clock.t
    assert [e["choice"]["label"] for e in log.tail(10)] == ["A", "B"]


def test_session_log_survives_torn_final_line(tmp_path):
    # A crash mid-write must not take history down with it.
    path = tmp_path / "sessions.jsonl"
    path.write_text(
        json.dumps({"timestamp_utc": 1, "choice": {"label": "A"}}) + "\n" + '{"torn'
    )
    log = SessionLog(path=path)
    assert log.last()["choice"]["label"] == "A"
    assert [e["choice"]["label"] for e in log.tail()] == ["A"]


# ---------------------------------------------------------------------------
# Kickoff flow
# ---------------------------------------------------------------------------
def test_kickoff_with_track_records_choice(ctx, tmp_path):
    clock = FakeClock()
    log = _log(tmp_path, clock)
    out = kickoff(ctx, choice_index=2, log=log, interactive=False)

    assert "angle: Track 2: Core Framework Adapter Hardening" in out
    assert "first domino:" in out
    assert handshake(ctx) in out
    assert len(log.tail()) == 1  # exactly one entry, chosen angle only
    assert log.last()["choice"]["label"].startswith("Track 2")


def test_kickoff_custom_angle_is_free_text(ctx, tmp_path):
    log = _log(tmp_path, FakeClock())
    kickoff(ctx, custom="ship the alpha stream landing page", log=log)
    last = log.last()
    assert last["choice"]["label"] == "ship the alpha stream landing page"
    assert last["choice"]["custom"] is True


def test_kickoff_auto_resumes_last_angle(ctx, tmp_path):
    clock = FakeClock()
    log = _log(tmp_path, clock)
    kickoff(ctx, choice_index=3, log=log, interactive=False)
    clock.advance(5)
    out = kickoff(ctx, auto=True, log=log, interactive=False)

    assert "angle: Track 3: Distributed Web UI Bridge (GLM / External Agent)" in out
    assert len(log.tail()) == 2


def test_kickoff_auto_with_no_history_records_nothing(ctx, tmp_path, capsys):
    log = _log(tmp_path, FakeClock())
    out = kickoff(ctx, auto=True, log=log, interactive=False)
    assert "no angle chosen" in out
    assert log.last() is None


def test_kickoff_without_choice_is_menu_only_and_non_polluting(ctx, tmp_path):
    # Cron/CI safety: no TTY, no flags -> menu rendered, nothing recorded.
    log = _log(tmp_path, FakeClock())
    out = kickoff(ctx, log=log, interactive=False)
    assert "1) Track 1" in out
    assert "no angle chosen" in out
    assert log.last() is None


def test_kickoff_rejects_out_of_range_track(ctx, tmp_path):
    with pytest.raises(ValueError):
        kickoff(ctx, choice_index=99, log=_log(tmp_path, FakeClock()))


# ---------------------------------------------------------------------------
# Auto-boot plan
# ---------------------------------------------------------------------------
def test_boot_plan_reports_cron_workflow_state(ctx):
    # This checkout ships .github/workflows/scout_cron.yml, so the plan must
    # reflect the template's real state (dispatch-first, schedule off).
    plan = boot_plan(ctx)
    joined = "\n".join(plan)
    assert any(a.startswith("terminal_windows:") for a in plan)
    assert "cron_monitors: template present" in joined
    assert any(a.startswith("loom_knowledge_graph:") for a in plan)


def test_boot_plan_passes_unknown_keys_through():
    ctx = {"session_kickoff": {"auto_boot": ["mystery_future_stage"]}}
    plan = boot_plan(ctx)
    assert len(plan) == 1 and plan[0].startswith("mystery_future_stage:")


# ---------------------------------------------------------------------------
# User config install + CLI
# ---------------------------------------------------------------------------
def test_install_user_config_respects_existing(tmp_path, monkeypatch):
    user_dir = tmp_path / "freebuff"
    monkeypatch.setattr(cc, "USER_CONFIG_DIR", user_dir)
    monkeypatch.setattr(cc, "USER_CONFIG_PATH", user_dir / "cannibal_context.json")

    first = install_user_config()
    assert first.exists() and json.loads(first.read_text())["operator"] == "Mikey"

    # User edits outrank the packaged default: no clobber without force=True.
    first.write_text('{"operator": "Mikey-Edited"}')
    assert install_user_config().read_text() == '{"operator": "Mikey-Edited"}'
    assert install_user_config(force=True).read_text() != '{"operator": "Mikey-Edited"}'


def test_cli_kickoff_with_explicit_paths(ctx, tmp_path, capsys):
    cfg = tmp_path / "ctx.json"
    cfg.write_text(json.dumps(ctx))
    rc = cc.main(
        [
            "kickoff", "--track", "1",
            "--config", str(cfg),
            "--session-log", str(tmp_path / "s.jsonl"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "angle: Track 1: Monetization Ledger & Signal SKU" in out
    assert (tmp_path / "s.jsonl").exists()


def test_cli_handshake_prints_one_line(ctx, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CANNIBAL_CONTEXT", str(DEFAULT_CONFIG_PATH))
    monkeypatch.delenv("CANNIBAL_SESSIONS", raising=False)
    monkeypatch.setattr(cc, "DEFAULT_SESSIONS_PATH", tmp_path / "unused.jsonl")
    assert cc.main(["handshake"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == handshake(ctx)
    assert out.count("\n") == 0  # the bridge primitive is one line, always
