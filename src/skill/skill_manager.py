"""
MOLT SkillManager — Core lifecycle for Living Markdown
Loads SKILL.md, parses YAML frontmatter, hydrates via RAG sidecars,
and synchronizes Scout/Oracle/Governor.

Frontmatter spec (Living SKILL.md):
---
name: <skill-name>
version: 1.0.0
scout:
  depth: 3
  interval: "6h"
  target_domains: []
oracle:
  mode: strict
  verify_compliance: []
privileges:
  elevated: false
---

Works from any cwd via PATH-discovered skill roots.
"""
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False

DEFAULT_SKILL_ROOTS = [
    Path(".agents/skills"),
    Path("projects/ScoutEmpire/scouts"),  # symlink farm
    Path("src/skill/definitions"),
]

# Safe defaults injected at creation time
DEFAULT_FRONTMATTER = {
    "name": "unnamed",
    "version": "1.0.0",
    "scout": {"depth": 3, "interval": "6h", "target_domains": []},
    "oracle": {"mode": "strict", "verify_compliance": []},
    "privileges": {"elevated": False},
    "gambit": {"enabled": False, "instar": 1, "memory_mint": False},
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class SkillManager:
    def __init__(self,
                 skill_roots: Optional[List[Path]] = None,
                 rag_dir: str = "rag_storage",
                 sidecar_dir: str = "rag_storage/sidecars"):
        self.skill_roots = [Path(p) for p in (skill_roots or DEFAULT_SKILL_ROOTS)]
        self.rag_dir = Path(rag_dir)
        self.sidecar_dir = Path(sidecar_dir)
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        self.sidecar_dir.mkdir(parents=True, exist_ok=True)

    # ── Discovery ────────────────────────────────────────────────
    def list_skills(self) -> List[str]:
        """Scan all roots for SKILL.md-bearing skill dirs."""
        found = set()
        for root in self.skill_roots:
            if not root.exists():
                continue
            for entry in root.iterdir():
                if entry.is_dir() and (entry / "SKILL.md").exists():
                    found.add(entry.name)
                # also handle symlink farm where entry is a symlink to scout dir
                # the parent folder name is still the skill name
        # fallback: scan .agents/skills directly
        agents = Path(".agents/skills")
        if agents.exists():
            for entry in agents.iterdir():
                if entry.is_dir() and (entry / "SKILL.md").exists():
                    found.add(entry.name)
        return sorted(found)

    def skill_path(self, name: str) -> Optional[Path]:
        """Resolve SKILL.md path for a given skill name."""
        for root in self.skill_roots:
            cand = root / name / "SKILL.md"
            if cand.exists():
                return cand
        # direct check
        for root in [Path(".agents/skills"), Path(".agents/skills")] + self.skill_roots:
            cand = root / name / "SKILL.md"
            if cand.exists():
                return cand
            # handle case where root is a symlink farm entry itself
            if root.name == name and (root / "SKILL.md").exists():
                return root / "SKILL.md"
        # legacy: SkillManager skips .agents/skills/<name>/scout symlink farm alias
        # fallback brute force
        for root in self.skill_roots:
            if not root.exists():
                continue
            for p in root.rglob("SKILL.md"):
                if p.parent.name == name:
                    return p
        return None

    def skill_dir(self, name: str) -> Optional[Path]:
        p = self.skill_path(name)
        return p.parent if p else None

    # ── Frontmatter parse / inject ───────────────────────────────
    def parse_frontmatter(self, skill_name_or_path) -> Dict[str, Any]:
        """
        Parse YAML frontmatter from a skill.
        Accepts skill name (str without slash) or Path.
        Returns merged dict with defaults.
        """
        path: Optional[Path]
        if isinstance(skill_name_or_path, Path):
            path = skill_name_or_path
        elif "/" in str(skill_name_or_path) or str(skill_name_or_path).endswith(".md"):
            path = Path(skill_name_or_path)
        else:
            path = self.skill_path(str(skill_name_or_path))
        if not path or not path.exists():
            return dict(DEFAULT_FRONTMATTER)
        return self._parse_file(path)

    def _parse_file(self, path: Path) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.match(text)
        if not m:
            # no frontmatter — treat as inert, inject defaults on demand
            return dict(DEFAULT_FRONTMATTER)
        raw = m.group(1)
        if HAS_YAML:
            try:
                data = yaml.safe_load(raw) or {}
            except Exception:
                data = {}
        else:
            # minimal fallback parser: key: value, nested 2 levels
            data = self._naive_yaml(raw)
        # merge defaults
        merged = dict(DEFAULT_FRONTMATTER)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        # normalize depth
        try:
            if "scout" in merged and "depth" in merged["scout"]:
                d = int(merged["scout"]["depth"])
                merged["scout"]["depth"] = max(1, min(5, d))
        except Exception:
            merged["scout"]["depth"] = 3
        return merged

    def _naive_yaml(self, raw: str) -> Dict[str, Any]:
        """Tiny YAML subset parser fallback — handles our frontmatter shape."""
        result: Dict[str, Any] = {}
        stack: List[Tuple[int, Dict]] = [(0, result)]
        for line in raw.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            stripped = line.strip()
            if ":" not in stripped:
                continue
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()
            # adjust stack to indent
            while stack and indent < stack[-1][0]:
                stack.pop()
            parent = stack[-1][1] if stack else result
            if val == "":
                # nested dict
                child: Dict[str, Any] = {}
                parent[key] = child
                stack.append((indent + 2, child))
            else:
                # scalar / inline list
                if val.startswith("[") and val.endswith("]"):
                    inner = val[1:-1].strip()
                    if not inner:
                        parent[key] = []
                    else:
                        parent[key] = [v.strip().strip("'\"") for v in inner.split(",")]
                elif val.lower() in ("true", "false"):
                    parent[key] = val.lower() == "true"
                else:
                    # try int
                    try:
                        parent[key] = int(val)
                    except ValueError:
                        parent[key] = val.strip("'\"")
        return result

    def body(self, skill_name: str) -> str:
        """Return markdown body without frontmatter."""
        path = self.skill_path(skill_name)
        if not path or not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.match(text)
        return text[m.end():] if m else text

    def inject_frontmatter(self, path: Path, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ensure a SKILL.md has a valid Living frontmatter. Creates one if missing.
        Returns final frontmatter dict.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        existing = self._parse_file(path)
        if overrides:
            for k, v in overrides.items():
                if isinstance(v, dict) and isinstance(existing.get(k), dict):
                    existing[k] = {**existing[k], **v}
                else:
                    existing[k] = v
        # Preserve body
        text = path.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER_RE.match(text)
        body_text = text[m.end():] if m else text
        # Dump frontmatter
        if HAS_YAML:
            dumped = yaml.safe_dump(existing, sort_keys=False, default_flow_style=False)
        else:
            # manual dump minimal
            lines = []
            for k, v in existing.items():
                if isinstance(v, dict):
                    lines.append(f"{k}:")
                    for kk, vv in v.items():
                        if isinstance(vv, list):
                            lines.append(f"  {kk}: [{', '.join(repr(x) for x in vv)}]")
                        elif isinstance(vv, bool):
                            lines.append(f"  {kk}: {'true' if vv else 'false'}")
                        else:
                            lines.append(f"  {kk}: {vv}")
                elif isinstance(v, list):
                    lines.append(f"{k}: [{', '.join(repr(x) for x in v)}]")
                else:
                    lines.append(f"{k}: {v}")
            dumped = "\n".join(lines) + "\n"
        path.write_text(f"---\n{dumped}---\n{body_text}", encoding="utf-8")
        return existing

    # ── Gambit helpers ───────────────────────────────────────────
    def get_gambit(self, user_id: str = "anon"):
        """Lazy-load InstarEngine for this human (no-op if gambit not installed)."""
        try:
            from .gambit import InstarEngine
            return InstarEngine(user_id=user_id)
        except Exception:
            return None

    # ── RAG hydration ────────────────────────────────────────────
    def hydrate(self, skill_name: str, oomf_level: Optional[int] = None,
                max_chars: int = 6000,
                include_sidecars: bool = True,
                gambit=None,
                user_id: str = None) -> str:
        """
        Build a single hydrated prompt chunk for one-shot API inference.
        - Loads SKILL.md body
        - Appends RAG sidecar snippets (freshest first, capped)
        - Returns a string ready to prepend to user query — no tool call needed.

        Usage:
            chunk = mgr.hydrate("med-triage-copilot", oomf_level=3)
            response = call_api(chunk + "\\n\\nUser: " + query)
        """
        front = self.parse_frontmatter(skill_name)
        # Gambit auto-OOMF: doc depth gated by human instar cap
        gambit_obj = gambit
        if gambit_obj is None and user_id is not None:
            gambit_obj = self.get_gambit(user_id=user_id)
        # If frontmatter has gambit.enabled and an engine wasn't passed, try anon
        if gambit_obj is None and front.get("gambit", {}).get("enabled"):
            gambit_obj = self.get_gambit(user_id=user_id or "anon")
        doc_depth = int(front.get("scout", {}).get("depth", 3))
        if gambit_obj is not None:
            try:
                cap = gambit_obj.auto_oomf(skill_name)
                doc_depth = min(doc_depth, cap)
            except Exception:
                pass
        # oomf_level overrides (but still capped by gambit if active)
        if oomf_level is not None:
            depth = max(1, min(5, int(oomf_level)))
            if gambit_obj is not None:
                try:
                    depth = min(depth, gambit_obj.auto_oomf(skill_name))
                except Exception:
                    pass
        else:
            depth = max(1, min(5, int(doc_depth)))

        body_text = self.body(skill_name)
        # Instar-gated reveal: strip <!-- instar:N --> blocks below your level
        if gambit_obj is not None:
            try:
                body_text = gambit_obj.gate_hydration(skill_name, body_text)
            except Exception:
                pass
        # Truncate body to avoid bloat: OOMF 1 keeps it minimal
        if depth == 1:
            body_text = body_text[:2000]
        else:
            body_text = body_text[:4000]

        # Force multipliers: pre_hydrate
        _fm_ctx = {"skill": skill_name, "oomf_level": depth, "max_chars": max_chars, "frontmatter": front}
        try:
            from .force_multipliers import run_stage
            _fm_ctx = run_stage("pre_hydrate", _fm_ctx)
            # short-circuit cache hit
            if _fm_ctx.get("_hydrate_cached") and _fm_ctx.get("_hydrate_chunk"):
                cached = _fm_ctx["_hydrate_chunk"]
                # still need gambit banner if present? return cached as-is
                return cached
            # morph hint surface
            if _fm_ctx.get("_body_preview") is None:
                _fm_ctx["_body_preview"] = body_text[:600]
        except Exception:
            _fm_ctx = {"skill": skill_name, "oomf_level": depth, "max_chars": max_chars}

        parts = [f"<!-- MOLT skill:{skill_name} depth:{depth} oomf:{depth} -->",
                 body_text.strip()]

        if include_sidecars and depth >= 2:
            sidecar_path = self.sidecar_dir / f"{skill_name}.jsonl"
            if sidecar_path.exists():
                try:
                    lines = sidecar_path.read_text(encoding="utf-8").strip().splitlines()
                    # freshest last (append order) — take tail
                    tail = lines[-8:] if len(lines) > 8 else lines
                    rag_snippets = []
                    chars = 0
                    for line in reversed(tail):
                        try:
                            entry = json.loads(line)
                            snippet = entry.get("snippet", "")[:800]
                            if not snippet:
                                continue
                            chunk = f"[RAG {entry.get('url','')}]\n{snippet}\n"
                            if chars + len(chunk) > max_chars:
                                break
                            rag_snippets.append(chunk)
                            chars += len(chunk)
                        except Exception:
                            continue
                    if rag_snippets:
                        parts.append("\n--- RAG sidecar (freshest) ---\n")
                        parts.extend(reversed(rag_snippets))
                except Exception:
                    pass
            # also include raw chunk .md files if jsonl missing
            if not parts or len(parts) < 3:
                chunk_files = sorted(self.rag_dir.glob(f"{skill_name}_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
                for cf in chunk_files:
                    try:
                        parts.append(f"\n--- {cf.name} ---\n" + cf.read_text(encoding="utf-8")[:1200])
                    except Exception:
                        pass

        hydrated = "\n\n".join(parts)
        # Force multipliers: post_hydrate (distill, cache_store, preflight, memory)
        try:
            from .force_multipliers import run_stage
            post_ctx = {"skill": skill_name, "oomf_level": depth, "max_chars": max_chars,
                        "hydrated": hydrated, "_hydrate_chunk_out": hydrated,
                        "_sidecar_hash": _fm_ctx.get("_sidecar_hash", ""),
                        "frontmatter": front}
            post_ctx = run_stage("post_hydrate", post_ctx)
            hydrated = post_ctx.get("hydrated", hydrated)
            # pre_inject gate (Oracle on RAG)
            pre_inject_ctx = {"skill": skill_name, "hydrated": hydrated}
            pre_inject_ctx = run_stage("pre_inject", pre_inject_ctx)
            hydrated = pre_inject_ctx.get("hydrated", hydrated)
        except Exception:
            pass
        # Gambit progress banner (when enabled, show instar + next challenge)
        if gambit_obj is not None:
            try:
                prog = gambit_obj.progress(skill_name)
                banner = f"\n\n<!-- gambit instar:{prog['instar']} {prog['instar_name']} oomf_cap:{prog['oomf_cap']} streak:{prog['streak']} xp:{prog['xp']}/{prog['xp_to_next']} -->"
                hydrated = hydrated + banner
            except Exception:
                pass
        return hydrated

    def hydrate_for_api(self, skill_name: str, user_query: str,
                        oomf_level: Optional[int] = None,
                        system_prefix: str = "",
                        gambit=None,
                        user_id: str = None) -> List[Dict[str, str]]:
        """
        Return OpenAI-style messages array ready for one-shot inference.
        No tool definitions. If gambit provided, hydration is instar-gated and OOMF-capped.
        """
        chunk = self.hydrate(skill_name, oomf_level=oomf_level, gambit=gambit, user_id=user_id)
        system = (system_prefix + "\n\n" + chunk).strip() if system_prefix else chunk
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ]

    # ── Mutation application (Governor + Oracle gated + versioned) ───
    def apply_mutation(self, skill_name: str, mutation: Dict[str, Any],
                       oracle_verdict: Dict[str, Any],
                       governor=None, bus=None, snapshotter=None,
                       auto_snapshot: bool = True) -> bool:
        """
        Apply a Scout-proposed mutation if Oracle passes and Governor allows.
        Hive upgrades:
          - StateSnapshotter: snapshot before mutation for zero-downtime rollback.
          - WhorlBusDispatcher: bus deposit of mutation + Oracle verdict.
        Returns True if applied.
        """
        if oracle_verdict.get("verdict") == "block":
            # Even blocked mutations are reported to bus for audit.
            if bus is not None:
                try:
                    from .whorl_bus import WhorlBusDispatcher
                    _bus = bus if hasattr(bus, "send_mutation") else WhorlBusDispatcher(auto_register=False)
                    _bus.send_mutation(skill_name, mutation, oracle_verdict)
                    _bus.send(skill_name, "molt.oracle_verdict", {"verdict": oracle_verdict.get("verdict"), "findings": len(oracle_verdict.get("findings", []))})
                except Exception:
                    pass
            return False
        ops = mutation.get("ops", [])
        needs_write = any(op.get("type") in ("write", "patch", "update_frontmatter", "update_sidecar") for op in ops if isinstance(op, dict))
        if needs_write and governor and not governor.is_elevated("write"):
            # Check via Governor's mutation gate if available
            if hasattr(governor, "check_mutation_allowed"):
                if not governor.check_mutation_allowed(mutation, oracle_verdict):
                    return False
            else:
                return False
        # Resolve snapshotter + bus (lazy, zero-bloat fallback)
        _snap = snapshotter
        if auto_snapshot and _snap is None:
            try:
                from .state_snapshotter import StateSnapshotter
                _snap = StateSnapshotter()
            except Exception:
                _snap = None
        _bus_disp = bus
        if _bus_disp is None:
            try:
                from .whorl_bus import WhorlBusDispatcher
                _bus_disp = WhorlBusDispatcher(agent_name=f"molt-manager-{skill_name[:8]}", auto_register=False)
            except Exception:
                _bus_disp = None
        # Snapshot BEFORE mutation for rewind on poisoned/corrupt case
        _pre_version = None
        if auto_snapshot and _snap is not None:
            try:
                # Determine current body/frontmatter for snapshot
                front = self.parse_frontmatter(skill_name)
                path_for_snap = self.skill_path(skill_name)
                body_hash = ""
                if path_for_snap and path_for_snap.exists():
                    body_hash = __import__("hashlib").sha256(path_for_snap.read_bytes()).hexdigest()[:10]
                cur = _snap.current(skill_name)
                _pre_version = int(cur["version"]) if cur and "version" in cur else 0
                _snap.snapshot(skill_name, {"frontmatter": front, "body_hash": body_hash, "mutation_ops": len(ops)},
                               label=f"pre-mutate:{skill_name}:{len(ops)}ops",
                               config=front.get("scout", {}))
            except Exception:
                _pre_version = None
        # For MVP: mutations are sidecar-only; SKILL.md body patches are applied as append
        path = self.skill_path(skill_name)
        if not path:
            return False
        for op in ops:
            if op.get("type") == "patch" and op.get("note"):
                # Append scout note to SKILL.md body (idempotent guard)
                current = path.read_text(encoding="utf-8", errors="replace")
                marker = f"<!-- scout:{op.get('note','')[:40]} -->"
                if marker not in current:
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(f"\n\n{marker}\n")
            elif op.get("type") == "update_frontmatter":
                updates = op.get("updates", {})
                if updates:
                    self.inject_frontmatter(path, overrides=updates)
        # Post-mutation: bus deposit + snapshot commit of new state
        if _bus_disp is not None:
            try:
                _bus_disp.send_mutation(skill_name, mutation, oracle_verdict)
                _bus_disp.send(skill_name, "molt.oracle_verdict", {"verdict": oracle_verdict.get("verdict")})
            except Exception:
                pass
        if _snap is not None:
            try:
                front_after = self.parse_frontmatter(skill_name)
                path_after = self.skill_path(skill_name)
                body_hash_after = __import__("hashlib").sha256(path_after.read_bytes()).hexdigest()[:10] if path_after and path_after.exists() else ""
                _snap.snapshot(skill_name, {"frontmatter": front_after, "body_hash": body_hash_after},
                               label=f"post-mutate:{skill_name}")
                # Auto-rollback check: if Governor Overseer flags this mutation, rewind
                # (Governor->Overseer integration below checks audit; no auto-rewind without signal)
            except Exception:
                pass
        return True

    def rewind_skill(self, skill: str, to_version: int) -> bool:
        """Zero-downtime rollback via snapshotter (Hive: Git-like versioning)."""
        try:
            from .state_snapshotter import StateSnapshotter
            StateSnapshotter().rewind(skill, to_version)
            return True
        except Exception:
            return False

    def scan_active(self) -> List[Dict[str, Any]]:
        """Scan all skills for active frontmatter + RAG sidecar status (discovery helper)."""
        result = []
        for name in self.list_skills():
            front = self.parse_frontmatter(name)
            sidecar = self.sidecar_dir / f"{name}.jsonl"
            result.append({
                "name": name,
                "frontmatter": front,
                "has_sidecar": sidecar.exists(),
                "sidecar_lines": sum(1 for _ in open(sidecar)) if sidecar.exists() else 0,
                "oomf": int(front.get("scout", {}).get("depth", 3)),
                "oracle_mode": front.get("oracle", {}).get("mode", "strict"),
            })
        return result
