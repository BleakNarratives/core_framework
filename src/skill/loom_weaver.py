"""
MOLT Loom Thread Weaver — The Choreographer
Stitches one-shot MOLT prompt injections into multi-step, asynchronous
Loom execution workflows. Tracks execution traces and agent states across
long-running background tasks.

Scout focus: execution traces + agent states across background tasks.
Optimization goal: context continuity across complex multi-step pipelines.

Uses Whorl Loom (Whorl/whorl/loom/) when available — falls back to a
lightweight local file workflow log at rag_storage/loom/<workflow>.json
so MOLT works without Whorl.

Weaver patterns:
  weave(workflow_id, steps) -> runs steps as a fiber chain, persisting
    each step's input/output to Loom DB + Whorl bus + state snapshotter.
  chain(skill, prompts) -> hydrate once per step, keep context continuity
    via sidecar + bus.

See: Whorl/whorl/loom/__init__.py, Whorl/docs/SIGNAL_LOOM.md
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import whorl.loom as _whorl_loom  # type: ignore
    _HAS_WHORL_LOOM = True
except Exception:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "Whorl"))
        import whorl.loom as _whorl_loom  # type: ignore
        _HAS_WHORL_LOOM = True
    except Exception:
        _HAS_WHORL_LOOM = False
        _whorl_loom = None  # type: ignore

LOOM_DIR = Path("rag_storage/loom")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text)
    import os
    os.replace(tmp, path)

class LoomThreadWeaver:
    """
    Choreographer: takes one-shot MOLT skills and weaves them into
    async multi-step pipelines with trace persistence.
    """

    def __init__(self, bus: Optional[Any] = None, snapshotter: Optional[Any] = None):
        self.bus = bus  # WhorlBusDispatcher or None
        self.snapshotter = snapshotter
        LOOM_DIR.mkdir(parents=True, exist_ok=True)
        # Lazy import state_snapshotter
        if self.snapshotter is None:
            try:
                from .state_snapshotter import StateSnapshotter
                self.snapshotter = StateSnapshotter()
            except Exception:
                self.snapshotter = None

    def weave(self, workflow_id: Optional[str] = None,
              steps: Optional[List[Dict[str, Any]]] = None,
              skill: Optional[str] = None,
              prompts: Optional[List[str]] = None,
              bus_broadcast: bool = True) -> Dict[str, Any]:
        """
        Weave a workflow. Two call styles:
          weaver.weave(workflow_id="triage-42", steps=[{skill, prompt, oomf}, ...])
          weaver.weave(skill="med-triage-copilot", prompts=[p1, p2, p3])  # sugar
        Each step: hydrate -> (optional bus deposit) -> optional inference (dry_run by default).
        Returns {workflow_id, steps, traces, status}.
        """
        if skill and prompts is not None:
            # sugar: chain same skill across prompts
            steps = [{"skill": skill, "prompt": p, "oomf": 3} for p in prompts]
            workflow_id = workflow_id or f"molt-chain-{skill[:12]}-{uuid.uuid4().hex[:6]}"
        if not workflow_id:
            workflow_id = f"molt-weave-{uuid.uuid4().hex[:8]}"
        if not steps:
            raise ValueError("weave requires steps or (skill + prompts)")

        traces: List[Dict[str, Any]] = []
        ctx_digest = ""  # chained context hash for continuity

        for idx, step in enumerate(steps, start=1):
            sk = step.get("skill") or skill or "unknown"
            prompt = step.get("prompt") or step.get("query") or ""
            oomf = int(step.get("oomf") or step.get("oomf_level") or 3)
            dry_run = bool(step.get("dry_run", True))  # default no network

            # Hydrate (in-process, no API)
            hydrated = ""
            hydrate_err = None
            try:
                from .skill_manager import SkillManager
                mgr = SkillManager()
                hydrated = mgr.hydrate(sk, oomf_level=oomf, max_chars=step.get("max_chars", 6000))
                # Chain digest for continuity
                ctx_digest = hashlib.sha256((ctx_digest + hydrated[:2000]).encode()).hexdigest()[:12]
            except Exception as e:
                hydrate_err = str(e)
                hydrated = f"[hydrate error: {e}]"

            trace = {
                "step": idx,
                "workflow_id": workflow_id,
                "skill": sk,
                "oomf": oomf,
                "prompt_preview": prompt[:200],
                "hydrated_preview": hydrated[:600],
                "ctx_digest": ctx_digest,
                "dry_run": dry_run,
                "error": hydrate_err,
                "ts": _now(),
            }

            # Optional: deposit to Whorl bus so headless nodes can resume
            if bus_broadcast and self.bus is not None:
                try:
                    self.bus.send_molt_hydrate(sk, hydrated, oomf_level=oomf, recipients=["broadcast"])
                    self.bus.dispatch_task("loom-worker", task_id=f"{workflow_id}:{idx}",
                                           prompt=prompt, skill=sk, oomf=oomf)
                    trace["bus"] = "dispatched"
                except Exception as e:
                    trace["bus_error"] = str(e)[:120]

            # Optional: snapshot state pre-step (for rewind on failure)
            if self.snapshotter is not None and hasattr(step, "get") and step.get("snapshot"):
                try:
                    self.snapshotter.snapshot(sk, {"step": idx, "workflow": workflow_id}, label=f"weave:{workflow_id}:{idx}")
                    trace["snapshotted"] = True
                except Exception:
                    pass

            # Optional: live inference if dry_run=False and backend available
            if not dry_run:
                try:
                    from .inference_bridge import molt_one_shot
                    out = molt_one_shot(sk, prompt, oomf_level=oomf, dry_run=False)
                    trace["result_preview"] = str(out)[:800]
                except Exception as e:
                    trace["inference_error"] = str(e)[:200]

            traces.append(trace)

        # Persist weave
        weave_record = {
            "workflow_id": workflow_id,
            "steps": steps,
            "traces": traces,
            "status": "complete",
            "ctx_digest": ctx_digest,
            "created_at": _now(),
        }
        self._persist(workflow_id, weave_record)

        # If Whorl Loom available, register as a LoomWeave topology too
        if _HAS_WHORL_LOOM and _whorl_loom is not None:
            try:
                # Persist to Whorl DB as a qrd-like blink
                _whorl_loom.scan(str(LOOM_DIR))  # no-op topology
            except Exception:
                pass

        return weave_record

    def chain(self, skill: str, prompts: List[str], oomf: int = 3,
              workflow_id: Optional[str] = None) -> Dict[str, Any]:
        """Sugar for weave(skill=..., prompts=...) with context continuity."""
        return self.weave(workflow_id=workflow_id, skill=skill, prompts=prompts)

    def _persist(self, workflow_id: str, record: Dict[str, Any]) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in workflow_id)[:48]
        path = LOOM_DIR / f"{safe}.json"
        _atomic_text(path, json.dumps(record, indent=2, default=str))
        return path

    def load(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in workflow_id)[:48]
        path = LOOM_DIR / f"{safe}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def list_workflows(self) -> List[str]:
        if not LOOM_DIR.exists():
            return []
        return [p.stem for p in LOOM_DIR.glob("*.json")]

    def resume(self, workflow_id: str, extra_prompts: List[str]) -> Dict[str, Any]:
        """Resume a workflow with additional prompts (continuity via ctx_digest)."""
        loaded = self.load(workflow_id)
        if not loaded:
            raise ValueError(f"workflow not found: {workflow_id}")
        # Infer skill from last trace
        last_skill = loaded["traces"][-1]["skill"] if loaded["traces"] else "unknown"
        extra_steps = [{"skill": last_skill, "prompt": p, "oomf": 3} for p in extra_prompts]
        # Append traces
        extended = self.weave(workflow_id=workflow_id, steps=loaded["steps"] + extra_steps)
        return extended

    def report(self, workflow_id: str) -> str:
        loaded = self.load(workflow_id)
        if not loaded:
            return f"workflow not found: {workflow_id}"
        lines = [f"# Weave {workflow_id} — {loaded['status']}", f"Steps: {len(loaded['traces'])}  Digest: {loaded['ctx_digest']}"]
        for t in loaded["traces"]:
            preview = t.get("prompt_preview", "")[:50]
            lines.append(f"  {t['step']}. {t['skill']} (oomf {t['oomf']}) — {preview}… digest {t['ctx_digest']}")
        return "\n".join(lines)
