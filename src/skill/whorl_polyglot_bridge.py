#!/usr/bin/env python3
"""
MOLT FLAPS Bridge — Oracle-Clean Polyglot Scout Recompiler

Bridges polyglot Scout daemons (Python, TS/JS, Rust, C++, Elixir) into the
MOLT Living Markdown ecosystem via the Whorl atomic filesystem bus.

Extracts execution contracts from scout sidecars, generates Oracle-safe
Python bindings using allowed IPC (importlib / ctypes / Unix socket) and
streams traces via MOLT's 18+4 atomic bus types.

Zero-network, zero-bloat. Degrades gracefully if Whorl/MOLT missing.
No forbidden process spawning — bindings pass Oracle SEV_CRITICAL audit.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import logging
import os
import re
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore

    HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore
    HAS_YAML = False

log = logging.getLogger("whorl.bridge")

# ── MOLT Integration (graceful degradation, no hard dependency) ──
HAS_MOLT = False
WhorlBusDispatcher = None  # type: ignore
SkillManager = None  # type: ignore
try:
    from .whorl_bus import WhorlBusDispatcher as _WBD  # type: ignore

    from .skill_manager import SkillManager as _SM  # type: ignore

    WhorlBusDispatcher = _WBD
    SkillManager = _SM
    HAS_MOLT = True
except ImportError:
    try:
        from src.skill.whorl_bus import WhorlBusDispatcher as _WBD2  # type: ignore

        from src.skill.skill_manager import SkillManager as _SM2  # type: ignore

        WhorlBusDispatcher = _WBD2
        SkillManager = _SM2
        HAS_MOLT = True
    except ImportError:
        HAS_MOLT = False

        class _StubBus:  # fallback for standalone testing without Whorl installed
            def __init__(self, *a: Any, **kw: Any) -> None:
                self.agent_name = kw.get("agent_name", "flaps-bridge-stub")
                self._log: List[Dict[str, Any]] = []

            def send(self, *a: Any, **kw: Any) -> Dict[str, Any]:
                rec = {"stub": True, "args": a, "kw": kw}
                self._log.append(rec)
                return rec

            def send_sidecar(self, *a: Any, **kw: Any) -> Dict[str, Any]:
                return self.send(*a, **kw)

            def send_mutation(self, *a: Any, **kw: Any) -> Dict[str, Any]:
                return self.send(*a, **kw)

            def send_molt_hydrate(self, *a: Any, **kw: Any) -> List[Dict[str, Any]]:
                return [self.send(*a, **kw)]

            def status(self) -> Dict[str, Any]:
                return {"stub": True}

        class _StubManager:  # minimal frontmatter parser
            def parse_frontmatter(self, p: Any) -> Dict[str, Any]:
                path = Path(p) if isinstance(p, (str, Path)) else None
                if path and path.exists():
                    text = path.read_text(encoding="utf-8", errors="replace")
                    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
                    if m and HAS_YAML:
                        try:
                            return yaml.safe_load(m.group(1)) or {}  # type: ignore
                        except Exception:
                            return {}
                    if m:
                        # tiny fallback: extract top-level key: value
                        out: Dict[str, Any] = {}
                        for line in m.group(1).splitlines():
                            if ":" in line and not line.startswith(" "):
                                k, v = line.split(":", 1)
                                out[k.strip()] = v.strip().strip("'\"")
                        return out
                return {}

            def body(self, *a: Any, **kw: Any) -> str:
                return ""

        WhorlBusDispatcher = _StubBus  # type: ignore
        SkillManager = _StubManager  # type: ignore

# ── Helpers ──────────────────────────────────────────────────────────


def _utc_ns() -> int:
    return time.time_ns()


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


_SENSITIVE_PARTS = (
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
    "private_key",
    "credential",
    "authorization",
)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(part in kl for part in _SENSITIVE_PARTS):
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _as_mapping(v: Any) -> Mapping[str, Any]:
    if isinstance(v, Mapping):
        return v
    if v is None:
        return {}
    return {"value": v}


# ── Scout Contract (Qwen richness + MOLT name compatibility) ────────


@dataclass(frozen=True)
class ScoutContract:
    """Normalized Whorl Scout IR — rich enough to price, meter, and route."""

    skill_id: str
    skill_name: str
    version: str
    language: str
    entrypoint: str
    summary: str
    ipc_strategy: str  # importlib | unix_socket | ctypes
    capabilities: Tuple[str, ...] = field(default_factory=tuple)
    inputs_schema: Mapping[str, Any] = field(default_factory=dict)
    outputs_schema: Mapping[str, Any] = field(default_factory=dict)
    permissions: Tuple[str, ...] = field(default_factory=tuple)
    growth: Mapping[str, Any] = field(default_factory=dict)
    commercial: Mapping[str, Any] = field(default_factory=dict)
    source_hash: str = ""
    manifest_hash: str = ""
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    ir: Mapping[str, Any] = field(default_factory=dict)
    root: Optional[Path] = None
    generated_dir: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "version": self.version,
            "language": self.language,
            "entrypoint": self.entrypoint,
            "summary": self.summary,
            "ipc_strategy": self.ipc_strategy,
            "capabilities": list(self.capabilities),
            "inputs": dict(self.inputs_schema),
            "outputs": dict(self.outputs_schema),
            "permissions": list(self.permissions),
            "growth": dict(self.growth),
            "commercial": dict(self.commercial),
            "source_hash": self.source_hash,
            "manifest_hash": self.manifest_hash,
            "source_hashes": dict(self.source_hashes),
            "ir": dict(self.ir),
            "root": str(self.root) if self.root else None,
            "generated_dir": str(self.generated_dir) if self.generated_dir else None,
        }


def _build_contract(
    skill_dir: Path,
    manifest: Mapping[str, Any],
    manifest_hash: str,
    language: str,
    entrypoint: str,
    ipc_strategy: str,
    source_hash: str,
    source_hashes: Mapping[str, str],
    ir: Mapping[str, Any],
) -> ScoutContract:
    # MOLT uses 'name', Qwen spec uses 'skill_id' — support both, prefer skill_id
    raw_id = manifest.get("skill_id") or manifest.get("name") or skill_dir.name
    skill_id = str(raw_id).strip() or skill_dir.name
    skill_name = str(manifest.get("name") or skill_id)
    version = str(manifest.get("version") or "1.0.0")
    summary = str(manifest.get("summary") or manifest.get("description") or "")
    # capabilities may be list or dict-shaped; normalize to tuple[str]
    raw_caps = manifest.get("capabilities") or manifest.get("exports") or []
    if isinstance(raw_caps, dict):
        caps = tuple(str(k) for k in raw_caps.keys())
    elif isinstance(raw_caps, (list, tuple)):
        caps = tuple(str(x) for x in raw_caps)
    else:
        caps = tuple()
    # ir may already contain richer function/exports list — merge if caps empty
    if not caps and ir.get("functions"):
        caps = tuple(str(x) for x in ir.get("functions", []))
    if not caps and ir.get("exports"):
        caps = tuple(str(x) for x in ir.get("exports", []))
    return ScoutContract(
        skill_id=skill_id,
        skill_name=skill_name,
        version=version,
        language=language,
        entrypoint=entrypoint,
        summary=summary,
        ipc_strategy=ipc_strategy,
        capabilities=caps,
        inputs_schema=_as_mapping(manifest.get("inputs")),
        outputs_schema=_as_mapping(manifest.get("outputs")),
        permissions=tuple(str(x) for x in (manifest.get("permissions") or [])),
        growth=_as_mapping(manifest.get("growth")),
        commercial=_as_mapping(manifest.get("commercial")),
        source_hash=source_hash,
        manifest_hash=manifest_hash,
        source_hashes=dict(source_hashes),
        ir=dict(ir),
        root=skill_dir,
    )


# ── Language Adapters ───────────────────────────────────────────────


class LanguageAdapter:
    name: str = "base"

    def detect(self, skill_dir: Path, manifest: Mapping[str, Any]) -> bool:
        raise NotImplementedError

    def extract_contract(
        self, skill_dir: Path, manifest: Mapping[str, Any], body: str, manifest_hash: str
    ) -> ScoutContract:
        raise NotImplementedError

    def generate_bindings(self, contract: ScoutContract, out_dir: Path) -> Path:
        raise NotImplementedError


class PythonAdapter(LanguageAdapter):
    name = "python"

    def detect(self, skill_dir: Path, manifest: Mapping[str, Any]) -> bool:
        lang = str(manifest.get("language", "")).lower()
        if lang in ("python", "py"):
            return True
        ep = str(manifest.get("entrypoint", ""))
        if ep.endswith(".py"):
            return True
        # convention probes
        candidates = (
            skill_dir / "scout" / "main.py",
            skill_dir / "main.py",
            skill_dir / "scout.py",
            skill_dir / "app.py",
        )
        return any(p.exists() for p in candidates)

    def _guess_entrypoint(self, skill_dir: Path, manifest: Mapping[str, Any]) -> str:
        declared = manifest.get("entrypoint")
        if declared:
            return str(declared)
        for cand in [Path("scout/main.py"), Path("main.py"), Path("scout.py"), Path("app.py")]:
            if (skill_dir / cand).exists():
                return str(cand)
        py_files = sorted(skill_dir.rglob("*.py"))
        # prefer scout/ if exists
        for pf in py_files:
            rel = pf.relative_to(skill_dir)
            if str(rel).startswith("scout/"):
                return str(rel)
        if py_files:
            return str(py_files[0].relative_to(skill_dir))
        raise RuntimeError(f"No Python entrypoint found in {skill_dir}")

    def extract_contract(
        self, skill_dir: Path, manifest: Mapping[str, Any], body: str, manifest_hash: str
    ) -> ScoutContract:
        entrypoint = self._guess_entrypoint(skill_dir, manifest)
        source_path = skill_dir / entrypoint
        if not source_path.exists():
            raise RuntimeError(f"Python entrypoint not found: {source_path}")
        source = source_path.read_text(encoding="utf-8")
        source_hash = _sha256_text(source)
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise RuntimeError(f"Python syntax error in {source_path}: {exc}") from exc
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        imports: List[str] = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports.extend(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                if n.module:
                    imports.append(n.module)
        ir: Dict[str, Any] = {
            "language": self.name,
            "entrypoint": entrypoint,
            "functions": sorted(set(funcs)),
            "classes": sorted(set(classes)),
            "imports": sorted(set(imports)),
            "has_whorl_invoke": "whorl_invoke" in funcs,
            "has_main": "main" in funcs,
            "body_hash": _sha256_text(body),
            "extraction_mode": "python-ast",
        }
        source_hashes = {entrypoint: source_hash, "SKILL.md": manifest_hash}
        return _build_contract(
            skill_dir=skill_dir,
            manifest=manifest,
            manifest_hash=manifest_hash,
            language=self.name,
            entrypoint=entrypoint,
            ipc_strategy="importlib",
            source_hash=source_hash,
            source_hashes=source_hashes,
            ir=ir,
        )

    def generate_bindings(self, contract: ScoutContract, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        binding = out_dir / "whorl_binding.py"
        # Oracle-safe: importlib only — no process spawning
        code = (
            '"""Auto-generated Whorl binding for '
            + contract.skill_id
            + "@"
            + contract.version
            + ' — Oracle-safe importlib."""\n'
            "import importlib.util\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            f"ENTRYPOINT = {json.dumps(contract.entrypoint)}\n"
            f"SKILL_ID = {json.dumps(contract.skill_id)}\n"
            f"VERSION = {json.dumps(contract.version)}\n"
            "\n"
            "\n"
            "def load_entrypoint(skill_root: str):\n"
            "    path = Path(skill_root) / ENTRYPOINT\n"
            '    spec = importlib.util.spec_from_file_location("whorl_scout_entry", path)\n'
            "    if spec is None or spec.loader is None:\n"
            '        raise RuntimeError("Unable to load scout entrypoint")\n'
            '    module = importlib.util.module_from_spec(spec)\n'
            '    sys.modules["whorl_scout_entry"] = module\n'
            "    spec.loader.exec_module(module)\n"
            "    return module\n"
            "\n"
            "\n"
            "def invoke(skill_root: str, payload: dict):\n"
            "    module = load_entrypoint(skill_root)\n"
            '    if hasattr(module, "whorl_invoke"):\n'
            "        return module.whorl_invoke(payload)\n"
            '    if hasattr(module, "main"):\n'
            "        return module.main(payload)\n"
            '    raise RuntimeError("Scout must expose whorl_invoke(payload) or main(payload)")\n'
            "\n"
            "\n"
            "def whorl_invoke(payload: dict) -> dict:\n"
            '    """Convenience when binding is imported directly."""\n'
            "    import pathlib as _pl\n"
            "    root = str(_pl.Path(__file__).resolve().parent.parent)\n"
            "    return invoke(root, payload)\n"
        )
        binding.write_text(code, encoding="utf-8")
        return binding


class TypeScriptAdapter(LanguageAdapter):
    name = "typescript"

    def detect(self, skill_dir: Path, manifest: Mapping[str, Any]) -> bool:
        lang = str(manifest.get("language", "")).lower()
        if lang in ("typescript", "ts", "javascript", "js", "node", "bun"):
            return True
        ep = str(manifest.get("entrypoint", ""))
        if ep.endswith((".ts", ".mts", ".js", ".mjs")):
            return True
        candidates = (
            skill_dir / "scout" / "main.ts",
            skill_dir / "main.ts",
            skill_dir / "scout" / "main.js",
            skill_dir / "main.js",
            skill_dir / "index.ts",
            skill_dir / "index.js",
        )
        return any(p.exists() for p in candidates)

    def _guess_entrypoint(self, skill_dir: Path, manifest: Mapping[str, Any]) -> str:
        declared = manifest.get("entrypoint")
        if declared:
            return str(declared)
        for cand in [
            Path("scout/main.ts"),
            Path("main.ts"),
            Path("scout/main.js"),
            Path("main.js"),
            Path("index.ts"),
            Path("index.js"),
        ]:
            if (skill_dir / cand).exists():
                return str(cand)
        files = sorted(
            list(skill_dir.rglob("*.ts"))
            + list(skill_dir.rglob("*.mts"))
            + list(skill_dir.rglob("*.js"))
            + list(skill_dir.rglob("*.mjs"))
        )
        if files:
            return str(files[0].relative_to(skill_dir))
        raise RuntimeError(f"No TS/JS entrypoint found in {skill_dir}")

    def extract_contract(
        self, skill_dir: Path, manifest: Mapping[str, Any], body: str, manifest_hash: str
    ) -> ScoutContract:
        entrypoint = self._guess_entrypoint(skill_dir, manifest)
        source_path = skill_dir / entrypoint
        if not source_path.exists():
            raise RuntimeError(f"TS/JS entrypoint not found: {source_path}")
        source = source_path.read_text(encoding="utf-8")
        source_hash = _sha256_text(source)
        exports = re.findall(r"export\s+(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)", source)
        exports += re.findall(r"export\s+const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=", source)
        exports = sorted(set(exports))
        ir: Dict[str, Any] = {
            "language": self.name,
            "entrypoint": entrypoint,
            "exports": exports,
            "has_whorl_invoke": ("whorlInvoke" in exports or "whorl_invoke" in exports),
            "has_main": "main" in exports,
            "body_hash": _sha256_text(body),
            "extraction_mode": "regex-basic",
        }
        source_hashes = {entrypoint: source_hash, "SKILL.md": manifest_hash}
        return _build_contract(
            skill_dir=skill_dir,
            manifest=manifest,
            manifest_hash=manifest_hash,
            language=self.name,
            entrypoint=entrypoint,
            ipc_strategy="unix_socket",
            source_hash=source_hash,
            source_hashes=source_hashes,
            ir=ir,
        )

    def generate_bindings(self, contract: ScoutContract, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        binding = out_dir / "whorl_binding.py"
        # Oracle-safe TS/JS via Unix Domain Socket — no process spawning.
        # Talks to a persistent Bun/Node worker at ~/.whorl/run/{skill}.sock
        # Caller must ensure the worker is running; binding handles timeout+framing.
        code = (
            '"""Auto-generated Whorl binding for '
            + contract.skill_id
            + "@"
            + contract.version
            + ' — Oracle-safe Unix socket (TS/JS)."""\n'
            "import json\n"
            "import os\n"
            "import socket\n"
            "\n"
            f"SKILL_ID = {json.dumps(contract.skill_id)}\n"
            f"VERSION = {json.dumps(contract.version)}\n"
            f"ENTRYPOINT = {json.dumps(contract.entrypoint)}\n"
            f"SOCK_PATH = os.path.expanduser({json.dumps('~/.whorl/run/' + contract.skill_id + '.sock')})\n"
            "SOCK_TIMEOUT = 5.0\n"
            "\n"
            "\n"
            "def whorl_invoke(payload: dict) -> dict:\n"
            '    """Invoke TS/JS scout via Unix Domain Socket (JSON request/response)."""\n'
            "    data = json.dumps(payload).encode(\"utf-8\")\n"
            "    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "    client.settimeout(SOCK_TIMEOUT)\n"
            "    try:\n"
            "        client.connect(SOCK_PATH)\n"
            "        client.sendall(data)\n"
            "        client.shutdown(socket.SHUT_WR)\n"
            '        buf = b""\n'
            "        while True:\n"
            "            try:\n"
            "                chunk = client.recv(4096)\n"
            "            except socket.timeout:\n"
            '                raise RuntimeError(f"TS worker timeout after {SOCK_TIMEOUT}s at {SOCK_PATH}")\n'
            "            if not chunk:\n"
            "                break\n"
            "            buf += chunk\n"
            "        if not buf:\n"
            '            raise RuntimeError("Empty response from TS worker")\n'
            "        return json.loads(buf.decode(\"utf-8\"))\n"
            "    finally:\n"
            "        try:\n"
            "            client.close()\n"
            "        except Exception:\n"
            "            pass\n"
            "\n"
            "\n"
            "def invoke(skill_root: str, payload: dict) -> dict:\n"
            '    _ = skill_root  # socket path is skill-id based, not root based\n'
            "    return whorl_invoke(payload)\n"
        )
        binding.write_text(code, encoding="utf-8")
        # also emit a JS worker stub for the persistent side
        worker = out_dir / "whorl_worker.mjs"
        worker_code = (
            "// Auto-generated Whorl TS worker stub for "
            + contract.skill_id
            + " — listens on ~/.whorl/run/{skill}.sock\n"
            "import { createServer } from \"node:net\";\n"
            "import { pathToFileURL } from \"node:url\";\n"
            "import path from \"node:path\";\n"
            "import os from \"node:os\";\n"
            "import fs from \"node:fs\";\n"
            f"const SKILL_ROOT = {json.dumps(str(contract.root) if contract.root else '.')};\n"
            f"const ENTRYPOINT = {json.dumps(contract.entrypoint)};\n"
            f"const SOCK = os.homedir() + {json.dumps('/.whorl/run/' + contract.skill_id + '.sock')};\n"
            "fs.mkdirSync(path.dirname(SOCK), { recursive: true });\n"
            "try { fs.unlinkSync(SOCK); } catch {}\n"
            "const mod = await import(pathToFileURL(path.join(SKILL_ROOT, ENTRYPOINT)).href);\n"
            "const handler = mod.whorlInvoke ?? mod.whorl_invoke ?? mod.main;\n"
            "if (typeof handler !== \"function\") throw new Error(\"Scout must export whorlInvoke or main\");\n"
            "const server = createServer(async (conn) => {\n"
            "  let buf=\"\"; for await (const chunk of conn) buf+=chunk;\n"
            "  let payload={}; try { payload=JSON.parse(buf||\"{}\"); } catch {}\n"
            "  let result; try { result=await handler(payload); } catch(e) { result={error:String(e)}; }\n"
            "  conn.end(JSON.stringify(result));\n"
            "});\n"
            "server.listen(SOCK, () => console.log(`[whorl] ${SOCK} listening`));\n"
        )
        worker.write_text(worker_code, encoding="utf-8")
        return binding


class RustAdapter(LanguageAdapter):
    name = "rust"

    def detect(self, skill_dir: Path, manifest: Mapping[str, Any]) -> bool:
        lang = str(manifest.get("language", "")).lower()
        if lang in ("rust", "rs"):
            return True
        return (skill_dir / "Cargo.toml").exists() or (skill_dir / "scout" / "Cargo.toml").exists()

    def _guess_entrypoint(self, skill_dir: Path, manifest: Mapping[str, Any]) -> str:
        declared = manifest.get("entrypoint")
        if declared:
            return str(declared)
        for cand in [
            Path("scout/target/release/libscout.so"),
            Path("target/release/libscout.so"),
            Path("scout/target/release/libscout.dylib"),
            Path("target/release/libscout.dylib"),
        ]:
            if (skill_dir / cand).exists():
                return str(cand)
        # default even if not yet built — binding will document expected path
        return "scout/target/release/libscout.so"

    def extract_contract(
        self, skill_dir: Path, manifest: Mapping[str, Any], body: str, manifest_hash: str
    ) -> ScoutContract:
        entrypoint = self._guess_entrypoint(skill_dir, manifest)
        source_path = skill_dir / entrypoint
        # binary may not exist yet — hash the manifest + Cargo.toml instead
        cargo = skill_dir / "scout" / "Cargo.toml"
        if not cargo.exists():
            cargo = skill_dir / "Cargo.toml"
        if source_path.exists():
            source_hash = _sha256_file(source_path)
        elif cargo.exists():
            source_hash = _sha256_file(cargo)
        else:
            source_hash = _sha256_text(entrypoint + body[:400])
        ir: Dict[str, Any] = {
            "language": self.name,
            "entrypoint": entrypoint,
            "exports": ["native_invoke"],
            "has_whorl_invoke": True,
            "cargo_exists": cargo.exists(),
            "binary_exists": source_path.exists(),
            "body_hash": _sha256_text(body),
            "extraction_mode": "manifest-driven",
        }
        source_hashes = {entrypoint: source_hash, "SKILL.md": manifest_hash}
        return _build_contract(
            skill_dir=skill_dir,
            manifest=manifest,
            manifest_hash=manifest_hash,
            language=self.name,
            entrypoint=entrypoint,
            ipc_strategy="ctypes",
            source_hash=source_hash,
            source_hashes=source_hashes,
            ir=ir,
        )

    def generate_bindings(self, contract: ScoutContract, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        binding = out_dir / "whorl_binding.py"
        code = (
            '"""Auto-generated Whorl binding for '
            + contract.skill_id
            + "@"
            + contract.version
            + ' — Oracle-safe ctypes FFI (Rust/C++)."""\n'
            "import ctypes\n"
            "import json\n"
            "from pathlib import Path\n"
            "\n"
            f"SKILL_ID = {json.dumps(contract.skill_id)}\n"
            f"VERSION = {json.dumps(contract.version)}\n"
            f"ENTRYPOINT = {json.dumps(contract.entrypoint)}\n"
            "LIB_PATH = Path(__file__).resolve().parent.parent / ENTRYPOINT\n"
            'LIB_ALT = Path(__file__).resolve().parent.parent / "target" / "release" / "libscout.so"\n'
            "\n"
            "def _load_lib():\n"
            "    for p in [LIB_PATH, LIB_ALT]:\n"
            "        if p.exists():\n"
            "            lib = ctypes.CDLL(str(p))\n"
            "            return lib\n"
            '    raise RuntimeError(f"Rust lib not found: {LIB_PATH} (build with cargo build --release)")\n'
            "\n"
            "_lib = None\n"
            "def _get_lib():\n"
            "    global _lib\n"
            "    if _lib is None:\n"
            "        _lib = _load_lib()\n"
            "        try:\n"
            "            _lib.whorl_invoke_json.argtypes = [ctypes.c_char_p]\n"
            "            _lib.whorl_invoke_json.restype = ctypes.c_char_p\n"
            "        except AttributeError:\n"
            "            pass\n"
            "    return _lib\n"
            "\n"
            "def whorl_invoke(payload: dict) -> dict:\n"
            '    """Invoke Rust scout via ctypes FFI (JSON over C string)."""\n'
            "    lib = _get_lib()\n"
            "    req = json.dumps(payload).encode(\"utf-8\")\n"
            "    try:\n"
            "        res_ptr = lib.whorl_invoke_json(req)\n"
            "    except AttributeError:\n"
            '        raise RuntimeError("Rust lib missing whorl_invoke_json symbol")\n'
            "    if not res_ptr:\n"
            '        raise RuntimeError("Rust FFI returned null")\n'
            "    raw = ctypes.string_at(res_ptr) if isinstance(res_ptr, int) else res_ptr\n"
            "    if isinstance(raw, bytes):\n"
            "        return json.loads(raw.decode(\"utf-8\"))\n"
            "    return json.loads(str(raw))\n"
            "\n"
            "def invoke(skill_root: str, payload: dict) -> dict:\n"
            "    return whorl_invoke(payload)\n"
        )
        binding.write_text(code, encoding="utf-8")
        return binding


# ── Adapter Registry ───────────────────────────────────────────────


class AdapterRegistry:
    def __init__(self, adapters: Optional[Sequence[LanguageAdapter]] = None) -> None:
        self.adapters: List[LanguageAdapter] = list(
            adapters or [PythonAdapter(), TypeScriptAdapter(), RustAdapter()]
        )

    def register(self, adapter: LanguageAdapter) -> None:
        self.adapters.append(adapter)

    def choose(self, skill_dir: Path, manifest: Mapping[str, Any]) -> LanguageAdapter:
        for adapter in self.adapters:
            try:
                if adapter.detect(skill_dir, manifest):
                    return adapter
            except Exception as exc:
                log.warning("Adapter %s detection failed for %s: %s", adapter.name, skill_dir, exc)
        raise RuntimeError(f"No language adapter matched {skill_dir.name} (manifest language={manifest.get('language')!r})")


# ── Minimal hash-chained ledger (local, inspectable) ───────────────


class HashChainLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prev_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return "genesis"
        last = ""
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    last = line
        except Exception:
            return "genesis"
        if not last:
            return "genesis"
        try:
            return str(json.loads(last).get("hash", "genesis"))
        except Exception:
            return "genesis"

    def append(self, kind: str, payload: Mapping[str, Any]) -> str:
        base = {"ts": _utc_ns(), "kind": kind, "payload": dict(payload), "prev_hash": self.prev_hash}
        h = _sha256_text(_canonical_json(base))
        entry = {**base, "hash": h}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical_json(entry) + "\n")
        self.prev_hash = h
        return h


# ── Bridge Orchestrator ────────────────────────────────────────────


class MoltPolyglotBridge:
    """Ingests polyglot scouts, generates Oracle-safe bindings, injects via Whorl bus."""

    def __init__(
        self,
        agent_name: str = "flaps-bridge",
        artifact_root: Path = Path(".whorl/generated"),
        ledger_path: Optional[Path] = None,
    ) -> None:
        self.registry = AdapterRegistry()
        self.artifact_root = Path(artifact_root)
        # Bus + manager (graceful stub if Whorl not installed)
        try:
            self.bus = WhorlBusDispatcher(agent_name=agent_name, capabilities=["molt.hydrate", "molt.sidecar", "molt.mutation"])  # type: ignore
        except Exception:
            self.bus = WhorlBusDispatcher(agent_name=agent_name)  # type: ignore
        try:
            self.mgr = SkillManager() if HAS_MOLT else None  # type: ignore
        except Exception:
            self.mgr = None
        # ledger defaults to .whorl/ledger.jsonl relative to cwd
        ledger_path = ledger_path or Path(".whorl/ledger.jsonl")
        try:
            self.ledger = HashChainLedger(ledger_path)
        except Exception:
            self.ledger = None  # type: ignore

    def _load_manifest(self, skill_dir: Path) -> Tuple[Dict[str, Any], str]:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise RuntimeError(f"Missing SKILL.md in {skill_dir}")
        # Prefer SkillManager (handles MOLT defaults + YAML), fallback to raw parse
        if self.mgr is not None:
            try:
                front = self.mgr.parse_frontmatter(skill_md)  # type: ignore
                # body via SkillManager if available, else raw
                try:
                    body = self.mgr.body(skill_dir.name)  # type: ignore
                    if not body:
                        raise ValueError("empty body")
                except Exception:
                    text = skill_md.read_text(encoding="utf-8")
                    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
                    body = text[m.end():] if m else text
                return dict(front), body.strip()
            except Exception as e:
                log.debug("SkillManager parse failed, falling back: %s", e)
        # fallback raw frontmatter
        text = skill_md.read_text(encoding="utf-8")
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3 and HAS_YAML:
                try:
                    front = yaml.safe_load(parts[1]) or {}  # type: ignore
                except Exception:
                    front = {}
                body = parts[2]
                if not isinstance(front, dict):
                    raise RuntimeError("SKILL.md frontmatter must be a mapping")
                return dict(front), body.strip()
            elif len(parts) >= 3:
                # JSON frontmatter fallback
                ft = parts[1].strip()
                if ft.startswith("{"):
                    front = json.loads(ft)
                    return dict(front), parts[2].strip()
                raise RuntimeError("PyYAML required for YAML frontmatter")
        return {}, text.strip()

    def _validate_manifest(self, manifest: Dict[str, Any], skill_dir: Path) -> None:
        # skill_id or name must be present (MOLT uses name, Qwen uses skill_id)
        if not manifest.get("skill_id") and not manifest.get("name"):
            # auto-fill from dir name — don't hard fail, keep ingest usable
            manifest["skill_id"] = skill_dir.name
            manifest["name"] = skill_dir.name
        if not manifest.get("version"):
            manifest["version"] = "1.0.0"
        if not str(manifest.get("skill_id") or manifest.get("name") or "").strip():
            raise RuntimeError(f"Missing skill_id/name in {skill_dir}/SKILL.md (empty string)")

    def ingest_skill(self, skill_dir: Path) -> ScoutContract:
        skill_dir = Path(skill_dir).resolve()
        manifest, body = self._load_manifest(skill_dir)
        self._validate_manifest(manifest, skill_dir)
        manifest_hash = _sha256_text(_canonical_json(manifest))
        adapter = self.registry.choose(skill_dir, manifest)
        contract = adapter.extract_contract(skill_dir, manifest, body, manifest_hash)
        # out_dir: prefer artifact_root/<skill_id>/<version>/<lang>, but also mirror to skill_dir/.whorl_generated for local dev
        out_dir = self.artifact_root / contract.skill_id / contract.version / contract.language
        binding_path = adapter.generate_bindings(contract, out_dir)
        # also ensure skill-local copy for direct invoke without artifact_root lookup
        local_dir = skill_dir / ".whorl_generated"
        if local_dir.resolve() != out_dir.resolve():
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
                # copy binding to local dir for convenience (best-effort)
                import shutil

                shutil.copy2(binding_path, local_dir / binding_path.name)
                # copy worker mjs if TS adapter emitted it
                worker_src = out_dir / "whorl_worker.mjs"
                if worker_src.exists():
                    shutil.copy2(worker_src, local_dir / "whorl_worker.mjs")
            except Exception:
                pass
        contract = ScoutContract(  # re-attach generated_dir
            skill_id=contract.skill_id,
            skill_name=contract.skill_name,
            version=contract.version,
            language=contract.language,
            entrypoint=contract.entrypoint,
            summary=contract.summary,
            ipc_strategy=contract.ipc_strategy,
            capabilities=contract.capabilities,
            inputs_schema=contract.inputs_schema,
            outputs_schema=contract.outputs_schema,
            permissions=contract.permissions,
            growth=contract.growth,
            commercial=contract.commercial,
            source_hash=contract.source_hash,
            manifest_hash=contract.manifest_hash,
            source_hashes=contract.source_hashes,
            ir=contract.ir,
            root=contract.root,
            generated_dir=out_dir,
        )
        # helical loop: propose mutation + sidecar telemetry via bus (Oracle audits the generated code)
        self._propose_binding_mutation(contract, binding_path)
        self._emit_sidecar(contract, binding_path, body)
        if self.ledger is not None:
            try:
                self.ledger.append("skill.ingested", _redact(contract.to_dict()))  # type: ignore
            except Exception:
                pass
        log.info(
            "FLAPS ingested %s@%s language=%s ipc=%s binding=%s",
            contract.skill_id,
            contract.version,
            contract.language,
            contract.ipc_strategy,
            binding_path,
        )
        return contract

    def _propose_binding_mutation(self, contract: ScoutContract, binding_path: Path) -> None:
        try:
            code = binding_path.read_text(encoding="utf-8")
        except Exception:
            code = ""
        mutation = {
            "ops": [
                {
                    "type": "write",
                    "path": str(binding_path),
                    "content": code,
                    "note": f"FLAPS: {contract.ipc_strategy} binding for {contract.language} — Oracle-safe",
                },
                {
                    "type": "update_frontmatter",
                    "updates": {"privileges": {"elevated": False}},
                },
            ]
        }
        try:
            # WhorlBusDispatcher.send_mutation(skill, mutation, oracle_verdict)
            if hasattr(self.bus, "send_mutation"):
                self.bus.send_mutation(skill=contract.skill_name, mutation=mutation)  # type: ignore
            else:
                self.bus.send(contract.skill_name, "molt.mutation", {"skill": contract.skill_name, "mutation": mutation})  # type: ignore
        except Exception as e:
            log.debug("send_mutation failed (stub or bus unavailable): %s", e)

    def _emit_sidecar(self, contract: ScoutContract, binding_path: Path, body: str) -> None:
        payload = _redact(
            {
                "event": "flaps.compiled",
                "skill_id": contract.skill_id,
                "skill_name": contract.skill_name,
                "version": contract.version,
                "language": contract.language,
                "ipc_strategy": contract.ipc_strategy,
                "binding_path": str(binding_path),
                "generated_dir": str(contract.generated_dir),
                "source_hash": contract.source_hash,
                "manifest_hash": contract.manifest_hash,
                "capabilities": list(contract.capabilities),
                "body_preview": body[:600],
            }
        )
        try:
            if hasattr(self.bus, "send_sidecar"):
                self.bus.send_sidecar(skill=contract.skill_name, sidecar_payload=payload)  # type: ignore
            else:
                self.bus.send(contract.skill_name, "molt.sidecar", payload)  # type: ignore
        except Exception as e:
            log.debug("send_sidecar failed (stub): %s", e)

    def ingest_many(self, skill_dirs: Sequence[Path]) -> Tuple[int, int]:
        ok = 0
        fail = 0
        for sd in skill_dirs:
            try:
                c = self.ingest_skill(Path(sd))
                ok += 1
                print(f"ingested {c.skill_id}@{c.version} language={c.language} ipc={c.ipc_strategy} binding={c.generated_dir}")
            except Exception as exc:
                fail += 1
                log.error("Failed to ingest %s: %s", sd, exc)
                print(f"FAILED {sd}: {exc}", file=sys.stderr)
        return ok, fail


# ── CLI ──────────────────────────────────────────────────────────────
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="MOLT FLAPS Bridge — Oracle-clean polyglot ingest")
    parser.add_argument("skill_dirs", nargs="+", help="Skill directories containing SKILL.md")
    parser.add_argument("--artifact-root", default=".whorl/generated", help="Where generated bindings are written")
    parser.add_argument("--ledger", default=".whorl/ledger.jsonl", help="Hash-chained ledger path")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    bridge = MoltPolyglotBridge(artifact_root=Path(args.artifact_root), ledger_path=Path(args.ledger))
    ok, fail = bridge.ingest_many([Path(p) for p in args.skill_dirs])
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
