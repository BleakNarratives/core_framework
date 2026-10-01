#!/usr/bin/env python3
"""
Cui Bono Regulator — a pre-action decision gate for agents.

"Cui bono?" — who benefits? An agent can produce a fluent, confident action that
serves momentum (or its own drift) rather than the project's stated goal. This
module scores a proposed action on two axes and returns a structured verdict:

  * Utility — does it serve an explicit, declared goal?
  * Risk    — could it break the 595-test green baseline, destroy uncommitted
              state, or is it irreversible?

Contract returned by `evaluate()`: a `CuiBonoVerdict` with `verdict`
(ALLOW / REDIRECT / BLOCK), `reasoning` (why), and `redirect_action` (a safer
alternative when one exists).

Trust boundary: this module is **PURE**. It performs no I/O, runs no command,
and touches no repository. It is an advisor, not an enforcement point — a BLOCK
here is a recommendation the caller (or a commit gate) must honour. Observed
state (dirty tree, tests touched, human approval) is passed IN by the caller so
the decision is deterministic and unit-testable. The only impure helper is
`repo_signals()`, which is read-only.

Usage:
    from tools.guard.cui_bono_regulator import evaluate
    v = evaluate({"command": "git reset --hard", "uncommitted_state": True})
    if not v.allowed:
        print(v.verdict, v.reasoning, v.redirect_action)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict, replace
from typing import Any, Dict, List, Optional, Union

ALLOW = "ALLOW"
REDIRECT = "REDIRECT"
BLOCK = "BLOCK"

# ── risk catalog ─────────────────────────────────────────────────
# (regex, weight, label, safer redirect or None). Matched against the lowercased
# action text. Weights are additive and clamped, not a probability.
IRREVERSIBLE = (
    (r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r", 0.6,
     "recursive/forced delete destroys files", "move the path into an archive dir instead of deleting"),
    (r"\bgit\s+reset\s+--hard\b", 0.6,
     "hard reset discards uncommitted work", "git stash --include-untracked"),
    (r"\bgit\s+clean\s+-[a-z]*[fd]", 0.6,
     "git clean deletes untracked files", "git clean -n (dry run first)"),
    (r"\bgit\s+push\b(?![^\n]*--force-with-lease)[^\n]*--force\b", 0.5,
     "force push rewrites remote history", "git push --force-with-lease"),
    (r"\bdrop\s+table\b", 0.6, "drops a database table", "rename the table, drop it after a backup"),
    (r"\btruncate\b", 0.5, "truncates data in place", None),
    (r"\bmkfs\b|\bdd\s+if=", 0.7, "raw disk write", None),
    (r"\b(shutdown|reboot|poweroff)\b", 0.6, "host power change", None),
)

# Actions that mutate tests are what can break the green baseline; merely
# *running* tests is safe and must not be penalised (closure runs pytest).
TEST_REF = re.compile(r"\btests?/|\btest_[a-z0-9_]+\.py\b|\bpytest\b|\bunittest\b")
SECRET_REF = re.compile(r"\bvault\.json\b|\.env\b|credential|(?<![a-z])_key\b|\.key\b|\bsecret\b|\btoken\b")
WRITE_OP = re.compile(r"\brm\b|\bmv\b|\bchmod\b|\bchown\b|\btruncate\b|\bdelete\b|>\s*|\bgit\s+(reset|clean|push|commit|checkout|rebase)\b")
NETWORK_OP = re.compile(r"\bcurl\b|\bwget\b|\bpip\s+install\b|\bnpm\s+i(nstall)?\b|\bgit\s+push\b|\bssh\b")

# Language that signals momentum or drift rather than a stated goal.
DRIFT_REF = re.compile(
    r"\brefactor\s+everything\b|\boptimize\s+all\b|\bclean\s+up\s+everything\b|"
    r"\bwhile\s+we'?re\s+at\s+it\b|\bjust\s+in\s+case\b|\bnice\s+to\s+have\b|"
    r"\bgeneral\s+cleanup\b|\btidy\s+up\s+the\s+codebase\b|\bmake\s+it\s+better\b"
)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True)
class CuiBonoVerdict:
    """Structured decision contract."""
    verdict: str
    reasoning: List[str]
    redirect_action: Optional[str]
    utility: float
    risk: float

    @property
    def allowed(self) -> bool:
        return self.verdict == ALLOW

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:  # concise one-liner for logs
        tail = f" -> {self.redirect_action}" if self.redirect_action else ""
        return f"[{self.verdict}] u={self.utility} r={self.risk}{tail}"


def _normalize(payload: Union[str, Dict[str, Any]], overrides: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, str):
        data: Dict[str, Any] = {"command": payload}
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        raise TypeError("payload must be a command string or a dict")
    data.update(overrides)
    return data


def evaluate(payload: Union[str, Dict[str, Any]], **overrides: Any) -> CuiBonoVerdict:
    """Score one proposed action. Pure: no I/O, deterministic.

    Payload keys (all optional except an action):
      command/action : str  — the command or description under evaluation
      goal           : str  — the explicit project goal this serves, if any
      serves_goal    : bool — caller's own utility judgement
      reversible     : bool — caller asserts the action is reversible
      touches_tests  : bool — the change modifies behaviour tests cover
      uncommitted_state : bool — the working tree is dirty (from repo_signals)
      human_approval : bool — a human has explicitly authorised it
      metadata       : dict — ignored, carried for callers

    Overrides are merged over the payload (keywords win).
    """
    data = _normalize(payload, overrides)
    command = str(data.get("command") or data.get("action") or "")
    text = command.lower()

    # ── utility ──────────────────────────────────────────────────
    utility = 0.5
    util_reasons: List[str] = []
    goal = (data.get("goal") or "").strip()
    serves = data.get("serves_goal")
    if goal:
        utility += 0.4
        util_reasons.append(f"serves a declared goal: {goal!r}")
    if serves is True:
        utility += 0.2
        util_reasons.append("caller marks it goal-serving")
    elif serves is False:
        utility -= 0.3
        util_reasons.append("caller marks it NOT goal-serving")
    if not goal and serves is None:
        utility -= 0.2
        util_reasons.append("no declared goal (drift risk)")
    if DRIFT_REF.search(text):
        utility -= 0.4
        util_reasons.append("momentum/drift language, not a stated objective")
    if data.get("reversible") is True:
        utility += 0.05
    utility = round(_clamp(utility), 2)

    # ── risk ─────────────────────────────────────────────────────
    risk = 0.1
    risk_reasons: List[str] = []
    redirect: Optional[str] = None
    for pattern, weight, label, alt in IRREVERSIBLE:
        if re.search(pattern, text):
            risk += weight
            risk_reasons.append(label)
            if alt and redirect is None:
                redirect = alt

    refs_tests = bool(TEST_REF.search(text))
    if data.get("touches_tests") or (refs_tests and WRITE_OP.search(text)):
        risk += 0.4
        risk_reasons.append("changes behaviour the test suite covers")

    if data.get("uncommitted_state") and WRITE_OP.search(text):
        risk += 0.3
        risk_reasons.append("mutates a dirty working tree (uncommitted state at risk)")

    if SECRET_REF.search(text) and WRITE_OP.search(text):
        risk += 0.5
        risk_reasons.append("mutates credential-shaped files")

    if NETWORK_OP.search(text):
        risk += 0.2
        risk_reasons.append("contacts the network or installs")

    if data.get("human_approval") is True:
        risk -= 0.5
        risk_reasons.append("explicit human approval present")
    risk = round(_clamp(risk), 2)

    # ── decision ─────────────────────────────────────────────────
    if risk >= 0.7 and utility < 0.5:
        verdict = BLOCK
    elif utility < 0.4:
        verdict = REDIRECT
        if redirect is None:
            redirect = "restate the explicit goal this action serves before running it"
    elif risk >= 0.4:
        verdict = REDIRECT
    else:
        verdict = ALLOW

    reasoning = util_reasons + risk_reasons
    if not risk_reasons:
        reasoning.append("no irreversible or test-breaking pattern detected")
    reasoning.append(
        f"utility={utility}, risk={risk} -> {verdict}"
    )
    return CuiBonoVerdict(verdict=verdict, reasoning=reasoning,
                          redirect_action=redirect, utility=utility, risk=risk)


def _tribunal_preflight(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort call into the existing Tribunal preflight guardrails.

    Tribunal (`~/tribunal/guardrails.py::preflight_check`) already detects
    dangerous operations before an agent runs them. We do not reimplement it:
    this composes it so the regulator is the single pre-execution entry point.
    A missing or broken Tribunal is degraded, not fatal — the local rules in
    `evaluate()` still apply.
    """
    try:
        import importlib
        import os
        import sys
        tdir = os.path.expanduser("~/tribunal")
        if os.path.isdir(tdir) and tdir not in sys.path:
            sys.path.insert(0, tdir)
        guardrails = importlib.import_module("guardrails")
        return guardrails.preflight_check(text)
    except Exception:
        return None


def evaluate_pre_execution(payload: Union[str, Dict[str, Any]], **overrides: Any) -> CuiBonoVerdict:
    """The pre-execution regulator used by the gateway loop.

    Composes the Tribunal ``preflight_check`` (known-dangerous operations) with
    the local utility/risk scoring in :func:`evaluate`, and returns one contract.
    Tribunal hard-blocks win outright; an elevated Tribunal risk downgrades an
    otherwise-ALLOW to REDIRECT so the operation gets a second look.
    """
    verdict = evaluate(payload, **overrides)
    data = _normalize(payload, overrides)
    command = str(data.get("command") or data.get("action") or "")
    tf = _tribunal_preflight(command)
    if not tf:
        return verdict

    issues = [str(i.get("message", "")) for i in tf.get("issues", []) if i.get("message")]
    if tf.get("should_block"):
        return replace(
            verdict, verdict=BLOCK, redirect_action=None,
            reasoning=verdict.reasoning + issues + ["tribunal preflight: dangerous operation"],
        )
    if tf.get("risk_level") in ("high", "critical") and verdict.verdict == ALLOW:
        return replace(
            verdict, verdict=REDIRECT,
            redirect_action=verdict.redirect_action or "review the flagged operation before running it",
            reasoning=verdict.reasoning + issues + ["tribunal preflight: elevated risk"],
        )
    return verdict


def repo_signals(cwd: Optional[str] = None) -> Dict[str, Any]:
    """Read-only observation to feed `evaluate` (impure but side-effect-free).

    Returns {"uncommitted_state": bool}. Never raises: an unreadable repo yields
    an empty dict so a caller simply gets less signal, not a crash.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ("git", "status", "--porcelain"), cwd=cwd,
            capture_output=True, text=True, timeout=10,
        )
        return {"uncommitted_state": bool(proc.stdout.strip())}
    except Exception:
        return {}


if __name__ == "__main__":  # tiny CLI for a manual sanity check
    import json
    import sys
    action = " ".join(sys.argv[1:]) or "git status"
    print(json.dumps(evaluate(action).to_dict(), indent=2))
