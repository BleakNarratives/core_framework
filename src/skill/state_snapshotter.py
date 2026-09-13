"""
MOLT Git-State Snapshotter — The Time Machine
Hooks into Whorl's Git-like versioning engine (~/.whorl/agents/) whenever
a MOLT skill mutates. Provides zero-downtime rollback on poisoned/corrupt
mutations.

Storage: mirrors Whorl agent_state layout but for MOLT skills under
~/.whorl/agents/molt-<skill>/ — or falls back to rag_storage/molt_state/<skill>/
if Whorl not installed. Same semantics: v1.json, v2.json, HEAD, branches.json.

Optimization goal: zero-downtime rollback capability.

Usage:
  from src.skill.state_snapshotter import StateSnapshotter
  snap = StateSnapshotter()
  snap.snapshot("saas-churn-oracle", {"frontmatter": front, "body_hash": "abc"})
  snap.rewind("saas-churn-oracle", to_version=1)

Hooked automatically by SkillManager.apply_mutation: snapshots before patch,
reverts if Oracle blocks post-check or tests fail.

See: Whorl/whorl/agent_state/__init__.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Try Whorl agent_state
_HAS_WHORL_STATE = False
_whorl_state = None
try:
    import whorl.agent_state as _whorl_state  # type: ignore
    _HAS_WHORL_STATE = True
except Exception:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Whorl"))
        import whorl.agent_state as _whorl_state  # type: ignore
        _HAS_WHORL_STATE = True
    except Exception:
        _HAS_WHORL_STATE = False

WHORL_AGENTS_DIR = Path.home() / ".whorl" / "agents"
FALLBACK_DIR = Path("rag_storage/molt_state")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _skill_agent_name(skill: str) -> str:
    # Namespace MOLT skills as molt-<skill> to avoid collision with Whorl agents
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in skill)[:40]
    return f"molt-{safe}"

def _fallback_dir(skill: str) -> Path:
    name = _skill_agent_name(skill)
    return FALLBACK_DIR / name

class StateSnapshotter:
    """
    Git-like versioning for MOLT Living Skills.
    Delegates to Whorl agent_state when available, else filesystem fallback.
    """

    def __init__(self, use_whorl: bool = True):
        self.use_whorl = use_whorl and _HAS_WHORL_STATE

    # ── Core ─────────────────────────────────────────────────────────
    def current(self, skill: str) -> Optional[Dict[str, Any]]:
        name = _skill_agent_name(skill)
        if self.use_whorl and _whorl_state is not None:
            try:
                return _whorl_state.current(name)
            except Exception:
                pass
        # fallback
        d = _fallback_dir(skill)
        head = d / "HEAD"
        if not head.exists():
            return None
        label = head.read_text().strip()
        vpath = d / f"{label}.json"
        if not vpath.exists():
            return None
        try:
            return json.loads(vpath.read_text())
        except Exception:
            return None

    def snapshot(self, skill: str, state: Dict[str, Any],
                 label: str = "", config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Commit a new version before mutation. Returns new state version dict.
        Called by SkillManager.apply_mutation before patch.
        At Instar 5 (Molt), snapshots are auto-branched for audit.
        """
        name = _skill_agent_name(skill)
        # Enrich state
        enriched = dict(state)
        enriched["_skill"] = skill
        enriched["_label"] = label[:60] if label else f"molt:{skill}"
        enriched["_ts"] = _now()

        if self.use_whorl and _whorl_state is not None:
            try:
                cur = _whorl_state.current(name)
                if cur is None:
                    # init
                    init = _whorl_state.init_agent(name, config=config or {"skill": skill})
                    # record first state as score
                    return _whorl_state.record_score(name, source="molt", detail=label or "init",
                                                     scores_update={"molt": enriched})
                else:
                    return _whorl_state.record_score(name, source="molt", detail=label[:60],
                                                     scores_update={"molt": enriched})
            except Exception:
                pass
        # fallback filesystem versioning (mirrors Whorl semantics)
        return self._fallback_commit(skill, enriched, label)

    def _fallback_commit(self, skill: str, state: Dict[str, Any], label: str) -> Dict[str, Any]:
        d = _fallback_dir(skill)
        d.mkdir(parents=True, exist_ok=True)
        head = d / "HEAD"
        branches = d / "branches.json"
        # Determine next version
        if head.exists():
            cur_label = head.read_text().strip()
            cur_path = d / f"{cur_label}.json"
            if cur_path.exists():
                try:
                    cur = json.loads(cur_path.read_text())
                    nxt = int(cur.get("version", 0)) + 1
                    parent = cur_label
                except Exception:
                    nxt = 1
                    parent = None
            else:
                nxt = 1
                parent = None
        else:
            nxt = 1
            parent = None
        versioned = {
            "version": nxt,
            "branch": "main",
            "parent": parent,
            "timestamp": _now(),
            "label": label[:60] if label else f"molt:{skill} v{nxt}",
            "skill": skill,
            "state": state,
            "history": [],
        }
        # carry history from parent
        if parent:
            try:
                par = json.loads((d / f"{parent}.json").read_text())
                versioned["history"] = par.get("history", []) + [{"at": _now(), "event": "molt_snapshot", "label": label[:40]}]
            except Exception:
                pass
        else:
            versioned["history"] = [{"at": _now(), "event": "molt_created", "label": label[:40]}]
        vl = f"v{nxt}"
        (d / f"{vl}.json").write_text(json.dumps(versioned, indent=2, default=str))
        head.write_text(vl)
        # branches
        try:
            b = json.loads(branches.read_text()) if branches.exists() else {}
        except Exception:
            b = {}
        b["main"] = vl
        branches.write_text(json.dumps(b, indent=2))
        return versioned

    def rewind(self, skill: str, to_version: int) -> Optional[Dict[str, Any]]:
        name = _skill_agent_name(skill)
        if self.use_whorl and _whorl_state is not None:
            try:
                return _whorl_state.rewind(name, to_version)
            except Exception:
                pass
        # fallback
        d = _fallback_dir(skill)
        target = f"v{to_version}"
        tpath = d / f"{target}.json"
        if not tpath.exists():
            raise ValueError(f"Version {target} not found for skill {skill}")
        (d / "HEAD").write_text(target)
        try:
            b = json.loads((d / "branches.json").read_text())
            b["main"] = target
            (d / "branches.json").write_text(json.dumps(b, indent=2))
        except Exception:
            pass
        return json.loads(tpath.read_text())

    def log(self, skill: str, limit: int = 10) -> List[Dict[str, Any]]:
        name = _skill_agent_name(skill)
        if self.use_whorl and _whorl_state is not None:
            try:
                return _whorl_state.log(name, limit=limit)
            except Exception:
                pass
        # fallback: walk parent chain
        d = _fallback_dir(skill)
        head = d / "HEAD"
        if not head.exists():
            return []
        label = head.read_text().strip()
        out = []
        while label and len(out) < limit:
            p = d / f"{label}.json"
            if not p.exists():
                break
            try:
                st = json.loads(p.read_text())
                out.append({"version": st.get("version"), "label": st.get("label"), "timestamp": st.get("timestamp")})
                label = st.get("parent") or ""
            except Exception:
                break
        return out

    def list_skills(self) -> List[str]:
        if self.use_whorl and _whorl_state is not None:
            try:
                agents = _whorl_state.list_agents()
                return [a[5:] for a in agents if a.startswith("molt-")]
            except Exception:
                pass
        if not FALLBACK_DIR.exists():
            return []
        return [p.name[5:] if p.name.startswith("molt-") else p.name for p in FALLBACK_DIR.iterdir() if p.is_dir()]

    def branch(self, skill: str, branch_name: str) -> Dict[str, Any]:
        name = _skill_agent_name(skill)
        if self.use_whorl and _whorl_state is not None:
            try:
                return _whorl_state.branch(name, branch_name)
            except Exception:
                pass
        # fallback: copy current version as branch
        d = _fallback_dir(skill)
        head = d / "HEAD"
        if not head.exists():
            raise ValueError(f"Skill {skill} not initialized")
        cur_label = head.read_text().strip()
        cur = json.loads((d / f"{cur_label}.json").read_text())
        nxt = int(cur.get("version", 0)) + 1
        branched = dict(cur)
        branched["version"] = nxt
        branched["branch"] = branch_name
        branched["parent"] = cur_label
        branched["label"] = f"branch:{branch_name}"
        branched["timestamp"] = _now()
        vl = f"v{nxt}"
        (d / f"{vl}.json").write_text(json.dumps(branched, indent=2, default=str))
        (d / "HEAD").write_text(f"branch:{branch_name}")
        try:
            b = json.loads((d / "branches.json").read_text()) if (d / "branches.json").exists() else {}
            b[branch_name] = vl
            (d / "branches.json").write_text(json.dumps(b, indent=2))
        except Exception:
            pass
        return branched

    def diff(self, skill: str, v1: int, v2: int) -> Dict[str, Any]:
        """Differential state history — for Scout audits."""
        name = _skill_agent_name(skill)
        s1 = self._read_version(skill, f"v{v1}")
        s2 = self._read_version(skill, f"v{v2}")
        if not s1 or not s2:
            return {"error": "version not found"}
        # naive diff: compare top-level keys
        keys = set(s1.get("state", {}).keys()) | set(s2.get("state", {}).keys())
        diffs = {}
        for k in keys:
            if s1.get("state", {}).get(k) != s2.get("state", {}).get(k):
                diffs[k] = {"v1": s1.get("state", {}).get(k), "v2": s2.get("state", {}).get(k)}
        return {"skill": skill, "v1": v1, "v2": v2, "changed_keys": list(diffs.keys()), "diff": diffs}

    def _read_version(self, skill: str, label: str) -> Optional[Dict[str, Any]]:
        # Whorl path
        name = _skill_agent_name(skill)
        if self.use_whorl and _whorl_state is not None:
            try:
                # _read_version is internal; use log walk fallback
                return _whorl_state._read_version(name, label)  # type: ignore
            except Exception:
                pass
        d = _fallback_dir(skill)
        p = d / f"{label}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except Exception:
            return None

    def rollback_on_failure(self, skill: str, before_version: int, reason: str) -> Optional[Dict[str, Any]]:
        """Convenience: rewind + annotate reason."""
        st = self.rewind(skill, before_version)
        # append rollback reason to log (best-effort)
        try:
            if self.use_whorl and _whorl_state is not None:
                _whorl_state.record_score(_skill_agent_name(skill), source="molt", detail=f"rollback: {reason[:40]}",
                                         scores_update={"rollback": {"reason": reason, "ts": _now()}})
        except Exception:
            pass
        return st
