"""
MOLT Whorl Bus Dispatcher — The Nervous System
Bridges MOLT inference_bridge / Scout / SkillManager to Whorl's filesystem bus
(~/.whorl/bus/) with 18 atomic message types + MOLT extensions.

Zero-network: atomic file writes, no sockets. Headless nodes (Termux, Chromebook,
desktop) consume Scout intelligence via filesystem without opening ports.

Architecture:
  [ Scout Engine ] ──(RAG Context)──► [ MOLT Triad ] ──(Atomic Write)──► [ Whorl Bus ]
                                         │                                  │
                                  (Instar Gate)                    (~/.whorl/bus/)
                                         ▼                                  ▼
  [ Loom Workflow ] ◄──(Version Commit)── [ Oracle ] ◄──(Logic Combat)─── [ Whorl Arena ]

Bus types (18 atomic + 4 MOLT extensions):
  agent.register / heartbeat / deregister
  task.dispatch / result / cancel / timeout
  state.update / query / response
  score.record / ack / drill.sweep_start / drill.sweep_done
  guard.check / status / restart / result
  + molt.hydrate / molt.sidecar / molt.mutation / molt.oracle_verdict

Optimization goals: latency minimization & zero-drop throughput.
- Latency: bus clock is monotonic, atomic rename exposes message instantly.
- Zero-drop: archive preservation + dead-letter + idempotent message_id.

Zero-bloat: if Whorl not installed or ~/.whorl missing, all methods degrade to
no-ops / local fallbacks. No exception leaks to MOLT callers.

Usage:
  from src.skill.whorl_bus import WhorlBusDispatcher
  bus = WhorlBusDispatcher(agent_name="molt-dispatcher")
  bus.register()
  bus.send_molt_hydrate("saas-churn-oracle", hydrated_chunk, oomf_level=3)
  bus.send_sidecar("saas-churn-oracle", sidecar_payload)
  msgs = bus.read("molt-dispatcher")

Headless consume (no network):
  msgs = bus.poll_inbox("molt-dispatcher")  # reads ~/.whorl/bus/inbox/molt-dispatcher/

See: Whorl/docs/AGENT_BUS_SPEC.md
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Try to import Whorl bus core if available (installed or Whorl/ in repo)
_HAS_WHORL_BUS = False
_whorl_bus = None  # module
_whorl_config = None
try:
    # Whorl lives at ./Whorl/whorl — add repo root to path is already done
    import whorl.bus as _whorl_bus  # type: ignore
    from whorl.core.config import WHORL_DIR as _WHORL_DIR  # type: ignore
    _HAS_WHORL_BUS = True
except Exception:
    try:
        # Fallback: Whorl as top-level import via path
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Whorl"))
        import whorl.bus as _whorl_bus  # type: ignore
        from whorl.core.config import WHORL_DIR as _WHORL_DIR  # type: ignore
        _HAS_WHORL_BUS = True
    except Exception:
        _HAS_WHORL_BUS = False
        _whorl_bus = None
        try:
            from pathlib import Path as _P
            _WHORL_DIR = _P(os.environ.get("WHORL_HOME", "~/.whorl")).expanduser()
        except Exception:
            _WHORL_DIR = Path.home() / ".whorl"

# 18 atomic bus types (canonical) + MOLT extensions
ATOMIC_TYPES = [
    "agent.register",
    "agent.heartbeat",
    "agent.deregister",
    "task.dispatch",
    "task.result",
    "task.cancel",
    "task.timeout",
    "state.update",
    "state.query",
    "state.response",
    "score.record",
    "score.ack",
    "drill.sweep_start",
    "drill.sweep_done",
    "guard.check",
    "guard.status",
    "guard.restart",
    "guard.result",
]

MOLT_TYPES = [
    "molt.hydrate",
    "molt.sidecar",
    "molt.mutation",
    "molt.oracle_verdict",
]

ALL_TYPES = ATOMIC_TYPES + MOLT_TYPES

# Bus dirs (mirrors Whorl/whorl/bus/__init__.py)
def _whorl_dir() -> Path:
    if _HAS_WHORL_BUS and _WHORL_DIR is not None:
        return Path(_WHORL_DIR)
    return Path(os.environ.get("WHORL_HOME", str(Path.home() / ".whorl"))).expanduser()

def _bus_dir() -> Path:
    return _whorl_dir() / "bus"

def _inbox_dir() -> Path:
    return _bus_dir() / "inbox"

def _dead_dir() -> Path:
    return _bus_dir() / "dead"

def _archive_dir() -> Path:
    return _bus_dir() / "archive"

def _log_file() -> Path:
    return _bus_dir() / "log" / "bus.jsonl"

def _clock_file() -> Path:
    return _bus_dir() / "clock"

def _registry_file() -> Path:
    return _bus_dir() / "registry.json"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)

def _append(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")

def _next_clock() -> int:
    p = _clock_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        v = int(p.read_text().strip())
    except Exception:
        v = 0
    v += 1
    _atomic_text(p, f"{v}\n")
    return v

def _load_registry() -> Dict[str, Any]:
    p = _registry_file()
    try:
        raw = json.loads(p.read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}

class WhorlBusDispatcher:
    """
    Nervous system: bridges MOLT → Whorl bus via atomic filesystem writes.
    Latency minimization: single clock increment + single atomic rename.
    Zero-drop: archive on ack, dead-letter on unknown recipient, idempotent IDs.
    """

    def __init__(self, agent_name: str = "molt-dispatcher",
                 whorl_dir: Optional[str] = None,
                 auto_register: bool = True,
                 version: str = "1.0.0",
                 capabilities: Optional[List[str]] = None,
                 dedupe_guard: Optional[Any] = None):
        self.agent_name = agent_name
        self.whorl_dir = Path(whorl_dir).expanduser() if whorl_dir else _whorl_dir()
        self.version = version
        self.capabilities = capabilities or [
            "molt.hydrate", "molt.sidecar", "molt.mutation",
            "task.dispatch", "task.result", "score.record",
        ]
        # Optional loop guard (DuplicateCallGuard); None keeps sends unchanged.
        self.dedupe_guard = dedupe_guard
        self._available: Optional[bool] = None
        if auto_register:
            try:
                self.register()
            except Exception:
                pass

    # ── Availability ─────────────────────────────────────────────────
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        # Check if bus dir exists or can be created
        try:
            _bus_dir().mkdir(parents=True, exist_ok=True)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def status(self) -> Dict[str, Any]:
        reg = _load_registry()
        return {
            "whorl_dir": str(self.whorl_dir),
            "bus_dir": str(_bus_dir()),
            "available": self.is_available(),
            "has_whorl_bus": _HAS_WHORL_BUS,
            "agent": self.agent_name,
            "registered": self.agent_name in reg,
            "registry_size": len(reg),
            "types": len(ALL_TYPES),
        }

    # ── Registry ─────────────────────────────────────────────────────
    def register(self, version: Optional[str] = None, capabilities: Optional[List[str]] = None,
                 heartbeat_s: int = 60) -> Dict[str, Any]:
        caps = capabilities or self.capabilities
        ver = version or self.version
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                return _whorl_bus.register(self.agent_name, ver, capabilities=caps, heartbeat_s=heartbeat_s)
            except Exception:
                pass
        # Fallback: direct registry.json write (mirrors whorl.bus.register)
        _bus_dir().mkdir(parents=True, exist_ok=True)
        reg = _load_registry()
        now = _now()
        entry = reg.get(self.agent_name, {})
        entry.update({
            "name": self.agent_name,
            "version": ver,
            "config": {},
            "capabilities": caps,
            "heartbeat_s": heartbeat_s,
            "registered_at": entry.get("registered_at", now),
            "last_heartbeat": now,
            "status": "active",
        })
        reg[self.agent_name] = entry
        _atomic_text(_registry_file(), json.dumps(reg, indent=2, sort_keys=True) + "\n")
        _append(_log_file(), {"event": "agent_register", "ts": now, "agent": entry})
        return entry

    def heartbeat(self, status: str = "active", uptime_s: float = 0) -> Dict[str, Any]:
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                return _whorl_bus.heartbeat(self.agent_name, status=status, uptime_s=uptime_s)
            except Exception:
                pass
        reg = _load_registry()
        if self.agent_name not in reg:
            return self.register()
        reg[self.agent_name].update({"last_heartbeat": _now(), "status": status, "uptime_s": uptime_s})
        _atomic_text(_registry_file(), json.dumps(reg, indent=2, sort_keys=True) + "\n")
        _append(_log_file(), {"event": "agent_heartbeat", "ts": _now(), "agent": self.agent_name, "status": status})
        return reg[self.agent_name]

    def ensure_recipient(self, recipient: str, version: str = "1.0.0") -> None:
        """Ensure recipient is registered so send doesn't dead-letter."""
        if recipient == "broadcast":
            return
        reg = _load_registry()
        if recipient not in reg:
            # Auto-register as passive consumer
            _bus_dir().mkdir(parents=True, exist_ok=True)
            now = _now()
            reg[recipient] = {
                "name": recipient, "version": version, "config": {},
                "capabilities": [], "heartbeat_s": 60,
                "registered_at": now, "last_heartbeat": now, "status": "active",
            }
            _atomic_text(_registry_file(), json.dumps(reg, indent=2, sort_keys=True) + "\n")

    # ── Core send (18 types) ──────────────────────────────────────────
    def send(self, recipient: str, message_type: str, payload: Dict[str, Any],
             priority: str = "normal", ttl_s: int = 300,
             reply_to: Optional[str] = None, message_id: Optional[str] = None) -> Dict[str, Any]:
        if message_type not in ALL_TYPES:
            # Allow custom molt.* but warn
            if not message_type.startswith("molt.") and message_type not in ATOMIC_TYPES:
                raise ValueError(f"Unknown bus type: {message_type}. Must be one of {ALL_TYPES}")
        if self.dedupe_guard is not None:
            sig = hashlib.sha256(
                f"{recipient}|{message_type}|{json.dumps(payload, sort_keys=True, default=str)}".encode()
            ).hexdigest()[:16]
            verdict = self.dedupe_guard.check(sig)
            if verdict.get("action") == "block":
                # Audited drop, never silent: the guard logged the verdict and
                # the bus log records the blocked dispatch (AGENTS.md §3/§5).
                self._deposit_to_bus_log("message_dedup_blocked",
                                         f"{message_type}->{recipient}", sig, 0)
                return {"id": message_id or f"msg_dedup_{sig}",
                        "timestamp": _now(), "from": self.agent_name,
                        "to": recipient, "type": message_type,
                        "dedup_blocked": True, "dedup": verdict, "payload": payload}
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                # Whorl bus validates recipient — ensure it's registered first
                self.ensure_recipient(recipient)
                return _whorl_bus.send(self.agent_name, recipient, message_type, payload,
                                       priority=priority, ttl_s=ttl_s, reply_to=reply_to, message_id=message_id)
            except Exception as e:
                # Fall through to fallback
                pass
        # Fallback: filesystem write directly
        return self._send_fallback(recipient, message_type, payload, priority, ttl_s, reply_to, message_id)

    def _send_fallback(self, recipient: str, message_type: str, payload: Dict[str, Any],
                       priority: str, ttl_s: int, reply_to: Optional[str], message_id: Optional[str]) -> Dict[str, Any]:
        _bus_dir().mkdir(parents=True, exist_ok=True)
        # Idempotency: check inbox/archive/dead for existing ID
        if message_id:
            for root in (_inbox_dir(), _archive_dir(), _dead_dir()):
                try:
                    for p in root.glob(f"**/*_{message_id}.json"):
                        try:
                            rec = json.loads(p.read_text())
                            return rec.get("message", rec) if isinstance(rec, dict) else rec
                        except Exception:
                            continue
                except Exception:
                    continue
        msg = {
            "id": message_id or f"msg_{uuid.uuid4().hex}",
            "timestamp": _now(),
            "clock": _next_clock(),
            "from": self.agent_name,
            "to": recipient,
            "type": message_type,
            "priority": priority,
            "ttl_s": int(ttl_s),
            **({"reply_to": reply_to} if reply_to else {}),
            "payload": payload,
        }
        reg = _load_registry()
        known = recipient == "broadcast" or recipient in reg
        if not known:
            # Dead-letter
            path = _dead_dir() / f"{msg['clock']:020d}_{msg['id']}.json"
            rec = {"reason": "recipient_not_registered", "dead_lettered_at": _now(), "message": msg}
            _atomic_text(path, json.dumps(rec, sort_keys=True) + "\n")
            _append(_log_file(), {"event": "message_dead_lettered", "ts": _now(), **rec})
            return msg
        target = _inbox_dir() / recipient
        target.mkdir(parents=True, exist_ok=True)
        filename = f"{msg['clock']:020d}_{msg['id']}.json"
        _atomic_text(target / filename, json.dumps(msg, sort_keys=True) + "\n")
        _append(_log_file(), {"event": "message_delivered", "ts": _now(), "message": msg})
        return msg

    # ── MOLT-specific shims ───────────────────────────────────────────
    def send_molt_hydrate(self, skill: str, hydrated_chunk: str, oomf_level: int = 3,
                          recipients: Optional[List[str]] = None,
                          ttl_s: int = 300) -> List[Dict[str, Any]]:
        """Broadcast hydrated prompt chunk so headless nodes can hydrate without network."""
        recips = recipients or ["broadcast"]
        out = []
        for r in recips:
            payload = {
                "skill": skill,
                "oomf_level": oomf_level,
                "hydrated_bytes": len(hydrated_chunk),
                "hydrated_preview": hydrated_chunk[:800],
                "hydrated_hash": __import__("hashlib").sha256(hydrated_chunk.encode()).hexdigest()[:12],
                "ts": time.time(),
            }
            # Also persist preview to bus log for observability
            out.append(self.send(r, "molt.hydrate", payload, ttl_s=ttl_s))
        # Atomic bus deposit of full chunk for offline consumers that read bus log
        self._deposit_to_bus_log("molt.hydrate", skill, hydrated_chunk, oomf_level)
        return out

    def send_sidecar(self, skill: str, sidecar_payload: Dict[str, Any],
                     recipient: str = "broadcast", ttl_s: int = 600) -> Dict[str, Any]:
        payload = {"skill": skill, **sidecar_payload}
        msg = self.send(recipient, "molt.sidecar", payload, ttl_s=ttl_s)
        self._deposit_to_bus_log("molt.sidecar", skill, json.dumps(sidecar_payload)[:2000], 0)
        return msg

    def send_mutation(self, skill: str, mutation: Dict[str, Any],
                      oracle_verdict: Optional[Dict[str, Any]] = None,
                      recipient: str = "broadcast") -> Dict[str, Any]:
        payload = {"skill": skill, "mutation": mutation, "oracle": oracle_verdict or {}}
        return self.send(recipient, "molt.mutation", payload)

    def _deposit_to_bus_log(self, event_type: str, skill: str, preview: str, oomf: int) -> None:
        """Append to bus log for headless consumers that tail bus.jsonl without inbox."""
        try:
            _append(_log_file(), {
                "event": event_type,
                "ts": _now(),
                "agent": self.agent_name,
                "skill": skill,
                "oomf": oomf,
                "preview": preview[:400],
            })
        except Exception:
            pass

    # ── Read / Ack (zero-drop) ────────────────────────────────────────
    def read(self, recipient: Optional[str] = None, limit: int = 50,
             include_expired: bool = False) -> List[Dict[str, Any]]:
        rec = recipient or self.agent_name
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                return _whorl_bus.read(rec, limit=limit, include_expired=include_expired)
            except Exception:
                pass
        # Fallback: read inbox files directly
        inbox = _inbox_dir() / rec
        try:
            paths = sorted(inbox.glob("*.json"), key=lambda p: p.name)[:limit]
        except Exception:
            return []
        out = []
        for p in paths:
            try:
                msg = json.loads(p.read_text())
                # Simple TTL check (only if not include_expired)
                if not include_expired:
                    try:
                        ts = __import__("datetime").datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00")).timestamp()
                        if time.time() > ts + int(msg.get("ttl_s", 300)):
                            continue
                    except Exception:
                        pass
                out.append(msg)
            except Exception:
                continue
        return out

    def acknowledge(self, recipient: str, message_id: str) -> bool:
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                return _whorl_bus.acknowledge(recipient, message_id)
            except Exception:
                pass
        # Fallback: move inbox -> archive
        inbox = _inbox_dir() / recipient
        try:
            matches = list(inbox.glob(f"*_{message_id}.json"))
            if not matches:
                return False
            src = matches[0]
            dst = _archive_dir() / recipient / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(src, dst)
            except OSError as e:
                if getattr(e, "errno", None) != 18:
                    raise
                _atomic_text(dst, src.read_text())
                src.unlink()
            _append(_log_file(), {"event": "message_acknowledged", "ts": _now(), "recipient": recipient, "message_id": message_id})
            return True
        except Exception:
            return False

    def poll_inbox(self, recipient: Optional[str] = None, limit: int = 50,
                   auto_ack: bool = False) -> List[Dict[str, Any]]:
        """Read inbox; optionally auto-ack after read (zero-drop requires explicit ack by default)."""
        rec = recipient or self.agent_name
        msgs = self.read(rec, limit=limit)
        if auto_ack:
            for m in msgs:
                self.acknowledge(rec, m["id"])
        return msgs

    def dead_letters(self, limit: int = 50, reason: Optional[str] = None) -> List[Dict[str, Any]]:
        if _HAS_WHORL_BUS and _whorl_bus is not None:
            try:
                return _whorl_bus.dead_letters(reason=reason, limit=limit)
            except Exception:
                pass
        out = []
        for p in sorted(_dead_dir().glob("*.json")):
            try:
                rec = json.loads(p.read_text())
                if reason and rec.get("reason") != reason:
                    continue
                out.append(rec)
                if len(out) >= limit:
                    break
            except Exception:
                continue
        return out

    # ── Scout focus: monitor bus for payload events ───────────────────
    def monitor_bus(self, recipients: Optional[List[str]] = None, limit: int = 100) -> Dict[str, Any]:
        """Scout optimization goal: latency minimization & zero-drop throughput report."""
        recips = recipients or [self.agent_name]
        total = 0
        inbox_counts = {}
        for r in recips:
            msgs = self.read(r, limit=limit)
            inbox_counts[r] = len(msgs)
            total += len(msgs)
        dead = self.dead_letters(limit=20)
        # Measure clock latency (next clock increment time)
        t0 = time.time()
        try:
            _next_clock()
            clock_latency_ms = (time.time() - t0) * 1000
        except Exception:
            clock_latency_ms = -1
        return {
            "whorl_dir": str(self.whorl_dir),
            "recipients": inbox_counts,
            "total_inbox": total,
            "dead_letters": len(dead),
            "clock_latency_ms": round(clock_latency_ms, 2),
            "zero_drop": len(dead) == 0,
            "bus_log": str(_log_file()),
        }

    # ── 18-type dispatcher helpers ────────────────────────────────────
    def dispatch_task(self, recipient: str, task_id: str, prompt: str, **kwargs) -> Dict[str, Any]:
        return self.send(recipient, "task.dispatch", {"task_id": task_id, "prompt": prompt, **kwargs})

    def result_task(self, recipient: str, task_id: str, result: str, status: str = "success") -> Dict[str, Any]:
        return self.send(recipient, "task.result", {"task_id": task_id, "result": result, "status": status})

    def emit_score(self, recipient: str, agent_id: str, score: float, scenario_id: str = "molt") -> Dict[str, Any]:
        return self.send(recipient, "score.record", {"agent_id": agent_id, "score": float(score), "scenario_id": scenario_id})
