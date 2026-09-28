"""
Governor — Privilege & Safety Control
Enforces strict user authorization for Triad mutations.
Session-scoped privilege escalation, CLI flags (--oomf, --elevate), TUI prompts.
"""
import time
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import json

# Allowed privilege scopes
VALID_SCOPES = {"read", "write", "network", "exec"}
# Oracle auto-approval policies (mode -> auto-approve scopes)
AUTO_APPROVAL = {
    "strict": set(),  # nothing auto-approved
    "permissive": {"read"},
    "user_only": set(),
}


@dataclass
class PrivilegeSession:
    """Single session-scoped elevation grant."""
    session_id: str
    scopes: set
    granted_at: float
    expires_at: float
    reason: str
    granted_by: str  # "user" | "oracle:auto" | "cli:--elevate"

    def is_active(self) -> bool:
        return time.time() < self.expires_at

    def has(self, scope: str) -> bool:
        return self.is_active() and scope in self.scopes


class Governor:
    """
    Security gate managing CLI flags (--oomf, --elevate), user approvals, TUI prompts.

    Zero-bloat: all methods are no-ops unless explicitly elevated. Existing CLI tools
    (Vibe, Codebuff, Gemini, VS Code) see no change unless they pass --elevate / --oomf.
    """

    SESSION_TTL_SECONDS = 3600  # 1h default session

    def __init__(self, audit_path: str = "rag_storage/governor_audit.jsonl"):
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, PrivilegeSession] = {}
        self._active_session: Optional[str] = None

    # ── CLI flag parsing (zero-bloat) ────────────────────────────────────
    @staticmethod
    def parse_cli_flags(argv: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Parse --oomf / --elevate from argv without breaking other tools.
        Returns dict with keys: oomf_level (1-5 or None), elevate (bool), elevate_scopes.
        Ignores unknown flags.
        """
        import argparse
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--oomf", type=int, default=None, choices=range(1, 6),
                            help="OOMF level 1-5 (scout depth)")
        parser.add_argument("--elevate", nargs="*", default=None,
                            metavar="SCOPE",
                            help="Elevate privileges: read/write/network/exec (no arg = all)")
        parser.add_argument("--elevate-ttl", type=int, default=None,
                            help="Elevation TTL seconds (default 3600)")
        # Unknown args are ignored — critical for zero-bloat
        try:
            known, _ = parser.parse_known_args(argv)
        except SystemExit:
            return {"oomf_level": None, "elevate": False, "elevate_scopes": set(), "elevate_ttl": None}

        oomf = known.oomf
        elevate_raw = known.elevate
        if elevate_raw is None:
            elevate = False
            scopes = set()
        elif len(elevate_raw) == 0:
            elevate = True
            scopes = set(VALID_SCOPES)
        else:
            # filter to valid scopes
            scopes = set(s.lower() for s in elevate_raw if s.lower() in VALID_SCOPES)
            elevate = len(scopes) > 0

        return {
            "oomf_level": oomf,
            "elevate": elevate,
            "elevate_scopes": scopes,
            "elevate_ttl": known.elevate_ttl,
        }

    # ── Session lifecycle ────────────────────────────────────────────────
    def request_elevation(self, scopes: set, reason: str = "",
                          granted_by: str = "user",
                          ttl: Optional[int] = None,
                          require_confirmation: bool = True,
                          auto_confirm: bool = False) -> str:
        """
        Create a session-scoped elevation. If require_confirmation and not auto_confirm,
        caller must call confirm_elevation(). For tests / CLI --elevate, use auto_confirm=True.
        Returns session_id.
        """
        unknown = scopes - VALID_SCOPES
        if unknown:
            raise ValueError(f"Unknown scopes: {unknown}. Valid: {VALID_SCOPES}")
        sid = hashlib.sha256(f"{time.time()}-{scopes}-{reason}".encode()).hexdigest()[:12]
        ttl = ttl or self.SESSION_TTL_SECONDS
        sess = PrivilegeSession(
            session_id=sid,
            scopes=set(scopes),
            granted_at=time.time(),
            expires_at=time.time() + ttl,
            reason=reason,
            granted_by=granted_by,
        )
        # If confirmation required and not auto-confirmed, stash as pending
        if require_confirmation and not auto_confirm:
            # Store but mark as pending — is_active still false until confirmed
            # We model pending as not yet active by setting expires_at in future but flagging
            sess.expires_at = -1  # sentinel for pending
            self._sessions[sid] = sess
            self._audit("elevation_requested", {"session_id": sid, "scopes": list(scopes), "reason": reason})
            return sid
        self._sessions[sid] = sess
        self._active_session = sid
        self._audit("elevation_granted", {"session_id": sid, "scopes": list(scopes), "reason": reason, "by": granted_by, "ttl": ttl})
        return sid

    def confirm_elevation(self, session_id: str, ttl: Optional[int] = None) -> bool:
        """User explicitly confirms a pending elevation (TUI prompt)."""
        sess = self._sessions.get(session_id)
        if not sess:
            return False
        if sess.expires_at != -1:
            return False  # not pending
        ttl = ttl or self.SESSION_TTL_SECONDS
        sess.expires_at = time.time() + ttl
        sess.granted_at = time.time()
        self._active_session = session_id
        self._audit("elevation_confirmed", {"session_id": session_id})
        return True

    def deny_elevation(self, session_id: str, reason: str = "") -> bool:
        sess = self._sessions.pop(session_id, None)
        if not sess:
            return False
        self._audit("elevation_denied", {"session_id": session_id, "reason": reason})
        if self._active_session == session_id:
            self._active_session = None
        return True

    def oracle_auto_approve(self, oracle_mode: str, requested_scopes: set, reason: str = "") -> Optional[str]:
        """
        Oracle may auto-approve only whitelisted scopes per mode.
        Returns session_id if auto-approved, else None.
        """
        allowed = AUTO_APPROVAL.get(oracle_mode, set())
        if not requested_scopes.issubset(allowed):
            self._audit("oracle_auto_deny", {"mode": oracle_mode, "requested": list(requested_scopes), "allowed": list(allowed)})
            return None
        return self.request_elevation(requested_scopes, reason=f"oracle:auto:{reason}", granted_by="oracle:auto", require_confirmation=False, auto_confirm=True)

    def revoke(self, session_id: Optional[str] = None) -> None:
        sid = session_id or self._active_session
        if not sid:
            return
        self._sessions.pop(sid, None)
        self._audit("elevation_revoked", {"session_id": sid})
        if self._active_session == sid:
            self._active_session = None

    def revoke_all(self) -> None:
        for sid in list(self._sessions.keys()):
            self.revoke(sid)

    # ── Checks ───────────────────────────────────────────────────────────
    def is_elevated(self, scope: str, session_id: Optional[str] = None) -> bool:
        """Check if scope is currently elevated."""
        if scope not in VALID_SCOPES:
            return False
        sid = session_id or self._active_session
        if not sid:
            return False
        sess = self._sessions.get(sid)
        if not sess:
            return False
        return sess.has(scope)

    def require(self, scope: str, session_id: Optional[str] = None) -> None:
        """Raise PermissionError if not elevated."""
        if not self.is_elevated(scope, session_id):
            raise PermissionError(
                f"Governor: '{scope}' requires elevation. "
                f"Pass --elevate {scope} or request_elevation({{'{scope}'}}). "
                f"Active session: {self._active_session}. "
                f"See src/skill/governor.py"
            )

    def check_mutation_allowed(self, mutation: Dict[str, Any], oracle_verdict: Dict[str, Any]) -> bool:
        """
        Gate a Scout mutation: requires appropriate elevation based on mutation ops.
        - file writes need 'write'
        - network fetches need 'network'
        - code exec needs 'exec'
        Oracle strict mode never auto-approves writes.
        """
        ops = mutation.get("ops", [])
        needs = set()
        for op in ops:
            t = op.get("type", "")
            if t in ("write", "patch", "update_frontmatter"):
                needs.add("write")
            if t == "fetch":
                needs.add("network")
            if t in ("exec", "run"):
                needs.add("exec")
        if not needs:
            return True  # read-only mutation
        # Oracle verdict must be pass
        if oracle_verdict.get("verdict") != "pass":
            self._audit("mutation_blocked_oracle", {"needs": list(needs), "verdict": oracle_verdict.get("verdict")})
            return False
        # Check elevation for each needed scope
        for scope in needs:
            if not self.is_elevated(scope):
                self._audit("mutation_blocked_privilege", {"missing_scope": scope})
                return False
        return True

    # ── TUI helper ───────────────────────────────────────────────────────
    @staticmethod
    def tui_prompt(scopes: set, reason: str) -> bool:
        """
        Simple terminal prompt for elevation. Returns True if user confirms.
        Non-interactive (no tty) returns False — caller must use --elevate.
        """
        import sys
        if not sys.stdin.isatty():
            return False
        print(f"\n[Governor] Elevation requested: {', '.join(sorted(scopes))}")
        print(f"  Reason: {reason}")
        try:
            ans = input("  Approve? [y/N]: ").strip().lower()
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Helpers ──────────────────────────────────────────────────────────
    def active_scopes(self) -> set:
        if not self._active_session:
            return set()
        sess = self._sessions.get(self._active_session)
        if not sess or not sess.is_active():
            return set()
        return set(sess.scopes)

    def pending_sessions(self) -> List[str]:
        return [sid for sid, s in self._sessions.items() if s.expires_at == -1]

    def _audit(self, event: str, data: Dict[str, Any]) -> None:
        entry = {"ts": time.time(), "event": event, **data}
        try:
            with open(self.audit_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # audit is best-effort

    # ── Headless Overseer → Governor integration ─────────────────────
    def audit_to_overseer(self, whorl_dir: str = "~/.whorl") -> Dict[str, Any]:
        """Expose Governor audit + session TTL to the Whorl Overseer daemon.
        The Overseer sweeps across CLI tools while MOLT stays zero-bloat.
        No daemon started — just atomic audit log read + bus heartbeat.
        """
        import os
        from pathlib import Path as _P
        wd = _P(whorl_dir).expanduser()
        bus_dir = wd / "bus"
        audit_lines = 0
        last_event = None
        try:
            if self.audit_path.exists():
                lines = self.audit_path.read_text().strip().splitlines()
                audit_lines = len(lines)
                if lines:
                    import json as _j
                    try:
                        last_event = _j.loads(lines[-1])
                    except Exception:
                        last_event = {"raw": lines[-1][:120]}
        except Exception:
            pass
        # Derived stale/dead like Whorl bus registry_status
        active = self.active_scopes()
        return {
            "whorl_dir": str(wd),
            "bus_dir": str(bus_dir),
            "governor_audit": str(self.audit_path),
            "audit_lines": audit_lines,
            "last_event": last_event,
            "active_session": self._active_session,
            "active_scopes": sorted(active) if isinstance(active, set) else list(active),
            "pending": len(self.pending_sessions()),
            "overseer_rules": str(_P("~/Overseer/rules.json").expanduser()),
        }

    def heartbeat_to_bus(self, agent_name: str = "molt-governor") -> Optional[Dict[str, Any]]:
        """Push a bus heartbeat so Overseer can monitor session TTLs without polling audit log."""
        try:
            from .whorl_bus import WhorlBusDispatcher
            bus = WhorlBusDispatcher(agent_name=agent_name, auto_register=True)
            scopes = self.active_scopes()
            return bus.heartbeat(status="active" if scopes else "idle",
                                 uptime_s=time.time() - (min(s.granted_at for s in self._sessions.values()) if self._sessions else time.time()))
        except Exception:
            return None

    # For tests: inject fixed time
    def _set_active_for_test(self, sid: str) -> None:
        self._active_session = sid


# ── Dispatch guards ────────────────────────────────────────────────────
# Salvaged from an external "Cub-Apex" proposal and rebuilt to repo
# invariants: bounded memory, every verdict audited, nothing suppressed
# silently. See docs/DISPATCH_GUARDS_SPEC.md.


def _audit_event(audit_path: Path, event: str, data: Dict[str, Any]) -> None:
    entry = {"ts": time.time(), "event": event, **data}
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # audit is best-effort, matching Governor._audit


class DuplicateCallGuard:
    """Bounded duplicate-call detector for tool/dispatch loops.

    Trust boundary: this is a signal gate, not a silent filter. Every flagged or
    blocked verdict is written to the audit log. The default action_on_loop is
    "flag" (pass the call through, record the verdict); "block" is opt-in for
    callers that own their retry semantics, and a blocked attempt is still
    audited. Memory is bounded twice: per-signature events expire after
    window_s, and the number of tracked signatures is capped.

    Callers whose repeats are legitimate (polling, retry after a state change)
    must vary the signature — include the attempt or state in it — so the guard
    sees distinct work rather than a loop.
    """

    MAX_SIGNATURES = 256

    def __init__(self, window_s: float = 60.0, max_duplicates: int = 1,
                 action_on_loop: str = "flag",
                 audit_path: str = "rag_storage/governor_audit.jsonl",
                 clock=None):
        if action_on_loop not in ("flag", "block"):
            raise ValueError("action_on_loop must be 'flag' or 'block'")
        if window_s <= 0 or max_duplicates < 0:
            raise ValueError("window_s must be > 0 and max_duplicates >= 0")
        self.window_s = float(window_s)
        self.max_duplicates = int(max_duplicates)
        self.action_on_loop = action_on_loop
        self.audit_path = Path(audit_path)
        self._clock = clock or time.time
        self._events: Dict[str, List[float]] = {}

    def check(self, signature: str) -> Dict[str, Any]:
        """Record one call attempt and return a verdict.

        Verdict: {signature, count, duplicate, exceeded, action, window_s}.
        action: "allow" (first sight) | "flag" (duplicate seen) | "block"
        (loop beyond tolerance, only when action_on_loop="block").
        """
        now = float(self._clock())
        window = [t for t in self._events.get(signature, []) if now - t <= self.window_s]
        window.append(now)
        # Refresh insertion order so hot signatures are evicted last.
        self._events.pop(signature, None)
        self._events[signature] = window
        while len(self._events) > self.MAX_SIGNATURES:
            self._events.pop(next(iter(self._events)))
        count = len(window)
        if count == 1:
            return {"signature": signature[:16], "count": 1, "duplicate": False,
                    "exceeded": False, "action": "allow"}
        exceeded = count > 1 + self.max_duplicates
        action = "block" if (exceeded and self.action_on_loop == "block") else "flag"
        verdict = {"signature": signature[:16], "count": count, "duplicate": True,
                   "exceeded": exceeded, "action": action, "window_s": self.window_s}
        _audit_event(self.audit_path,
                     "duplicate_call_blocked" if action == "block" else "duplicate_call_flagged",
                     verdict)
        return verdict

    def tracked_signatures(self) -> int:
        return len(self._events)


class SingleCheckRule:
    """"Rule of Single Check" — one meaningful verification per subject state.

    Re-running the identical check against an identical subject cannot change
    the answer; that is loop waste, not verification. The subject_digest scopes
    the check to the state being verified: a changed digest (code modified)
    legitimately re-opens it. Flagged rechecks are audited and reported — the
    rule never pretends a skipped check ran, and never refuses a human asking
    for a re-run (AGENTS.md §3: the user is the authority); it makes the
    repetition visible in the audit trail instead.
    """

    MAX_TRACKED = 256

    def __init__(self, ttl_s: float = 86400.0,
                 audit_path: str = "rag_storage/governor_audit.jsonl",
                 clock=None):
        if ttl_s <= 0:
            raise ValueError("ttl_s must be > 0")
        self.ttl_s = float(ttl_s)
        self.audit_path = Path(audit_path)
        self._clock = clock or time.time
        # check_id -> (subject state, last run ts); bounded below.
        self._seen: Dict[str, Any] = {}

    def should_run(self, check_id: str, subject_digest: str = "") -> Dict[str, Any]:
        """Return {run, reason} and record the attempt.

        reason: "first_check" | "subject_changed" | "ttl_elapsed" (run: true)
        or "identical_check_on_identical_state" (run: false, audited).
        """
        state = subject_digest or "unscoped"
        now = float(self._clock())
        entry = self._seen.get(check_id)
        if entry is not None:
            last_state, last_ts = entry
            if last_state == state and now - last_ts <= self.ttl_s:
                verdict = {"check_id": check_id, "subject_digest": state[:16],
                           "run": False, "reason": "identical_check_on_identical_state"}
                _audit_event(self.audit_path, "recheck_flagged", verdict)
                return verdict
            reason = "subject_changed" if last_state != state else "ttl_elapsed"
        else:
            reason = "first_check"
        self._seen.pop(check_id, None)
        self._seen[check_id] = (state, now)
        while len(self._seen) > self.MAX_TRACKED:
            self._seen.pop(next(iter(self._seen)))
        return {"check_id": check_id, "subject_digest": state[:16],
                "run": True, "reason": reason}

    def record_result(self, check_id: str, subject_digest: str = "", result: str = "") -> None:
        _audit_event(self.audit_path, "verification_check",
                     {"check_id": check_id, "subject_digest": (subject_digest or "unscoped")[:16],
                      "result": str(result)[:200]})
