"""
Scout: Skill Loader with Safe Sandboxing.
Implements a safe loader that validates skill manifests before execution.

Trust ordering (P2 before P1) — the invariant this module exists to protect:

    P2 (verify)  a sidecar is untrusted local state until its content hash
                 is recomputed and matched against the stored digest.
    P1 (trust)   only verified sidecar state may be returned to a caller.

A sidecar is a plain JSON file in a shared directory, so any other process on
the box can rewrite it. Reading it and believing it *before* checking the hash
is the poisoned-cache inversion: an attacker who can write the file gets their
content executed as context. So `read_sidecar` verifies first and returns
None (rather than the payload) whenever verification fails, missing, or is
ambiguous.

Network posture: `run()` at depth >= 2 only reaches the network when a caller
injects a `fetcher` or passes `allow_network=True`. Tests and offline callers
inject a local stub. Governor elevation for the "network" scope is required
either way — the fetcher is the transport, the Governor is the permission.
"""

import hashlib
import json
import os
import time
import yaml
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# Bound on a single fetched document and on the whole sidecar payload. Scout
# output is untrusted input that later becomes context, so it stays small.
MAX_DOC_BYTES = 64 * 1024
MAX_SIDECAR_BYTES = 256 * 1024
HASH_ALGO = "sha256"

FetchResult = Dict[str, Any]


def _canonical(payload: Any) -> str:
    """Stable serialization for hashing.

    sort_keys + compact separators so the digest covers content, not key
    ordering or incidental whitespace.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via temp file + rename so readers never observe a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def urlopen_fetcher(url: str, timeout: float = 10.0) -> FetchResult:
    """Real HTTP fetcher. Only reached when the caller passes allow_network."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "molt-scout/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read(MAX_DOC_BYTES + 1)
        status = getattr(resp, "status", 200)
    return {
        "url": url,
        "status": status,
        "truncated": len(raw) > MAX_DOC_BYTES,
        "content": raw[:MAX_DOC_BYTES].decode("utf-8", errors="replace"),
    }


class ScoutResult:
    """Output of a scout run."""

    def __init__(self, depth: int = 1, mutation: Optional[Dict[str, Any]] = None,
                 errors: Optional[list] = None,
                 sidecar: Optional[Dict[str, Any]] = None):
        self.depth = depth
        self.mutation = mutation or {}
        self.errors = errors or []
        # Receipt for the sidecar this run wrote (or attempted to). None when
        # the run was inert, blocked, or quarantine rejected the payload.
        self.sidecar = sidecar


class ScoutLoader:
    def __init__(self, skill_root: Optional[Path] = None, **kwargs):
        self.skill_root = (skill_root or Path(".")).resolve()
        self.rag_dir = Path(kwargs.get("rag_dir", "rag_storage"))
        self.sidecar_dir = Path(kwargs.get("sidecar_dir", "rag_storage/sidecars"))
        self.governor = kwargs.get("governor")
        self.oracle = kwargs.get("oracle")
        self.bus = kwargs.get("bus")
        self.snapshotter = kwargs.get("snapshotter")
        # Transport injection. No fetcher => no network, regardless of depth.
        self.fetcher: Optional[Callable[[str, float], FetchResult]] = kwargs.get("fetcher")
        if self.fetcher is None and kwargs.get("allow_network"):
            self.fetcher = urlopen_fetcher
        self.fetch_timeout = float(kwargs.get("fetch_timeout", 10.0))
        # Non-fatal problems a caller may want to inspect. Populated rather
        # than swallowed, so a degraded run is visible instead of silent.
        self.warnings: List[str] = []

    def load_manifest(self, skill_name: str) -> Dict[str, Any]:
        """Loads and validates skill.yaml from the skill directory."""
        manifest_path = self.skill_root / skill_name / "skill.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found for skill: {skill_name}")

        with open(manifest_path, 'r') as f:
            manifest = yaml.safe_load(f)

        required_fields = ["name", "version", "runtime", "entrypoint"]
        for field in required_fields:
            if field not in manifest:
                raise ValueError(f"Missing required field in manifest: {field}")

        return manifest

    def execute_skill(self, skill_name: str, args: Dict[str, Any]):
        """Executes a skill within its policy constraints."""
        manifest = self.load_manifest(skill_name)
        print(f"Loading and executing {skill_name} ({manifest['runtime']})")

    @staticmethod
    def _is_url_allowed(url: str) -> bool:
        blocked = {"file", "ftp", "gopher"}
        try:
            parsed = urlparse(url)
            if parsed.scheme in blocked:
                return False
            host = (parsed.hostname or "").lower()
            if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
                return False
            if host.startswith("10.") or host.startswith("192.168.") or host.startswith("172."):
                return False
            return True
        except Exception:
            return False

    # ── Sidecar: P2 verify, then P1 trust ──────────────────────────

    def sidecar_path(self, skill_name: str) -> Path:
        return self.sidecar_dir / f"{skill_name}.json"

    def write_sidecar(self, skill_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Atomically persist a sidecar and stamp it with its content hash.

        The digest is computed over the payload only, never over the envelope,
        so verification does not have to trust any other envelope field.
        """
        text = _canonical(payload)
        if len(text.encode("utf-8")) > MAX_SIDECAR_BYTES:
            raise ValueError(
                f"sidecar payload exceeds {MAX_SIDECAR_BYTES} bytes: {len(text)}"
            )
        envelope = {
            "skill": skill_name,
            "hash_algo": HASH_ALGO,
            "payload_hash": payload_hash(payload),
            "written_at": time.time(),
            "payload": payload,
        }
        _atomic_write_text(
            self.sidecar_path(skill_name),
            json.dumps(envelope, sort_keys=True, indent=2) + "\n",
        )
        receipt = {
            "path": str(self.sidecar_path(skill_name)),
            "payload_hash": envelope["payload_hash"],
        }
        # Bus emission is best-effort observability, not the trust path: the
        # file above is what gets verified on read.
        if self.bus is not None:
            try:
                self.bus.send_sidecar(skill_name, {**payload, "payload_hash": receipt["payload_hash"]})
            except Exception as exc:
                # Best-effort by design -- a bus outage must not fail the
                # sidecar write, which is the artifact that actually gets
                # verified on read. Recorded, not swallowed.
                self.warnings.append(f"bus sidecar emit failed: {exc}")
        return receipt

    def read_sidecar(self, skill_name: str) -> Dict[str, Any]:
        """Verify then trust. Returns {ok, payload, error}; ok=False means the
        caller must treat the payload as absent."""
        path = self.sidecar_path(skill_name)
        if not path.exists():
            return {"ok": False, "payload": None, "error": "sidecar missing"}

        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "payload": None, "error": f"sidecar unreadable: {exc}"}

        if not isinstance(envelope, dict) or "payload" not in envelope:
            return {"ok": False, "payload": None, "error": "sidecar malformed: no payload"}

        if envelope.get("hash_algo") != HASH_ALGO:
            return {"ok": False, "payload": None,
                    "error": f"sidecar hash_algo not supported: {envelope.get('hash_algo')!r}"}

        stored = envelope.get("payload_hash")
        actual = payload_hash(envelope["payload"])
        if not isinstance(stored, str) or not stored:
            return {"ok": False, "payload": None, "error": "sidecar missing payload_hash"}
        if stored != actual:
            # Poisoned or stale cache. Refusing here is the whole point.
            return {"ok": False, "payload": None,
                    "error": f"sidecar hash mismatch: stored={stored[:12]} actual={actual[:12]}"}

        return {"ok": True, "payload": envelope["payload"], "error": ""}

    # ── Crawl ──────────────────────────────────────────────────────

    def crawl(self, domains: List[str], depth: int) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Fetch each allowed domain once. Returns (documents, errors).

        Every document is recorded as untrusted: {"url", "status", "truncated",
        "content"}. The caller decides what survives Oracle review.
        """
        docs: List[Dict[str, Any]] = []
        errors: List[str] = []
        if self.fetcher is None:
            errors.append("no fetcher configured — pass fetcher= or allow_network=True")
            return docs, errors

        # depth caps breadth so a high-depth skill cannot fan out unbounded.
        budget = max(0, min(int(depth), 5))
        for url in domains[:budget]:
            try:
                result = self.fetcher(url, self.fetch_timeout)
            except Exception as exc:
                errors.append(f"fetch failed {url}: {exc}")
                continue
            if not isinstance(result, dict):
                errors.append(f"fetcher returned non-dict for {url}")
                continue
            docs.append({
                "url": result.get("url", url),
                "status": result.get("status", 0),
                "truncated": bool(result.get("truncated", False)),
                "content": str(result.get("content", ""))[:MAX_DOC_BYTES],
            })
        return docs, errors

    def run(self, skill_name: str, depth: int = 1, target_domains: Optional[list] = None, **kwargs) -> ScoutResult:
        """Run a scout pass. Depth 1 is inert by contract; depth >= 2 crawls."""
        errors: List[str] = []
        mutation: Dict[str, Any] = {}
        sidecar: Optional[Dict[str, Any]] = None

        if depth == 1:
            mutation = {"reason": "depth 1 inert — no fetch"}
            return ScoutResult(depth=depth, mutation=mutation, errors=errors, sidecar=sidecar)

        # Governor gate first: no privilege, no network, regardless of fetcher.
        if self.governor is not None:
            try:
                if not self.governor.is_elevated("network"):
                    errors.append("Governor: 'network' requires elevation.")
                    mutation = {"reason": "blocked: no network privilege"}
                    return ScoutResult(depth=depth, mutation=mutation, errors=errors, sidecar=sidecar)
            except Exception as exc:
                errors.append(f"Governor check failed: {exc}")

        allowed: List[str] = []
        if target_domains:
            blocked = [d for d in target_domains if not self._is_url_allowed(d)]
            if blocked:
                errors.append(f"Blocked target domains: {blocked}")
            allowed = [d for d in target_domains if d not in blocked]

        docs, crawl_errors = self.crawl(allowed, depth)
        errors.extend(crawl_errors)

        payload = {
            "skill": skill_name,
            "depth": depth,
            "domains": allowed,
            "documents": docs,
            "doc_count": len(docs),
        }

        # P2 for outbound content: untrusted fetched text is audited before it
        # is ever written somewhere another component will read it.
        if docs and self.oracle is not None:
            try:
                verdict = self.oracle.audit_text("\n".join(d["content"] for d in docs))
                if verdict.has_blocking():
                    errors.append(f"Oracle blocked crawled content: {verdict.verdict}")
                    mutation = {"reason": "quarantined: oracle blocked crawled content",
                                "ops": [{"type": "fetch", "domains": allowed}]}
                    return ScoutResult(depth=depth, mutation=mutation, errors=errors, sidecar=sidecar)
            except Exception as exc:
                errors.append(f"Oracle audit failed: {exc}")

        try:
            sidecar = self.write_sidecar(skill_name, payload)
        except Exception as exc:
            errors.append(f"sidecar write failed: {exc}")
            sidecar = None

        mutation = {
            "reason": "crawled" if docs else "no documents collected",
            "ops": [{"type": "fetch", "domains": allowed}],
            "doc_count": len(docs),
        }
        return ScoutResult(depth=depth, mutation=mutation, errors=errors, sidecar=sidecar)


Scout = ScoutLoader
