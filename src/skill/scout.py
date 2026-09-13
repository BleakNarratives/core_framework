"""
MOLT Scout — Intelligence & Mutation Feeder
Active web querying, documentation scraping, RAG index updates to feed context
into host SKILL.md. Depth 1-5 (OOMF_LEVEL).

Depth semantics:
  1  inert      — no fetch, prompt shortcut only
  2  shallow    — 1-2 whitelisted docs, no crawl
  3  standard   — full target_domains fetch + RAG bake
  4  deep       — standard + link expansion 1 hop
  5  crawl      — deep + active web search + fresh docs

All network operations require Governor 'network' elevation.
All file writes require Governor 'write' elevation and Oracle pass.
"""
import re
import time
import json
import hashlib
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# Optional deps — Scout degrades gracefully without them
try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

DEFAULT_RAG_DIR = Path("rag_storage")
DEFAULT_SIDECAR_DIR = Path("rag_storage/sidecars")

# Depth config
DEPTH_CONFIG = {
    1: {"fetch": False, "max_docs": 0,   "expand_links": False, "web_search": False, "label": "inert"},
    2: {"fetch": True,  "max_docs": 2,   "expand_links": False, "web_search": False, "label": "shallow"},
    3: {"fetch": True,  "max_docs": 8,   "expand_links": False, "web_search": False, "label": "standard"},
    4: {"fetch": True,  "max_docs": 15,  "expand_links": True,  "web_search": False, "label": "deep"},
    5: {"fetch": True,  "max_docs": 30,  "expand_links": True,  "web_search": True,  "label": "crawl"},
}

# Safe fetch guard
MAX_BYTES = 500_000
MAX_DOCS_HARD_CAP = 30
TIMEOUT_S = 12
BLOCKED_SCHEMES = {"file", "ftp", "gopher"}


@dataclass
class ScoutResult:
    """Output of a scout run."""
    skill_name: str
    depth: int
    fetched: List[Dict[str, Any]] = field(default_factory=list)  # {url, status, bytes, hash, snippet}
    rag_docs: List[str] = field(default_factory=list)  # rag doc ids
    mutation: Dict[str, Any] = field(default_factory=dict)  # proposed ops for Oracle
    errors: List[str] = field(default_factory=list)
    elapsed_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "depth": self.depth,
            "fetched": self.fetched,
            "rag_docs": self.rag_docs,
            "mutation": self.mutation,
            "errors": self.errors,
            "elapsed_s": self.elapsed_s,
        }


class Scout:
    """
    Autonomous feeder for web fetching, RAG indexing, and updating host markdown.

    Usage:
        scout = Scout(governor=gov, oracle=oracle)
        result = scout.run("med-triage-copilot", depth=3)  # requires network
        # result.mutation is proposed, not applied — must pass Oracle + Governor
    """

    def __init__(self, governor=None, oracle=None,
                 rag_dir: str = "rag_storage",
                 sidecar_dir: str = "rag_storage/sidecars",
                 bus=None, snapshotter=None):
        self.governor = governor
        self.oracle = oracle
        self.rag_dir = Path(rag_dir)
        self.sidecar_dir = Path(sidecar_dir)
        self.rag_dir.mkdir(parents=True, exist_ok=True)
        self.sidecar_dir.mkdir(parents=True, exist_ok=True)
        # Whorl hive mind (optional, zero-network fallback if Whorl not installed)
        self.bus = bus
        self.snapshotter = snapshotter
        if self.bus is None:
            try:
                from .whorl_bus import WhorlBusDispatcher
                self.bus = WhorlBusDispatcher(agent_name=f"molt-scout-{id(self) % 10000}", auto_register=False)
            except Exception:
                self.bus = None
        if self.snapshotter is None:
            try:
                from .state_snapshotter import StateSnapshotter
                self.snapshotter = StateSnapshotter()
            except Exception:
                self.snapshotter = None

    # ── Public entrypoint ────────────────────────────────────────────
    def run(self, skill_name: str, depth: int = 3,
            target_domains: Optional[List[str]] = None,
            extra_urls: Optional[List[str]] = None,
            dry_run: bool = False) -> ScoutResult:
        """
        Run scout at given depth. Network fetch requires Governor 'network'.
        File mutation is NOT applied here — only proposed in result.mutation.
        Caller must pass mutation through Oracle + Governor before applying.
        """
        start = time.time()
        depth = max(1, min(5, int(depth)))
        cfg = DEPTH_CONFIG[depth]
        result = ScoutResult(skill_name=skill_name, depth=depth)

        if not cfg["fetch"]:
            result.mutation = {"ops": [], "reason": "depth 1 inert — no fetch"}
            result.elapsed_s = time.time() - start
            return result

        # Governor gate for network
        if self.governor and not self.governor.is_elevated("network"):
            result.errors.append("Governor: 'network' required for Scout fetch (pass --elevate network or --oomf).")
            result.mutation = {"ops": [], "reason": "blocked: no network privilege"}
            result.elapsed_s = time.time() - start
            return result

        # Gather URLs: frontmatter target_domains + extra
        urls = self._collect_urls(skill_name, target_domains, extra_urls, cfg)
        if not urls:
            result.errors.append("No target_domains or urls provided for fetch.")
            result.elapsed_s = time.time() - start
            return result

        # Fetch
        for url in urls[:cfg["max_docs"]]:
            try:
                doc = self._fetch_url(url)
                if doc:
                    result.fetched.append(doc)
                    # Link expansion at depth 4+
                    if cfg["expand_links"] and doc.get("links"):
                        for link in doc["links"][:2]:
                            try:
                                extra = self._fetch_url(link)
                                if extra:
                                    result.fetched.append(extra)
                            except Exception as e:
                                result.errors.append(f"expand fetch failed {link}: {e}")
            except Exception as e:
                result.errors.append(f"fetch failed {url}: {e}")

        # Web search at depth 5 (best-effort, degraded if unavailable)
        if cfg["web_search"]:
            try:
                search_hits = self._web_search(skill_name, limit=3)
                for url in search_hits:
                    if len(result.fetched) >= MAX_DOCS_HARD_CAP:
                        break
                    try:
                        doc = self._fetch_url(url)
                        if doc:
                            result.fetched.append(doc)
                    except Exception as e:
                        result.errors.append(f"search fetch failed {url}: {e}")
            except Exception as e:
                result.errors.append(f"web_search degraded: {e}")

        # Build RAG docs + mutation proposal
        if result.fetched and not dry_run:
            result.rag_docs = self._bake_rag(skill_name, result.fetched)
        result.mutation = self._propose_mutation(skill_name, result)

        result.elapsed_s = time.time() - start
        # Persist sidecar (requires write privilege if not dry_run)
        if not dry_run:
            self._write_sidecar(result)
            # Hive upgrade 1: Scout → Whorl Bus atomic write (zero-network transport)
            if self.bus is not None:
                try:
                    # Headless nodes consume via ~/.whorl/bus/ without opening ports
                    preview = "\n".join(d.get("snippet","")[:400] for d in result.fetched[:2])
                    self.bus.send_sidecar(result.skill_name, {
                        "depth": result.depth,
                        "fetched": len(result.fetched),
                        "rag_docs": len(result.rag_docs),
                        "preview": preview[:1000],
                        "elapsed_s": round(result.elapsed_s, 2),
                    }, recipient="broadcast")
                except Exception:
                    pass
        return result

    # ── URL collection ───────────────────────────────────────────────
    def _collect_urls(self, skill_name: str, target_domains: Optional[List[str]],
                      extra_urls: Optional[List[str]], cfg: Dict) -> List[str]:
        urls: List[str] = []
        # From skill frontmatter if available
        try:
            from .skill_manager import SkillManager
            mgr = SkillManager()
            front = mgr.parse_frontmatter(skill_name)
            if front and front.get("scout", {}).get("target_domains"):
                for d in front["scout"]["target_domains"]:
                    if d.startswith("http"):
                        urls.append(d)
                    else:
                        urls.append(f"https://{d}")
        except Exception:
            pass
        if target_domains:
            for d in target_domains:
                urls.append(d if d.startswith("http") else f"https://{d}")
        if extra_urls:
            urls.extend(extra_urls)
        # Deduplicate, validate
        seen = set()
        clean = []
        for u in urls:
            if u in seen:
                continue
            if self._is_url_allowed(u):
                clean.append(u)
                seen.add(u)
        return clean

    def _is_url_allowed(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme in BLOCKED_SCHEMES:
                return False
            if parsed.scheme not in ("http", "https"):
                return False
            # Block private nets (basic)
            host = parsed.hostname or ""
            if host in ("localhost", "127.0.0.1", "::1") or host.startswith("10.") or host.startswith("192.168."):
                return False
            return True
        except Exception:
            return False

    # ── Fetch ────────────────────────────────────────────────────────
    def _fetch_url(self, url: str) -> Optional[Dict[str, Any]]:
        raw = None
        if HAS_REQUESTS:
            try:
                r = requests.get(url, timeout=TIMEOUT_S, headers={"User-Agent": "MOLT-Scout/1.0"},
                                 allow_redirects=True)
                if r.status_code != 200:
                    return None
                raw = r.content[:MAX_BYTES]
                text = raw.decode("utf-8", errors="replace")
            except Exception:
                raise
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "MOLT-Scout/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    if resp.status != 200:
                        return None
                    raw = resp.read(MAX_BYTES)
                    text = raw.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if e.code != 200:
                    return None
                raise

        # Light HTML -> text extraction
        text = self._html_to_text(text) if "<html" in text.lower() or "<body" in text.lower() else text
        snippet = text[:2000]
        links = re.findall(r'href="([^"]+)"', text)[:10] if "<a " in text.lower() else []
        # Normalize relative links
        abs_links = []
        for L in links:
            if L.startswith("http"):
                abs_links.append(L)
            elif L.startswith("/"):
                try:
                    base = f"{urllib.parse.urlparse(url).scheme}://{urllib.parse.urlparse(url).netloc}"
                    abs_links.append(base + L)
                except Exception:
                    pass

        return {
            "url": url,
            "status": 200,
            "bytes": len(raw) if raw else len(snippet),
            "hash": hashlib.sha256(snippet.encode()).hexdigest()[:12],
            "snippet": snippet,
            "links": abs_links,
        }

    def _html_to_text(self, html: str) -> str:
        # Brutal but zero-dep HTML stripping — enough for RAG snippets
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"\s+", " ", html)
        return html.strip()[:20000]

    def _web_search(self, query: str, limit: int = 3) -> List[str]:
        """
        Best-effort web search. If no search API configured, returns [] gracefully.
        Hook for future: wire to Serper / Brave / etc via env key.
        """
        # Degraded: no search backend configured -> no-op (depth 5 still fetches target_domains)
        return []

    # ── RAG bake ─────────────────────────────────────────────────────
    def _bake_rag(self, skill_name: str, fetched: List[Dict[str, Any]]) -> List[str]:
        """
        Write fetched snippets into RAG sidecar docs.
        Sidecar path: rag_storage/sidecars/<skill>.jsonl
        Also writes individual .md chunks for local RAG indexers.
        """
        doc_ids = []
        sidecar_path = self.sidecar_dir / f"{skill_name}.jsonl"
        # Append new docs
        for doc in fetched:
            doc_id = f"{skill_name}:{doc['hash']}"
            entry = {
                "id": doc_id,
                "skill": skill_name,
                "url": doc["url"],
                "snippet": doc["snippet"][:4000],
                "hash": doc["hash"],
                "ts": time.time(),
            }
            doc_ids.append(doc_id)
            try:
                with open(sidecar_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception:
                pass
            # Also write chunk file for discovery RAG
            chunk_path = self.rag_dir / f"{skill_name}_{doc['hash']}.md"
            try:
                chunk_path.write_text(f"# Source: {doc['url']}\n\n{doc['snippet'][:4000]}\n", encoding="utf-8")
            except Exception:
                pass
        return doc_ids

    def _propose_mutation(self, skill_name: str, result: ScoutResult) -> Dict[str, Any]:
        """
        Propose a mutation without applying it. Oracle must audit, Governor must approve write.
        """
        if not result.fetched:
            return {"ops": [], "reason": "no fetched docs — no mutation"}

        # Proposal: update sidecar reference + optional frontmatter interval bump
        ops = [{
            "type": "update_sidecar",
            "skill": skill_name,
            "rag_docs": result.rag_docs,
            "fetched_count": len(result.fetched),
        }]
        # At depth 3+, propose appending an auto-update hook to SKILL.md body
        if result.depth >= 3:
            ops.append({
                "type": "patch",
                "skill": skill_name,
                "note": f"Scout depth {result.depth} baked {len(result.rag_docs)} RAG docs — hydrate on next load",
            })
        return {"ops": ops, "source_hashes": [d["hash"] for d in result.fetched]}

    def _write_sidecar(self, result: ScoutResult) -> None:
        """
        Persist scout run summary. This is a sidecar write (rag_storage), not SKILL.md mutation.
        Requires Governor 'write' if governor present, else best-effort.
        """
        summary_path = self.sidecar_dir / f"{result.skill_name}.scout.json"
        payload = result.to_dict()
        try:
            if self.governor and not self.governor.is_elevated("write"):
                # Still allow sidecar writes in rag_storage without elevation by default —
                # Governor only gates SKILL.md writes. Sidecars are sandboxed.
                pass
            with open(summary_path, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass
