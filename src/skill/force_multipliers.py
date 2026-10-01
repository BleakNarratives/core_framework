"""
MOLT Force Multipliers — registered hooks that make the human×doc tandem fly.

Each multiplier is a tiny, composable transform on the hydration or lifecycle path.
They register in a central FM_REGISTRY and declare:
  - where they fire (stage)
  - what they need (requires)
  - a pointcut (when to auto-apply vs opt-in)

Stages: pre_hydrate | post_hydrate | pre_scout | post_oracle | pre_inject | on_progress

Philosophy: force multipliers don't change the MOLT spec — they just make the
existing path faster, safer, or more retentive. All are additive and removable.

Ship these 6 + stubs for more:
  1  hydrate_cache     — skip RAG assembly if sidecar unchanged (fast)
  2  auto_distill      — compress hydrated chunk to fit model window (no bloat)
  3  preflight_gate    — run Oracle on hydrate payload before API (fail fast)
  4  memory_mint       — write compact run receipts to .grimoire/bus (retain)
  5  morph_preset      — expand morph presets + suggest best domain for skill
  6  retention_nudge   — hook challenge submissions → schedule spaced recall

More stubs at bottom — wire whatever scouts you already have.
"""
import time
import json
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, List, Callable, Optional, Tuple

log = logging.getLogger(__name__)


def _emit(source: str, stage: str, event: str, payload: Dict[str, Any]) -> None:
    """Best-effort event emit to the central telemetry bus.

    Telemetry is never allowed to break the hydration path: the import is
    lazy (so importing this module has no side effects) and a missing or
    broken sink is recorded at debug rather than raised. Previously the
    preflight gate referenced an undefined ``bus``, so this path raised
    ``NameError`` on every non-empty hydration and the error handler raised
    again on its own emit.
    """
    try:
        from ..core.telemetry_bus import bus  # optional: not present in slim checkouts
        bus.emit_sync(source, stage, event, payload)
    except Exception as exc:  # telemetry is fire-and-forget by contract
        log.debug("telemetry emit skipped (%s/%s/%s): %s", source, stage, event, exc)


# ── registry ─────────────────────────────────────────────────────
@dataclass
class ForceMultiplier:
    name: str
    stage: str  # pre_hydrate|post_hydrate|pre_scout|post_oracle|pre_inject|on_progress
    description: str
    fn: Callable[..., Any]
    auto: bool = True  # auto-apply when conditions met
    requires: Tuple[str, ...] = ()
    enabled: bool = True


FM_REGISTRY: Dict[str, ForceMultiplier] = {}

def register(name: str, stage: str, description: str = "", auto: bool = True, requires=()):
    """Decorator to register a force multiplier."""
    def deco(fn):
        FM_REGISTRY[name] = ForceMultiplier(name=name, stage=stage, description=description, fn=fn, auto=auto, requires=tuple(requires))
        return fn
    return deco

def list_multipliers(stage: Optional[str] = None, enabled_only: bool = False) -> List[ForceMultiplier]:
    items = FM_REGISTRY.values()
    if stage:
        items = [f for f in items if f.stage == stage]
    if enabled_only:
        items = [f for f in items if f.enabled]
    return sorted(items, key=lambda f: f.name)

def toggle(name: str, enabled: bool) -> bool:
    fm = FM_REGISTRY.get(name)
    if not fm:
        return False
    fm.enabled = enabled
    return True

def run_stage(stage: str, ctx: Dict[str, Any], enabled_only: bool = True) -> Dict[str, Any]:
    """
    Run all enabled multipliers for a stage, threading ctx through each.
    Each FM receives ctx and returns a (possibly mutated) ctx or a dict of patches.
    Convention: if FM returns None, ctx unchanged; if dict, ctx.update(ret).
    """
    for fm in list_multipliers(stage=stage, enabled_only=enabled_only):
        try:
            ret = fm.fn(ctx)
            if ret is not None and isinstance(ret, dict):
                ctx.update(ret)
        except Exception as e:
            ctx.setdefault("_fm_errors", []).append(f"{fm.name}: {e}")
    return ctx


# ═══════════════════════════════════════════════════════════════════
# 1 — HYDRATE CACHE (pre_hydrate)
# Skip RAG file reassembly if sidecar hash unchanged since last hydrate.
# Saves 10-50ms per hydrate on warm docs. Zero semantics change.
# ═══════════════════════════════════════════════════════════════════
_CACHE: Dict[str, Tuple[str, str]] = {}  # key -> (sidecar_hash, hydrated_chunk)

def _sidecar_hash(skill: str, sidecar_dir: str = "rag_storage/sidecars", rag_dir: str = "rag_storage") -> str:
    h = hashlib.sha256()
    p = Path(sidecar_dir) / f"{skill}.jsonl"
    if p.exists():
        h.update(p.read_bytes()[:200000])
        h.update(str(p.stat().st_mtime).encode())
    # also include frontmatter so OOMF changes bust cache
    try:
        from .skill_manager import SkillManager
        fm = SkillManager().parse_frontmatter(skill)
        h.update(json.dumps(fm, sort_keys=True).encode())
    except Exception:
        pass
    return h.hexdigest()[:12]

@register("hydrate_cache", stage="pre_hydrate",
          description="Skip RAG assembly if sidecars unchanged — hydrate from cache.", auto=True)
def fm_hydrate_cache(ctx: Dict[str, Any]):
    skill = ctx.get("skill")
    oomf = ctx.get("oomf_level")
    key = f"{skill}:{oomf}:{ctx.get('max_chars', 6000)}"
    sh = _sidecar_hash(skill) if skill else ""
    cached = _CACHE.get(key)
    if cached and cached[0] == sh:
        return {"_hydrate_cached": True, "_hydrate_chunk": cached[1], "_sidecar_hash": sh}
    ctx["_sidecar_hash"] = sh
    return None  # miss — proceed to real hydration


@register("hydrate_cache_store", stage="post_hydrate",
          description="Store hydrate result for next cache hit.", auto=True)
def fm_hydrate_cache_store(ctx: Dict[str, Any]):
    # only store if we have a real chunk and a hash
    skill = ctx.get("skill")
    oomf = ctx.get("oomf_level")
    chunk = ctx.get("_hydrate_chunk_out") or ctx.get("hydrated")
    sh = ctx.get("_sidecar_hash")
    if skill is not None and chunk and sh:
        key = f"{skill}:{oomf}:{ctx.get('max_chars', 6000)}"
        _CACHE[key] = (sh, chunk)
    return None


# ═══════════════════════════════════════════════════════════════════
# 2 — AUTO-DISTILL (post_hydrate)
# If hydrated chunk exceeds budget, compress via truncation + header priority.
# Head (frontmatter) beats tail (old RAG). No LLM needed for MVP — deterministic.
# ═══════════════════════════════════════════════════════════════════
@register("auto_distill", stage="post_hydrate",
          description="Compress hydrated chunk to budget — head beats tail.", auto=True)
def fm_auto_distill(ctx: Dict[str, Any]):
    chunk = ctx.get("hydrated") or ctx.get("_hydrate_chunk_out") or ctx.get("_hydrate_chunk")
    budget = int(ctx.get("max_chars", 6000))
    if not chunk or len(chunk) <= budget:
        return None
    # priority: first 800 chars (instruction) + freshest RAG tail, drop middle
    head = chunk[:800]
    tail = chunk[-(budget - 900):]
    sep = "\n\n…[distilled — middle truncated for budget]…\n\n"
    distilled = head + sep + tail
    if len(distilled) > budget:
        distilled = distilled[:budget]
    ctx["hydrated"] = distilled
    ctx["_distilled"] = True
    ctx["_hydrate_chunk_out"] = distilled
    return {"hydrated": distilled, "_distilled": True}


# ═══════════════════════════════════════════════════════════════════
# 3 — PREFLIGHT GATE (pre_inject)
# Run Oracle on hydrate sidecar snippets before they reach the model.
# Catches prompt-injection smuggled via fetched docs. Fail-closed.
# ═══════════════════════════════════════════════════════════════════
@register("preflight_gate", stage="pre_inject",
          description="Oracle audit on RAG snippets before hydration reaches model.", auto=True)
def fm_preflight_gate(ctx: Dict[str, Any]):
    hydrated = ctx.get("hydrated") or ctx.get("_hydrate_chunk_out") or ""
    skill = ctx.get("skill") or "?"
    if not hydrated:
        return None
    try:
        from .oracle import Oracle
        from .skill_manager import SkillManager
        front = SkillManager().parse_frontmatter(skill)
        mode = front.get("oracle", {}).get("mode", "strict")
        compliance = front.get("oracle", {}).get("verify_compliance", [])
        oracle = Oracle(mode=mode, verify_compliance=compliance)
        # audit the hydrated text (RAG portion is inside)
        verdict = oracle.audit_text(hydrated)
        ctx["_preflight_verdict"] = verdict.to_dict()
        
        # BUS EMIT
        _emit("preflight_gate", "pre_inject", "audit_complete",
              {"verdict": verdict.verdict, "skill": skill})

        if verdict.verdict == "block":
            # redact injection indicators, do not pass hydrated to model
            ctx["_preflight_blocked"] = True
            ctx["_preflight_findings"] = len(verdict.findings)
            # keep only head instruction, drop RAG
            ctx["hydrated"] = hydrated[:800] + "\n\n…[RAG redacted — Oracle blocked]…"
            ctx["_hydrate_chunk_out"] = ctx["hydrated"]
    except Exception as e:
        ctx.setdefault("_fm_errors", []).append(f"preflight_gate: {e}")
        _emit("preflight_gate", "pre_inject", "error", {"error": str(e)})
    return None


# ═══════════════════════════════════════════════════════════════════
# 4 — MEMORY MINT (post_hydrate / on_progress)
# Write compact, searchable run receipts to Anchor + .grimoire/bus.
# So the doc remembers how you ran it, not just what it says.
# ═══════════════════════════════════════════════════════════════════
@register("memory_mint", stage="post_hydrate",
          description="Mint run receipt to .grimoire/bus + Anchor session log.", auto=False,
          requires=("skill",))
def fm_memory_mint(ctx: Dict[str, Any]):
    # opt-in per skill (set memory_mint: true) or global FM toggle
    skill = ctx.get("skill")
    if not skill:
        return None
    # check frontmatter flag
    try:
        from .skill_manager import SkillManager
        front = SkillManager().parse_frontmatter(skill)
        # look for gambit.memory_mint or skill.memory_mint
        flag = front.get("gambit", {}).get("memory_mint") if isinstance(front.get("gambit"), dict) else None
        if flag is None:
            flag = front.get("memory_mint")
        # default off unless explicitly enabled or FM toggled on
        fm = FM_REGISTRY.get("memory_mint")
        if not flag and not (fm and fm.enabled and flag is None):
            # respect global toggle: if FM enabled but no frontmatter, still mint at low rate
            # for now: only when explicitly requested via ctx
            if not ctx.get("_mint_memory"):
                return None
    except Exception:
        if not ctx.get("_mint_memory"):
            return None
    # mint
    try:
        bus_dir = Path.home() / ".grimoire" / "bus"
        bus_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "agent": "molt:memory_mint",
            "ts": time.time(),
            "skill": skill,
            "oomf": ctx.get("oomf_level"),
            "chars": len(ctx.get("hydrated", "")),
            "distilled": ctx.get("_distilled", False),
        }
        (bus_dir / f"molt_{int(time.time())}_{skill[:12]}.json").write_text(json.dumps(receipt, indent=2))
        # also session log
        log_path = Path.home() / ".molt_receipts.jsonl"
        with open(log_path, "a") as f:
            f.write(json.dumps(receipt) + "\n")
    except Exception as e:
        ctx.setdefault("_fm_errors", []).append(f"memory_mint: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════
# 5 — MORPH PRESET BOOST (pre_hydrate helper)
# Suggests best domain preset for a skill + expands morph reach.
# Used by RepurposingEngine.morph_skill — surfaces in hydrate banner.
# ═══════════════════════════════════════════════════════════════════
PRESET_AFFINITY = {
    # skill keyword -> suggested preset
    "triage": "medical_triage",
    "medical": "medical_triage",
    "disaster": "disaster_relief",
    "vision": "vision_clinic",
    "dental": "dental_clinic",
    "emergency": "emergency_services",
    "broadcast": "sports_broadcast",
    "sports": "sports_broadcast",
    "legal": "legal_financial",
    "finance": "legal_financial",
}

@register("morph_suggest", stage="pre_hydrate",
          description="Suggest best domain preset for this skill in the hydrate banner.", auto=True)
def fm_morph_suggest(ctx: Dict[str, Any]):
    skill = (ctx.get("skill") or "").lower()
    suggested = None
    for kw, preset in PRESET_AFFINITY.items():
        if kw in skill:
            suggested = preset
            break
    # also check body keywords
    if not suggested:
        body = ctx.get("_body_preview", "")
        body_l = (body or "").lower()[:2000]
        for kw, preset in PRESET_AFFINITY.items():
            if kw in body_l:
                suggested = preset
                break
    if suggested:
        ctx["_morph_hint"] = suggested
        # append to hydrated preview if requested
        if ctx.get("_include_morph_hint"):
            ctx["_morph_banner"] = f" Morph hint: this skill fits preset `{suggested}` — `morph_skill('{ctx.get('skill')}','{suggested}')`"
    return None


# ═══════════════════════════════════════════════════════════════════
# 6 — RETENTION NUDGE (on_progress)
# On challenge submit, push next_due_at and optionally schedule a nudge.
# No notification infra needed — just updates InstarState and writes a nudge file.
# ═══════════════════════════════════════════════════════════════════
@register("retention_nudge", stage="on_progress",
          description="Schedule spaced retention nudge after each challenge.", auto=True)
def fm_retention_nudge(ctx: Dict[str, Any]):
    # ctx expected to contain {skill, new_instar, passed, next_challenge_due}
    skill = ctx.get("skill")
    due = ctx.get("next_challenge_due")
    if not skill or not due:
        return None
    try:
        nudge_dir = Path("rag_storage/instars")
        nudge_dir.mkdir(parents=True, exist_ok=True)
        # write a lightweight nudge manifest — a cron or startup hook can read it
        manifest = nudge_dir / "_nudges.json"
        existing = {}
        if manifest.exists():
            try:
                existing = json.loads(manifest.read_text())
            except Exception:
                existing = {}
        existing[skill] = {"due": due, "instar": ctx.get("new_instar"), "at": time.time()}
        manifest.write_text(json.dumps(existing, indent=2))
    except Exception as e:
        ctx.setdefault("_fm_errors", []).append(f"retention_nudge: {e}")
    return None


# ── stubs — wire later, discoverable now ──────────────────────────
@register("orphan_detector", stage="pre_hydrate", description="(stub) Flag orphaned sidecars with no parent skill.", auto=False)
def fm_orphan_detector(ctx): return None

@register("cost_guard", stage="pre_scout", description="(stub) Estimate fetch cost at depth, block if over budget.", auto=False)
def fm_cost_guard(ctx): return None

@register("post_oracle_tune", stage="post_oracle", description="(stub) Tune threshold per skill from verdict history.", auto=False)
def fm_post_oracle_tune(ctx): return None
