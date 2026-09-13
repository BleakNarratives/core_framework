"""
Sovereign Bridges — the two junctions the prompt asks to wire first.

1) Implor → Thoth (Introspect → Orchestrate)
   Symmetric: `mplore_thoth_bridge` — Implor repo scan → ContextPacket → Thoth bus →
   MotherBrain → synthesis.

2) Merkaba → Claw (Route → Execute)
   `merkaba_claw_bridge` — zero-latency IPC: Merkaba Ka/Ba → Whorl bus →
   agent_bus → OpenClaw shell.

Also:
  Akasha vault ops  — `akasha_vault` crypto-signed store + Journal commits
  Endempts gate     — `endempts_gate` lifecycle boundary + termination

All bridges degrade without their subsystem; none assumes elevation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

RECURSIVE_DIR = Path.home() / "RootBase" / "logs" / "shared" / "recursive_engine"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:12]

# ── 1) Implor → Thoth ────────────────────────────────────────────────
def implor_scan(codebase: str = ".", limit: int = 80) -> Dict[str, Any]:
    """Run Implor RepoWalker + ProfileBuilder deep scan (no-op if Implor absent)."""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "Implore" / "app"))
        from implore_scanner_walker import RepoWalker  # type: ignore
        from implore_scanner_profile import ProfileBuilder  # type: ignore
        walker = RepoWalker(codebase)
        builder = ProfileBuilder()
        scanned = 0
        for fp in walker.walk():
            fp_str = str(fp)
            # normalize: RepoWalker may yield str or Path; ProfileBuilder needs a path with .suffix
            try:
                builder.update_with_file(fp_str)
            except AttributeError:
                # older builder expects Path with .suffix — pass Path
                builder.update_with_file(Path(fp_str))  # type: ignore[arg-type]
            scanned += 1
            if scanned >= limit:
                break
        prof = builder.get_profile()
        return {"scanned_files": scanned, "profile_keys": list(prof.keys())[:20], "profile_preview": json.dumps(prof, default=str)[:1500], "source": "implor"}
    except Exception as e:
        return {"error": str(e)[:300], "source": "implor_unavailable"}

def implor_to_thoth_packet(codebase: str = ".", goal: str = "molt recursive refinement",
                           project_id: str = "molt-sovereign") -> Dict[str, Any]:
    """
    Wire 1 of 2 (the recommended first): Implor → Thoth's synthesis engine.
    - Implor scans codebase → profile
    - Akasha ContextPacket is built (evidence-hashed, bounded)
    - Thoth packet hits agent_bus; MotherBrain soon ingests it.
    Returns the packet dict + bus event id.
    """
    scan = implor_scan(codebase)
    out: Dict[str, Any] = {"scan": scan, "ts": _now()}
    # Build Akasha packet
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "Akasha"))
        from akasha.packet import ContextPacket  # type: ignore
        pkt = ContextPacket(
            project_id=project_id,
            goal=goal,
            constraints=["agency_is_leased", "no_source_delete", "oracle_strict"],
            allowed_operations=["read", "list_tree", "write:src/", "run:test"],
            open_dissent=[],
            known_failures=[],
        )
        pkt.add_source(f"implor:{_hash(json.dumps(scan, default=str))}")
        pkt.seal()
        out["packet_id"] = pkt.packet_id
        out["context_window"] = pkt.context_window(max_chars=1200)
        # Persist packet for Akasha ledger
        p = RECURSIVE_DIR / f"packet_{_hash(str(pkt.packet_id))}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(pkt.to_json())
        out["packet_path"] = str(p)
    except Exception as e:
        out["packet_error"] = str(e)[:300]

    # Thoth bus emit
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path.home() / "thoth_orchestrator"))
        import agent_bus  # type: ignore
        evt = agent_bus.emit_event(
            "molt.implor.packet",
            {"goal": goal, "project_id": project_id, "packet_id": out.get("packet_id", ""), "scan_files": scan.get("scanned_files", 0)},
            source="implor", channel="molt", tags=["introspect", "implor->thoth"],
        )
        out["thoth_event_id"] = evt.get("event_id")
        # Eager MotherBrain tick so prediction/decision for this packet fires promptly
        try:
            from motherbrain import MotherBrain  # type: ignore
            mb = MotherBrain()
            tick = mb.tick()
            out["motherbrain_tick"] = {"analysis_keys": list(tick.get("analysis", {}).keys())[:6], "decisions": tick.get("decisions", [])[:2]}
        except Exception:
            pass
    except Exception as e:
        out["thoth_bus_error"] = str(e)[:300]
    out["wire"] = "implor->thoth"
    return out

# ── 2) Merkaba → Claw ────────────────────────────────────────────────
def merkaba_generate_ka(intent: str, scope_in: Optional[List[str]] = None,
                        scope_out: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate a Merkaba Ka (execution contract) from intent via ka_gen.py template."""
    try:
        ka_gen = Path.home() / "Merkaba" / "ka_gen.py"
        if not ka_gen.exists():
            return {"error": "ka_gen.py not found", "intent": intent}
        import subprocess as _sp
        import yaml as _yaml
        ba = {
            "name": f"molt-merkle-{_hash(intent)}",
            "version": "0.1.0",
            "intent": intent,
            "success_criteria": ["oracle:pass", "tests:pass", "ship_or_kill resolved"],
            "scope": {"in": scope_in or ["src/skill", "src/sovereign"], "out": scope_out or ["~", "~/.config"], "boundaries": ["scope_is_law", "no_orphan_code"]},
            "requires": ["oracle", "governor"],
            "metadata": {"status": "ship", "intent_hash": _hash(intent)},
        }
        tmp_ba = Path("/tmp") / f"molt_{_hash(intent)}.ba.yaml"
        tmp_ba.write_text(_yaml.safe_dump(ba))
        # ka_gen has import-time PyYAML requirement; ensure we surface validation result too
        # Validate Ba first
        validator = Path.home() / "Merkaba" / "validator.py"
        val_ok = None
        if validator.exists():
            try:
                vr = _sp.run(["python3", str(validator), str(tmp_ba)], capture_output=True, text=True, timeout=15)
                val_ok = vr.returncode == 0
            except Exception:
                pass
        out = {"ba_path": str(tmp_ba), "intent": intent, "ba_validation_ok": val_ok, "scope": ba["scope"]}
        # Try ka generation
        try:
            kr = _sp.run(["python3", str(ka_gen), str(tmp_ba)], capture_output=True, text=True, timeout=20)
            out["ka_gen_stdout"] = kr.stdout[:1200]
            out["ka_gen_returncode"] = kr.returncode
            # ka_gen writes a .ka.yaml alongside Ba
            ka_path = tmp_ba.with_suffix("").with_suffix(".ka.yaml")
            if ka_path.exists():
                out["ka_path"] = str(ka_path)
        except Exception as e:
            out["ka_error"] = str(e)[:300]
        return out
    except Exception as e:
        return {"error": str(e)[:300]}

def merkaba_claw_bridge(intent: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Wire 2 of 2: expose Open Claw execution paths to the Merkaba bus.
    Zero-latency IPC: Merkaba Ka → Whorl bus + agent_bus → OpenClaw shell.

    `intent` is the same one used for Ka synthesis; `payload` is the staged
    mutation package from RecursiveEngine Phase 2 (patch_plan).
    """
    out: Dict[str, Any] = {"intent": intent, "ts": _now(), "wire": "merkaba->claw"}
    ka = merkaba_generate_ka(intent)
    out["ka"] = ka
    # Whorl bus transport of the routed Ka
    try:
        from src.skill.whorl_bus import WhorlBusDispatcher  # type: ignore
        bus = WhorlBusDispatcher(agent_name="merkaba-claw", auto_register=False)
        bus.send("openclaw", "task.dispatch", {"ka_intent": intent, "payload": payload or {}, "ka_ba": ka.get("ba_path", "")}, ttl_s=600)
        out["whorl_bus_sent"] = True
    except Exception as e:
        out["whorl_bus_error"] = str(e)[:300]
    # agent_bus (Thoth's bus) parallel deposit
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path.home() / "thoth_orchestrator"))
        import agent_bus  # type: ignore
        evt = agent_bus.emit_event("molt.merkaba.route", {"intent": intent, "ka_ba": ka.get("ba_path", "")}, source="merkaba", channel="molt")
        out["agent_bus_event_id"] = evt.get("event_id")
    except Exception as e:
        out["agent_bus_error"] = str(e)[:300]
    # OpenClaw low-level execution endpoint (OutClaw/Ox) — staged, not silent
    try:
        # Light probe: does OutClaw wrapper exist?
        claw = Path.home() / "OutClaw" / "OllamaWrapper" / "client.py"
        if claw.exists():
            out["claw_endpoint"] = str(claw)
            out["claw_status"] = "available (staged — awaiting --elevate exec to apply patch)"
        else:
            out["claw_endpoint"] = "OutClaw not mounted — execution degrades to SkillManager.apply_mutation"
    except Exception:
        pass
    return out

# ── Akasha vault + Endempts gate ─────────────────────────────────────
def akasha_store_evidence(content: str, tags: Optional[List[str]] = None,
                          metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """akasha-mutation-vault: git-backed, crypto-signed evidence store."""
    try:
        import sys
        sys.path.insert(0, str(Path.home() / "Akasha"))
        from akasha.vault import Vault  # type: ignore
        vault = Vault()
        obj_id = vault.store(content, metadata=metadata or {}, tags=tags or ["molt", "mutation"])
        return {"object_id": obj_id, "backend": "akasha.vault"}
    except Exception as e:
        # Fallback: content-addressed store in rag_storage/molt_state/vault/
        try:
            d = RECURSIVE_DIR / "akasha_fallback"
            d.mkdir(parents=True, exist_ok=True)
            h = _hash(content)
            obj = {"object_id": f"object:sha256:{h}", "tags": tags or [], "metadata": metadata or {}, "ts": _now()}
            (d / f"{h}.json").write_text(json.dumps({"object": obj, "content": content[:4000]}, indent=2))
            return {"object_id": obj["object_id"], "backend": "fallback", "path": str(d / f"{h}.json")}
        except Exception as e2:
            return {"error": str(e)[:300], "fallback_error": str(e2)[:200]}

def endempts_gate(cycle_record: Dict[str, Any], kill_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Endempts boundary & termination: SHIP / HOLD / KILL + safe process cleanup.
    `cycle_record` is a CycleRecord.to_dict(); we respect its gate/violations.
    """
    gate = cycle_record.get("validate", {}).get("gate", "HOLD")
    out: Dict[str, Any] = {"gate": gate, "cycle_id": cycle_record.get("cycle_id", ""), "ts": _now()}
    if gate == "SHIP":
        out["action"] = "commit"
        out["cleanup"] = "leave_execution_space_intact"
    elif gate == "HOLD":
        violations = cycle_record.get("validate", {}).get("violations", [])
        out["action"] = "hold_for_review"
        out["violations"] = violations[:5]
    else:  # KILL / FAILED
        out["action"] = "kill_and_cleanup"
        if kill_file and Path(kill_file).exists():
            try:
                Path(kill_file).unlink()
                out["killed_file"] = kill_file
            except Exception as e:
                out["kill_error"] = str(e)[:200]
    # Emit to bus for audit
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path.home() / "thoth_orchestrator"))
        import agent_bus  # type: ignore
        agent_bus.emit_event("molt.endempts.gate", {"gate": gate, "cycle_id": cycle_record.get("cycle_id","")}, source="endempts", channel="molt")
    except Exception:
        pass
    return out
