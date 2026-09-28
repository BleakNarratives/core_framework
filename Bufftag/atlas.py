#!/usr/bin/env python3
"""Append-only code-movement atlas for FKA/AKA path and import routing.

A route is explicit operator-approved evidence. The atlas records old and new
addresses, aliases, optional Python module names, content hashes at move time,
reason, actor, and source evidence. It never guesses from filename similarity.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

try:
    from Bufftag import bufftag
except ModuleNotFoundError:  # Allows `python Bufftag/atlas.py`.
    import bufftag


SCHEMA = "bufftag/move/v1"
ANCHOR_SCHEMA = "bufftag/anchor/v1"
DEFAULT_ATLAS = Path(".bufftag/moves.jsonl")
DEFAULT_ANCHOR = Path(".bufftag/moves.head.json")
GENESIS = bufftag.GENESIS_HASH
MAX_HASH_BYTES = bufftag.DEFAULT_MAX_BYTES
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\x00]+$")


class AtlasError(Exception):
    pass


@dataclass(frozen=True)
class Route:
    record_id: str
    old_path: str
    new_path: str
    aka: tuple[str, ...]
    old_module: str
    new_module: str
    actor: str
    reason: str
    evidence: tuple[str, ...]
    created_at: str
    new_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.record_id,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "aka": list(self.aka),
            "old_module": self.old_module,
            "new_module": self.new_module,
            "actor": self.actor,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "created_at": self.created_at,
            "new_sha256": self.new_sha256,
        }


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _timestamp(value: Any) -> str:
    timestamp = _text(value, "created_at")
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AtlasError("created_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AtlasError("created_at must include a timezone")
    return timestamp


def _text(value: Any, name: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise AtlasError(f"{name} must be a string")
    value = value.strip()
    if not value:
        raise AtlasError(f"{name} must not be empty")
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise AtlasError(f"{name} is empty, too long, or contains a control character")
    return value


def _relative_path(value: Any, name: str) -> str:
    path = _text(value, name)
    if not PATH_RE.fullmatch(path) or Path(path).is_absolute():
        raise AtlasError(f"{name} must be a safe workspace-relative path")
    return Path(path).as_posix()


def _module_name(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise AtlasError(f"{name} must be a string")
    value = value.strip()
    if not value:
        return ""
    if not MODULE_RE.fullmatch(value):
        raise AtlasError(f"{name} is not a valid dotted Python module name")
    return value


def _safe_workspace_path(workspace: Path, relative: str, *, require_file: bool) -> Path:
    root = workspace.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AtlasError(f"path escapes workspace: {relative}") from exc
    absolute = root / relative
    current = absolute.parent
    while current != root:
        if current.is_symlink():
            raise AtlasError(f"symlink parent is not allowed: {current}")
        current = current.parent
    if absolute.is_symlink():
        raise AtlasError(f"symlink path is not allowed: {absolute}")
    if require_file and not path.is_file():
        raise AtlasError(f"file does not exist: {relative}")
    return path


def _file_hash(path: Path) -> str:
    if path.stat().st_size > MAX_HASH_BYTES:
        raise AtlasError(f"file exceeds {MAX_HASH_BYTES} bytes: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in {"record_id", "signature"}}


def _record_id(identity: Mapping[str, Any]) -> str:
    return "move_" + hashlib.sha256(bufftag._canonical_bytes(identity)).hexdigest()[:24]


def _record_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(bufftag._canonical_bytes(record)).hexdigest()


def _anchor_identity(anchor: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in anchor.items() if key not in {"anchor_id", "signature"}}


def _anchor_id(identity: Mapping[str, Any]) -> str:
    return "anchor_" + hashlib.sha256(bufftag._canonical_bytes(identity)).hexdigest()[:24]


def _sign(identity: Mapping[str, Any], secret: bytes | None) -> dict[str, Any]:
    if secret is None:
        return {"mode": "unsigned"}
    return {
        "mode": "hmac-sha256",
        "value": hmac.new(secret, bufftag._canonical_bytes(identity), hashlib.sha256).hexdigest(),
    }


def _validate_record(
    record: Mapping[str, Any],
    previous: str,
    secret: bytes | None,
    *,
    allow_unsigned_existing: bool = False,
) -> list[str]:
    issues: list[str] = []
    if record.get("schema") != SCHEMA:
        issues.append("wrong schema")
    if record.get("previous") != previous:
        issues.append("broken hash chain")
    action = record.get("action")
    if action not in {"route", "retract"}:
        issues.append("unknown action")
    try:
        _relative_path(record.get("old_path"), "old_path")
    except AtlasError as exc:
        issues.append(str(exc))
    if action == "route":
        try:
            old_path = _relative_path(record.get("old_path"), "old_path")
            new_path = _relative_path(record.get("new_path"), "new_path")
            if old_path == new_path:
                issues.append("old_path equals new_path")
            aliases = record.get("aka")
            if not isinstance(aliases, list):
                issues.append("aka must be a list")
            else:
                for alias in aliases:
                    _relative_path(alias, "aka")
            _module_name(record.get("old_module"), "old_module")
            _module_name(record.get("new_module"), "new_module")
            _text(record.get("actor"), "actor")
            _text(record.get("reason"), "reason")
            if not isinstance(record.get("evidence"), list):
                issues.append("evidence must be a list")
            digest = record.get("new_sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                issues.append("invalid new_sha256")
            old_digest = record.get("old_sha256")
            if old_digest is not None and (
                not isinstance(old_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", old_digest)
            ):
                issues.append("invalid old_sha256")
            _timestamp(record.get("created_at"))
        except AtlasError as exc:
            issues.append(str(exc))
    elif action == "retract":
        try:
            _text(record.get("route_id"), "route_id")
            _text(record.get("actor"), "actor")
            _text(record.get("reason"), "reason")
            _timestamp(record.get("created_at"))
        except AtlasError as exc:
            issues.append(str(exc))
    identity = _identity(record)
    if record.get("record_id") != _record_id(identity):
        issues.append("invalid record id")
    signature = record.get("signature")
    if not isinstance(signature, dict):
        issues.append("missing signature")
    elif signature.get("mode") == "unsigned":
        if secret is not None and not allow_unsigned_existing:
            issues.append("unsigned record in signed verification context")
    elif signature.get("mode") == "hmac-sha256":
        if secret is None:
            issues.append("signature key unavailable")
        else:
            expected = hmac.new(secret, bufftag._canonical_bytes(identity), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, str(signature.get("value", ""))):
                issues.append("invalid signature")
    else:
        issues.append("unknown signature mode")
    return issues


def _read_records(
    path: Path,
    secret: bytes | None,
    *,
    allow_unsigned_existing: bool = False,
) -> tuple[list[dict[str, Any]], list[bufftag.Finding]]:
    if not path.exists():
        return [], []
    records: list[dict[str, Any]] = []
    findings: list[bufftag.Finding] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [bufftag.Finding("error", "atlas_unreadable", str(path), str(exc))]
    previous = GENESIS
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        display = f"{path}:{line_number}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(bufftag.Finding("error", "move_json", display, str(exc)))
            continue
        if not isinstance(record, dict):
            findings.append(bufftag.Finding("error", "move_shape", display, "record is not an object"))
            continue
        for issue in _validate_record(
            record,
            previous,
            secret,
            allow_unsigned_existing=allow_unsigned_existing,
        ):
            findings.append(bufftag.Finding("error", "move_invalid", display, issue))
        records.append(record)
        previous = _record_hash(record)
    return records, findings


def _validate_anchor(anchor: Mapping[str, Any], secret: bytes | None) -> list[str]:
    issues: list[str] = []
    if anchor.get("schema") != ANCHOR_SCHEMA:
        issues.append("wrong anchor schema")
    try:
        _text(anchor.get("actor"), "actor")
        _text(anchor.get("reason"), "reason")
        _timestamp(anchor.get("created_at"))
    except AtlasError as exc:
        issues.append(str(exc))
    count = anchor.get("ledger_records")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        issues.append("ledger_records must be a positive integer")
    head = anchor.get("ledger_head")
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{64}", head):
        issues.append("invalid ledger_head")
    identity = _anchor_identity(anchor)
    if anchor.get("anchor_id") != _anchor_id(identity):
        issues.append("invalid anchor id")
    signature = anchor.get("signature")
    if not isinstance(signature, dict):
        issues.append("missing anchor signature")
    elif signature.get("mode") == "unsigned":
        issues.append("unsigned anchor is not trusted rollback evidence")
    elif signature.get("mode") == "hmac-sha256":
        if secret is None:
            issues.append("anchor signature key unavailable")
        else:
            expected = hmac.new(
                secret, bufftag._canonical_bytes(identity), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, str(signature.get("value", ""))):
                issues.append("invalid anchor signature")
    else:
        issues.append("unknown anchor signature mode")
    return issues


def _read_anchor(
    path: Path, secret: bytes | None
) -> tuple[dict[str, Any] | None, list[bufftag.Finding]]:
    if not path.exists():
        return None, [bufftag.Finding("error", "anchor_missing", str(path), "external movement head does not exist")]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [bufftag.Finding("error", "anchor_unreadable", str(path), str(exc))]
    if not isinstance(value, dict):
        return None, [bufftag.Finding("error", "anchor_shape", str(path), "anchor is not an object")]
    issues = _validate_anchor(value, secret)
    findings = [
        bufftag.Finding("error", "anchor_invalid", str(path), issue) for issue in issues
    ]
    return value, findings


def _atomic_anchor_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise AtlasError(f"refusing symlink anchor path: {path}")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def create_anchor(
    *,
    atlas_path: str | Path,
    anchor_path: str | Path,
    actor: str,
    reason: str,
    secret: bytes,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Write an HMAC-authenticated head to separately controlled storage."""
    if not secret:
        raise AtlasError("rollback anchors require an HMAC key")
    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=True
    )
    if findings:
        raise AtlasError("refusing to anchor an invalid movement atlas")
    if not records:
        raise AtlasError("refusing to anchor an empty movement atlas")
    identity: dict[str, Any] = {
        "schema": ANCHOR_SCHEMA,
        "ledger_records": len(records),
        "ledger_head": _record_hash(records[-1]),
        "actor": _text(actor, "actor"),
        "reason": _text(reason, "reason"),
        "created_at": _timestamp(created_at or _now()),
    }
    anchor = {
        **identity,
        "anchor_id": _anchor_id(identity),
        "signature": _sign(identity, secret),
    }
    issues = _validate_anchor(anchor, secret)
    if issues:
        raise AtlasError(f"refusing invalid rollback anchor: {'; '.join(issues)}")
    encoded = json.dumps(
        anchor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8") + b"\n"
    _atomic_anchor_write(Path(anchor_path), encoded)
    return anchor


def verify_anchor(
    *, atlas_path: str | Path, anchor_path: str | Path, secret: bytes | None
) -> list[bufftag.Finding]:
    """Compare a signed external head with the valid local ledger prefix."""
    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=True
    )
    if findings:
        return findings
    anchor, anchor_findings = _read_anchor(Path(anchor_path), secret)
    findings.extend(anchor_findings)
    if anchor is None or anchor_findings:
        return findings
    count = anchor["ledger_records"]
    anchored_head = anchor["ledger_head"]
    if len(records) < count:
        local_head = _record_hash(records[-1]) if records else GENESIS
        if local_head != anchored_head:
            findings.append(
                bufftag.Finding(
                    "error",
                    "movement_rollback",
                    str(atlas_path),
                    f"local ledger has {len(records)} records but signed external head requires {count}",
                )
            )
        return findings
    local_anchored_head = _record_hash(records[count - 1])
    if not hmac.compare_digest(local_anchored_head, anchored_head):
        findings.append(
            bufftag.Finding(
                "error",
                "movement_rollback",
                str(atlas_path),
                "local ledger diverges from the signed external movement head",
            )
        )
    elif len(records) > count:
        findings.append(
            bufftag.Finding(
                "info",
                "anchor_behind",
                str(anchor_path),
                f"signed head is valid; ledger has advanced by {len(records) - count} records",
            )
        )
    return findings


def assert_anchor_current(
    *, atlas_path: str | Path, anchor_path: str | Path, secret: bytes | None
) -> None:
    findings = [
        finding
        for finding in verify_anchor(
            atlas_path=atlas_path, anchor_path=anchor_path, secret=secret
        )
        if finding.severity == "error"
    ]
    if findings:
        raise AtlasError("external movement head rejected: " + findings[0].message)


@contextlib.contextmanager
def _atlas_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _append(
    path: Path,
    record: Mapping[str, Any],
    secret: bytes | None,
    *,
    allow_unsigned_existing: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _atlas_lock(path):
        records, findings = _read_records(
            path, secret, allow_unsigned_existing=allow_unsigned_existing
        )
        if findings:
            raise AtlasError("refusing to append to an invalid movement atlas")
        previous = _record_hash(records[-1]) if records else GENESIS
        if record.get("previous") != previous:
            raise AtlasError("movement chain changed while appending")
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def record_route(
    *,
    workspace: str | Path,
    atlas_path: str | Path,
    old_path: str,
    new_path: str,
    actor: str,
    reason: str,
    aka: Sequence[str] = (),
    old_module: str = "",
    new_module: str = "",
    evidence: Sequence[str] = (),
    created_at: str | None = None,
    secret: bytes | None = None,
    allow_unsigned_existing: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    old_relative = _relative_path(old_path, "old_path")
    new_relative = _relative_path(new_path, "new_path")
    if old_relative == new_relative:
        raise AtlasError("old_path equals new_path")
    aliases = tuple(_relative_path(value, "aka") for value in aka)
    if new_relative in aliases or old_relative in aliases:
        raise AtlasError("old/new path cannot also be an alias")
    old_module_name = _module_name(old_module, "old_module")
    new_module_name = _module_name(new_module, "new_module")
    if bool(old_module_name) != bool(new_module_name):
        raise AtlasError("old_module and new_module must both be set or both be empty")
    new_file = _safe_workspace_path(root, new_relative, require_file=True)
    new_digest = _file_hash(new_file)
    old_file = _safe_workspace_path(root, old_relative, require_file=False)
    old_digest = _file_hash(old_file) if old_file.is_file() else None

    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=allow_unsigned_existing
    )
    if findings:
        raise AtlasError("refusing to record into an invalid movement atlas")
    try:
        existing_paths, existing_modules = active_routes(
            Path(atlas_path),
            secret,
            allow_unsigned_existing=allow_unsigned_existing,
        )
    except AtlasError as exc:
        raise AtlasError(f"refusing to record over an invalid route set: {exc}") from exc
    for address in (old_relative, *aliases):
        previous_route = existing_paths.get(address)
        if previous_route:
            raise AtlasError(f"active path/alias already maps elsewhere: {address}")
    if old_module_name:
        previous_route = existing_modules.get(old_module_name)
        if previous_route:
            raise AtlasError(f"active module already maps elsewhere: {old_module_name}")
    previous = _record_hash(records[-1]) if records else GENESIS
    identity: dict[str, Any] = {
        "schema": SCHEMA,
        "previous": previous,
        "action": "route",
        "old_path": old_relative,
        "new_path": new_relative,
        "aka": list(aliases),
        "old_module": old_module_name,
        "new_module": new_module_name,
        "actor": _text(actor, "actor"),
        "reason": _text(reason, "reason"),
        "evidence": [_text(value, "evidence") for value in evidence],
        "created_at": _timestamp(created_at or _now()),
        "old_sha256": old_digest,
        "new_sha256": new_digest,
    }
    record = {
        **identity,
        "record_id": _record_id(identity),
        "signature": _sign(identity, secret),
    }
    _append(
        Path(atlas_path),
        record,
        secret,
        allow_unsigned_existing=allow_unsigned_existing,
    )
    return record


def retract_route(
    *,
    atlas_path: str | Path,
    route_id: str,
    actor: str,
    reason: str,
    created_at: str | None = None,
    secret: bytes | None = None,
    allow_unsigned_existing: bool = False,
) -> dict[str, Any]:
    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=allow_unsigned_existing
    )
    if findings:
        raise AtlasError("refusing to retract in an invalid movement atlas")
    route = _text(route_id, "route_id", 100)
    if not re.fullmatch(r"move_[0-9a-f]{24}", route):
        raise AtlasError("route_id is malformed")
    if not any(record.get("record_id") == route and record.get("action") == "route" for record in records):
        raise AtlasError("target route does not exist")
    previous = _record_hash(records[-1]) if records else GENESIS
    identity = {
        "schema": SCHEMA,
        "previous": previous,
        "action": "retract",
        "old_path": next(
            record["old_path"] for record in records if record.get("record_id") == route
        ),
        "route_id": route,
        "actor": _text(actor, "actor"),
        "reason": _text(reason, "reason"),
        "created_at": _timestamp(created_at or _now()),
    }
    record = {**identity, "record_id": _record_id(identity), "signature": _sign(identity, secret)}
    _append(
        Path(atlas_path),
        record,
        secret,
        allow_unsigned_existing=allow_unsigned_existing,
    )
    return record


def active_routes(
    atlas_path: str | Path,
    secret: bytes | None = None,
    *,
    allow_unsigned_existing: bool = False,
) -> tuple[dict[str, Route], dict[str, Route]]:
    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=allow_unsigned_existing
    )
    if findings:
        details = "; ".join(finding.message for finding in findings[:3])
        raise AtlasError(f"movement atlas failed integrity verification: {details}")
    route_records: dict[str, dict[str, Any]] = {}
    retracted: set[str] = set()
    for record in records:
        if record["action"] == "route":
            route_records[record["record_id"]] = record
        elif record["action"] == "retract":
            retracted.add(record["route_id"])
    live_records = [record for record in route_records.values() if record["record_id"] not in retracted]
    by_path: dict[str, Route] = {}
    by_alias: dict[str, Route] = {}
    by_module: dict[str, Route] = {}
    for raw in live_records:
        route = Route(
            record_id=raw["record_id"],
            old_path=raw["old_path"],
            new_path=raw["new_path"],
            aka=tuple(raw["aka"]),
            old_module=raw["old_module"],
            new_module=raw["new_module"],
            actor=raw["actor"],
            reason=raw["reason"],
            evidence=tuple(raw["evidence"]),
            created_at=raw["created_at"],
            new_sha256=raw["new_sha256"],
        )
        for key, mapping in ((route.old_path, by_path), *((alias, by_alias) for alias in route.aka)):
            previous = mapping.get(key)
            if previous and previous.new_path != route.new_path:
                raise AtlasError(f"conflicting active route for {key}")
            mapping[key] = route
        if route.old_module:
            previous = by_module.get(route.old_module)
            if previous and previous.new_module != route.new_module:
                raise AtlasError(f"conflicting active module route for {route.old_module}")
            by_module[route.old_module] = route
    return {**by_path, **by_alias}, by_module


def _route_for_path(candidate: str | Path, workspace: Path, mapping: dict[str, Route]) -> Route | None:
    raw = Path(candidate)
    if raw.is_absolute():
        try:
            relative = raw.resolve().relative_to(workspace.resolve()).as_posix()
        except ValueError:
            relative = raw.as_posix().lstrip("/")
    else:
        relative = Path(candidate).as_posix()
    return mapping.get(relative)


def resolve_path(candidate: str | Path, workspace: str | Path, mapping: dict[str, Route]) -> Route | None:
    return _route_for_path(candidate, Path(workspace), mapping)


def verify_atlas(
    *,
    workspace: str | Path,
    atlas_path: str | Path,
    secret: bytes | None,
    anchor_path: str | Path | None = None,
    allow_unsigned_existing: bool = False,
) -> bufftag.Report:
    root = Path(workspace).resolve()
    records, findings = _read_records(
        Path(atlas_path), secret, allow_unsigned_existing=allow_unsigned_existing
    )
    if anchor_path is not None and not findings:
        findings.extend(verify_anchor(atlas_path=atlas_path, anchor_path=anchor_path, secret=secret))
    if not Path(atlas_path).exists():
        findings.append(bufftag.Finding("error", "atlas_missing", str(atlas_path), "movement atlas does not exist"))
    try:
        by_path, by_module = active_routes(
            Path(atlas_path),
            secret,
            allow_unsigned_existing=allow_unsigned_existing,
        )
        routes = list({route.record_id: route for route in by_path.values()}.values())
    except AtlasError as exc:
        findings.append(bufftag.Finding("error", "atlas_routes", str(atlas_path), str(exc)))
        routes = []
    for route in routes:
        try:
            target = _safe_workspace_path(root, route.new_path, require_file=True)
        except AtlasError as exc:
            findings.append(bufftag.Finding("error", "route_target", route.new_path, str(exc)))
            continue
        try:
            current = _file_hash(target)
        except (OSError, AtlasError) as exc:
            findings.append(bufftag.Finding("error", "route_unreadable", route.new_path, str(exc)))
            continue
        if current != route.new_sha256:
            findings.append(
                bufftag.Finding(
                    "warn",
                    "route_content_changed",
                    route.new_path,
                    "target changed after the move; route remains valid but move-time hash differs",
                )
            )
    return bufftag.Report(str(root), len(routes), len(records), findings)


def _atlas_path(workspace: Path, value: str | None) -> Path:
    return (workspace / (value or DEFAULT_ATLAS)).resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("record", help="append an explicit path/module movement route")
    record.add_argument("workspace")
    record.add_argument("--atlas")
    record.add_argument("--old-file", required=True)
    record.add_argument("--new-file", required=True)
    record.add_argument("--actor", required=True)
    record.add_argument("--reason", required=True)
    record.add_argument("--aka", action="append", default=[])
    record.add_argument("--old-module", default="")
    record.add_argument("--new-module", default="")
    record.add_argument("--evidence", action="append", default=[])
    record.add_argument("--recorded-at")
    record.add_argument("--anchor", help="require this separately controlled signed head before appending")
    record.add_argument("--signing-key-env", default="BUFFTAG_KEY")

    retract = sub.add_parser("retract", help="append a retraction for a route")
    retract.add_argument("workspace")
    retract.add_argument("--atlas")
    retract.add_argument("--route-id", required=True)
    retract.add_argument("--actor", required=True)
    retract.add_argument("--reason", required=True)
    retract.add_argument("--recorded-at")
    retract.add_argument("--anchor", help="require this separately controlled signed head before appending")
    retract.add_argument("--signing-key-env", default="BUFFTAG_KEY")

    anchor = sub.add_parser("anchor", help="write a signed rollback head to separate storage")
    anchor.add_argument("workspace")
    anchor.add_argument("--atlas")
    anchor.add_argument("--anchor", help="external head path; defaults beside the atlas")
    anchor.add_argument("--actor", required=True)
    anchor.add_argument("--reason", required=True)
    anchor.add_argument("--created-at")
    anchor.add_argument("--signing-key-env", default="BUFFTAG_KEY")

    verify = sub.add_parser("verify", help="verify movement chain, signatures, targets, and collisions")
    verify.add_argument("workspace")
    verify.add_argument("--atlas")
    verify.add_argument("--anchor", help="verify against this separately controlled signed head")
    verify.add_argument("--signing-key-env", default="BUFFTAG_KEY")
    verify.add_argument("--json", action="store_true")

    resolve = sub.add_parser("resolve", help="resolve an old path, alias, or old module name")
    resolve.add_argument("workspace")
    resolve.add_argument("target")
    resolve.add_argument("--atlas")
    resolve.add_argument("--module", action="store_true")
    resolve.add_argument("--anchor", help="require this separately controlled signed head before resolving")
    resolve.add_argument("--signing-key-env", default="BUFFTAG_KEY")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    workspace = Path(args.workspace).resolve()
    atlas_path = _atlas_path(workspace, args.atlas)
    anchor_path = None
    if args.command == "anchor":
        configured_anchor = Path(args.anchor).expanduser() if args.anchor else atlas_path.with_name(DEFAULT_ANCHOR.name)
        anchor_path = configured_anchor if configured_anchor.is_absolute() else (workspace / configured_anchor)
    elif hasattr(args, "anchor") and args.anchor:
        configured_anchor = Path(args.anchor).expanduser()
        anchor_path = configured_anchor if configured_anchor.is_absolute() else (workspace / configured_anchor)
    try:
        secret = bufftag._secret_from_env(getattr(args, "signing_key_env", None))
        if args.command != "anchor" and anchor_path is not None:
            assert_anchor_current(atlas_path=atlas_path, anchor_path=anchor_path, secret=secret)
        if args.command == "anchor":
            result = create_anchor(
                atlas_path=atlas_path,
                anchor_path=anchor_path,
                actor=args.actor,
                reason=args.reason,
                created_at=args.created_at,
                secret=secret,
            )
        elif args.command == "record":
            result = record_route(
                workspace=workspace,
                atlas_path=atlas_path,
                old_path=args.old_file,
                new_path=args.new_file,
                actor=args.actor,
                reason=args.reason,
                aka=args.aka,
                old_module=args.old_module,
                new_module=args.new_module,
                evidence=args.evidence,
                created_at=args.recorded_at,
                secret=secret,
                allow_unsigned_existing=anchor_path is not None,
            )
        elif args.command == "retract":
            result = retract_route(
                atlas_path=atlas_path,
                route_id=args.route_id,
                actor=args.actor,
                reason=args.reason,
                created_at=args.recorded_at,
                secret=secret,
                allow_unsigned_existing=anchor_path is not None,
            )
        elif args.command == "verify":
            report = verify_atlas(
                workspace=workspace,
                atlas_path=atlas_path,
                secret=secret,
                anchor_path=anchor_path,
                allow_unsigned_existing=anchor_path is not None,
            )
            if args.json:
                print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
            else:
                for finding in report.findings:
                    print(f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.message}")
                print(f"{'OK' if report.ok else 'FAILED'}: routes={report.files_scanned} records={report.receipt_count}")
            return 0 if report.ok else 1
        else:
            by_path, by_module = active_routes(
                atlas_path,
                secret,
                allow_unsigned_existing=anchor_path is not None,
            )
            route = by_module.get(args.target) if args.module else _route_for_path(args.target, workspace, by_path)
            result = route.as_dict() if route else {"ok": False, "target": args.target, "route": None}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (AtlasError, bufftag.BufftagError) as exc:
        print(f"bufftag atlas: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
