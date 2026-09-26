"""
verified_cache — verify before you trust state you did not just write.

The pattern
-----------
Any agent that caches state to disk creates a trust inversion. The cache lives
in a directory that every other process on the machine can write, and something
downstream reads it back as if it were trustworthy. That produces an ordering
bug with a security consequence:

    WRONG:  read cache  ->  use it as context
    RIGHT:  read cache  ->  verify hash -> THEN use it as context

The first line is what almost everyone writes, because it is the obvious one.
It means anyone who can write a file can choose what your agent believes. A
poisoned cache is not a bug in the cache; it is a code-execution primitive
aimed at the reader.

This library makes the right ordering the only one available. Every read
verifies a content hash before returning anything, and a failed verification
returns *nothing* -- not a payload with a warning attached. There is no "trust
me" flag, no `verify=False`, because the unsafe path should not be one
keystroke away.

The sidecar pattern — a small JSON file beside a skill or agent, carrying
hydrated context that other processes consume — is the case that motivated
this, but nothing here is specific to it. RAG stores, prompt caches, evaluation
snapshots and model checkpoints have the same shape and the same hole.

Trust model
-----------
The digest covers the payload only, never the envelope. A verifier that hashes
the whole file is verifying the attacker's own metadata too.

This is tamper *detection*, not tamper *prevention*. An attacker who can write
the file can also write a matching digest -- they have the payload, so they can
hash it. What this buys you is that a corrupted, truncated, stale or
half-written cache cannot be silently consumed, and that a writer which fails
mid-update cannot leave a plausible-looking lie behind. If you need a guarantee
against a writer who is also the adversary, you need a signature against a key
they do not hold; that is deliberately out of scope here, and pretending
otherwise would be the more dangerous library.

Stdlib only. No network. No clock or randomness in the trust decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

__all__ = [
    "SidecarStore", "Verification", "Digest", "TrustError",
    "canonical_json", "digest_of", "UNSUPPORTED_ALGOS",
]

# Algorithms this library will accept. Whitelisting rather than trusting a
# stored algorithm name matters: an attacker who can write the envelope could
# otherwise nominate something absurd, or a weakened variant, to be "verified"
# with. Refusing unknown values is fail-closed.
UNSUPPORTED_ALGOS = frozenset({"", None, "md5", "sha1", "none", "null"})

SUPPORTED_ALGOS = {
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
    "blake2b": hashlib.blake2b,
}


class TrustError(Exception):
    """Raised only by verify_or_raise; the normal API returns a result."""


@dataclass(frozen=True)
class Digest:
    """A content digest plus the algorithm that produced it."""

    algo: str
    value: str

    def to_dict(self) -> Dict[str, str]:
        return {"algo": self.algo, "value": self.value}


@dataclass
class Verification:
    """The result of a read attempt.

    `ok` is the only field a caller should branch on. When False, `payload` is
    always None -- there is deliberately no way to get the unverified bytes out
    of this object, because every "but I still want the data" path is how the
    bug gets reintroduced.
    """

    ok: bool
    payload: Optional[Any] = None
    reason: str = ""
    # Populated on failure so an operator can tell a tampered cache from a
    # truncated one from a cache that was never written.
    detail: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok

    def unwrap(self) -> Any:
        """Return the payload or raise. For call sites that cannot proceed."""
        if not self.ok:
            raise TrustError(self.reason)
        return self.payload


def canonical_json(payload: Any) -> str:
    """Stable serialization for hashing.

    sort_keys so the digest covers content rather than key order, and compact
    separators so it does not cover incidental whitespace. Without this, a
    re-serialized-but-identical payload would fail verification and look like
    tampering.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(payload: Any, algo: str = "sha256") -> Digest:
    if algo in UNSUPPORTED_ALGOS or algo not in SUPPORTED_ALGOS:
        raise ValueError(f"unsupported digest algorithm: {algo!r}")
    h = SUPPORTED_ALGOS[algo]()
    h.update(canonical_json(payload).encode("utf-8"))
    return Digest(algo=algo, value=h.hexdigest())


def _atomic_write(path: Path, text: str) -> None:
    """Write via temp file + rename so a reader never sees a partial file.

    This is not a durability guarantee -- there is no fsync -- it is an
    atomicity guarantee: a concurrent reader sees either the old file or the
    new one, never a truncated one. A truncated cache is exactly the case that
    makes a reader believe a partial update is complete.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class SidecarStore:
    """A directory of hashed, atomically-written JSON state.

    `root` is untrusted by construction. Treat it as you would a /tmp handed to
    you by a stranger: readable, and therefore writable, by anything local.
    """

    DEFAULT_MAX_BYTES = 4 * 1024 * 1024

    def __init__(
        self,
        root: os.PathLike | str,
        algo: str = "sha256",
        max_bytes: int = DEFAULT_MAX_BYTES,
        signer: Optional[Callable[[bytes], str]] = None,
    ):
        if algo in UNSUPPORTED_ALGOS or algo not in SUPPORTED_ALGOS:
            raise ValueError(
                f"unsupported digest algorithm: {algo!r}; "
                f"choose one of {sorted(SUPPORTED_ALGOS)}"
            )
        self.root = Path(root)
        self.algo = algo
        self.max_bytes = max_bytes
        # Optional HMAC signer. When present, a digest alone is not enough --
        # an attacker who can write the file can also compute an unkeyed hash
        # over their own payload. See the module docstring on why this is
        # detection, not prevention.
        self._signer = signer

    # ── write ────────────────────────────────────────────────────────────────

    def path_for(self, key: str) -> Path:
        if not key or "/" in key or key in (".", "..") or "\\" in key:
            raise ValueError(f"unsafe cache key: {key!r}")
        return self.root / f"{key}.json"

    def write(self, key: str, payload: Any, *, extra: Optional[Dict[str, Any]] = None) -> Digest:
        """Atomically persist payload under key, stamped with its digest."""
        text = canonical_json(payload)
        encoded = text.encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise ValueError(f"payload is {len(encoded)} bytes, over the {self.max_bytes} limit")

        dg = digest_of(payload, self.algo)
        envelope: Dict[str, Any] = {
            "key": key,
            "algo": self.algo,
            "digest": dg.value,
            "written_at": time.time(),
            "version": 1,
            "payload": payload,
        }
        if extra:
            envelope["meta"] = extra
        if self._signer is not None:
            envelope["sig"] = hmac.new(
                dg.value.encode(), canonical_json(payload).encode(), hashlib.sha256
            ).hexdigest()

        _atomic_write(self.path_for(key), json.dumps(envelope, indent=2, sort_keys=True) + "\n")
        return dg

    # ── read: verify, then trust ─────────────────────────────────────────────

    def read(self, key: str) -> Verification:
        """Verify first. Returns ok=False with payload withheld on any problem."""
        path = self.path_for(key)
        if not path.exists():
            return Verification(False, reason="absent", detail={"path": str(path)})

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            return Verification(False, reason="unreadable", detail={"error": str(exc)})
        except UnicodeDecodeError as exc:
            return Verification(False, reason="undecodable", detail={"error": str(exc)})

        try:
            env = json.loads(raw)
        except json.JSONDecodeError as exc:
            return Verification(False, reason="malformed", detail={"error": str(exc)})

        if not isinstance(env, dict):
            return Verification(False, reason="malformed", detail={"error": "envelope is not an object"})
        if "payload" not in env:
            return Verification(False, reason="malformed", detail={"error": "no payload field"})

        algo = env.get("algo")
        if algo in UNSUPPORTED_ALGOS or algo not in SUPPORTED_ALGOS:
            # Fail closed on an unknown algorithm rather than falling back to a
            # default: "verify it the way the file asks" is attacker control.
            return Verification(False, reason="unsupported_algo", detail={"algo": algo})

        stored = env.get("digest")
        if not isinstance(stored, str) or not stored:
            return Verification(False, reason="missing_digest")

        try:
            actual = digest_of(env["payload"], algo)
        except (ValueError, TypeError) as exc:
            return Verification(False, reason="unhashable", detail={"error": str(exc)})

        if not hmac.compare_digest(stored, actual.value):
            return Verification(
                False,
                reason="digest_mismatch",
                detail={"stored": stored[:12], "actual": actual.value[:12]},
            )

        if self._signer is not None:
            sig = env.get("sig")
            if not isinstance(sig, str) or not sig:
                return Verification(False, reason="missing_signature")
            expected = hmac.new(
                actual.value.encode(), canonical_json(env["payload"]).encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return Verification(False, reason="bad_signature")

        return Verification(True, payload=env["payload"])

    def verify_or_raise(self, key: str) -> Any:
        return self.read(key).unwrap()

    # ── housekeeping ─────────────────────────────────────────────────────────

    def keys(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.json"))

    def delete(self, key: str) -> bool:
        p = self.path_for(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def audit(self) -> Dict[str, Dict[str, Any]]:
        """Verify every entry and report per-key status.

        Use this to find out *whether* a cache has been tampered with before
        you go debugging a strange model behaviour downstream of it.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for k in self.keys():
            v = self.read(k)
            out[k] = {"ok": v.ok, "reason": v.reason, **({"detail": v.detail} if v.detail else {})}
        return out
