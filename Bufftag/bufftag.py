#!/usr/bin/env python3
"""Bufftag: strict, drift-aware provenance tags and tamper-evident receipts.

The header records an assertion. A receipt binds that assertion to file content.
Receipts can be HMAC-signed with a key kept outside the repository. Without a
signature, Bufftag detects accidental drift and log edits but cannot prove who
created a record or stop a privileged attacker from rebuilding the log.
"""

from __future__ import annotations

import argparse
import ast
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
import time
import tokenize
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


VERSION = "bufftag/v1"
HEADER_START = "# [BUFFTAG v1]"
HEADER_END = "# [/BUFFTAG]"
HTML_HEADER_START = "<!-- [BUFFTAG v1] -->"
HTML_HEADER_END = "<!-- [/BUFFTAG] -->"
RECEIPT_SCHEMA = "bufftag/receipt/v1"
GENESIS_HASH = "0" * 64
DEFAULT_MAX_BYTES = 2_000_000
SUPPORTED_SUFFIXES = {
    ".bash", ".html", ".js", ".jsx", ".md", ".py", ".sh", ".text",
    ".toml", ".ts", ".tsx", ".txt", ".yaml", ".yml",
}
DEFAULT_EXCLUDED_DIRS = {
    ".git", ".hg", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".svn",
    ".tox", ".venv", "__pycache__", "build", "dist", "node_modules", "venv",
}
REQUIRED_METADATA = {"author", "deps", "origin", "pillar", "recorded_at", "role"}
FIELD_RE = re.compile(r"^# ([a-z_]+): (.*)$")
HTML_FIELD_RE = re.compile(r"^<!-- ([a-z_]+): (.*) -->$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
PY_ENCODING_RE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")


class BufftagError(Exception):
    """Base class for expected, user-facing failures."""


class HeaderError(BufftagError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Header:
    metadata: dict[str, str]
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass
class Report:
    root: str
    files_scanned: int
    receipt_count: int
    findings: list[Finding]

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "bufftag/report/v1",
            "root": self.root,
            "ok": self.ok,
            "files_scanned": self.files_scanned,
            "receipt_count": self.receipt_count,
            "findings": [finding.as_dict() for finding in self.findings],
        }


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _validate_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    keys = set(metadata)
    if keys != REQUIRED_METADATA:
        missing = sorted(REQUIRED_METADATA - keys)
        extra = sorted(keys - REQUIRED_METADATA)
        raise HeaderError(
            "header_fields",
            f"required={sorted(REQUIRED_METADATA)} missing={missing} extra={extra}",
        )

    clean: dict[str, str] = {}
    for key, raw_value in metadata.items():
        if not isinstance(raw_value, str):
            raise HeaderError("header_field_type", f"{key} must be a string")
        value = raw_value.strip()
        if not value or value != raw_value:
            raise HeaderError("header_field_spacing", f"{key} must be non-empty and trimmed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise HeaderError("header_control_character", f"{key} contains a control character")
        if len(value) > 500:
            raise HeaderError("header_field_too_long", f"{key} exceeds 500 characters")
        if key in {"origin", "pillar", "author"} and not IDENTIFIER_RE.fullmatch(value):
            raise HeaderError(
                "header_identifier",
                f"{key} must match {IDENTIFIER_RE.pattern}",
            )
        clean[key] = value

    recorded_at = clean["recorded_at"]
    try:
        parsed = dt.datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HeaderError("header_timestamp", "recorded_at must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HeaderError("header_timestamp", "recorded_at must include a timezone")
    return clean


def _uses_html_comments(suffix: str) -> bool:
    return suffix in {".html", ".md"}


def _prefix_line_count(lines: Sequence[str], suffix: str = "") -> int:
    """Return the line count reserved for file-format declarations."""
    if suffix == ".md" and lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], 1):
            if line.strip() in {"---", "..."}:
                return index + 1
        raise HeaderError("markdown_frontmatter", "unterminated Markdown frontmatter")
    count = 0
    if lines and lines[0].startswith("#!"):
        count = 1
    if len(lines) > count and count < 2 and PY_ENCODING_RE.match(lines[count]):
        count += 1
    return count


def _python_comment_lines(text: str) -> set[int]:
    try:
        return {
            token.start[0]
            for token in tokenize.generate_tokens(StringIO(text).readline)
            if token.type == tokenize.COMMENT
        }
    except (IndentationError, tokenize.TokenError) as exc:
        raise HeaderError("python_tokenize", f"cannot validate Python header: {exc}") from exc


def parse_header(text: str, suffix: str = "") -> Header | None:
    """Parse only a complete, exact, top-level Bufftag block.

    Python headers must consist of real COMMENT tokens, so a decoy embedded in
    a docstring or string cannot impersonate provenance. Markdown and HTML use
    comments so a tag never becomes a visible document heading.
    """
    lines = text.splitlines(keepends=True)
    if not lines:
        return None
    expected_start = _prefix_line_count(lines, suffix)
    normalized = [line.rstrip("\r\n") for line in lines]
    html = _uses_html_comments(suffix)
    start = HTML_HEADER_START if html else HEADER_START
    end_marker = HTML_HEADER_END if html else HEADER_END
    field_re = HTML_FIELD_RE if html else FIELD_RE
    if len(normalized) <= expected_start or normalized[expected_start] != start:
        return None

    try:
        end = normalized.index(end_marker, expected_start + 1)
    except ValueError as exc:
        raise HeaderError("header_unclosed", f"{start} has no exact {end_marker}") from exc

    metadata: dict[str, str] = {}
    for line_number in range(expected_start + 1, end):
        match = field_re.fullmatch(normalized[line_number].rstrip())
        if not match:
            raise HeaderError("header_malformed_line", f"line {line_number + 1} is not a field")
        key, value = match.groups()
        if key in metadata:
            raise HeaderError("header_duplicate_field", f"duplicate field {key}")
        metadata[key] = value

    if suffix == ".py":
        comment_lines = _python_comment_lines(text)
        header_lines = set(range(expected_start + 1, end + 2))
        if not header_lines.issubset(comment_lines):
            raise HeaderError("header_not_comment", "Python header contains non-comment content")

    return Header(_validate_metadata(metadata), expected_start, end)


def render_header(
    metadata: Mapping[str, str], newline: str = "\n", suffix: str = ""
) -> str:
    clean = _validate_metadata(metadata)
    if _uses_html_comments(suffix):
        fields = "".join(
            f"<!-- {key}: {clean[key]} -->{newline}"
            for key in sorted(REQUIRED_METADATA)
        )
        return f"{HTML_HEADER_START}{newline}{fields}{HTML_HEADER_END}{newline}"
    fields = "".join(
        f"# {key}: {clean[key]}{newline}" for key in sorted(REQUIRED_METADATA)
    )
    return f"{HEADER_START}{newline}{fields}{HEADER_END}{newline}"


def _content_without_header(text: str, header: Header | None) -> str:
    if header is None:
        return text
    lines = text.splitlines(keepends=True)
    end = header.end_line + 1
    if end < len(lines) and not lines[end].strip():
        end += 1
    return "".join(lines[:header.start_line] + lines[end:])


def content_sha256(text: str, header: Header | None = None) -> str:
    if header is None:
        header = parse_header(text)
    payload = _content_without_header(text, header).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_target(root: Path, file_path: str | Path) -> Path:
    root = root.resolve()
    requested = Path(file_path)
    absolute = requested if requested.is_absolute() else root / requested
    if not absolute.exists():
        raise BufftagError(f"file does not exist: {absolute}")
    if absolute.is_symlink():
        raise BufftagError(f"refusing symlink target: {absolute}")
    resolved = absolute.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BufftagError(f"target escapes root: {absolute}") from exc

    current = absolute.parent
    while current != root:
        if current.is_symlink():
            raise BufftagError(f"refusing symlink parent: {current}")
        current = current.parent
    return resolved


def _atomic_write(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()


def _record_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"record_id", "signature"}
    }


def _record_id(identity: Mapping[str, Any]) -> str:
    return "bt_" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()[:24]


def _record_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def _make_receipt(
    *,
    path: str,
    digest: str,
    metadata: Mapping[str, str],
    previous: str,
    secret: bytes | None,
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "previous": previous,
        "path": path,
        "sha256": digest,
        "metadata": dict(metadata),
    }
    record: dict[str, Any] = {
        **identity,
        "record_id": _record_id(identity),
        "signature": {"mode": "unsigned"},
    }
    if secret is not None:
        signature = hmac.new(secret, _canonical_bytes(identity), hashlib.sha256).hexdigest()
        record["signature"] = {"mode": "hmac-sha256", "value": signature}
    return record


def _receipt_issues(
    record: Mapping[str, Any], expected_previous: str, secret: bytes | None
) -> list[str]:
    issues: list[str] = []
    if record.get("schema") != RECEIPT_SCHEMA:
        issues.append("wrong schema")
    if record.get("previous") != expected_previous:
        issues.append("broken hash chain")
    receipt_path = record.get("path")
    if not isinstance(receipt_path, str) or Path(receipt_path).is_absolute() or ".." in Path(receipt_path).parts:
        issues.append("unsafe receipt path")
    digest = record.get("sha256")
    if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
        issues.append("invalid content hash")
    metadata = record.get("metadata")
    try:
        _validate_metadata(metadata)
    except HeaderError as exc:
        issues.append(f"invalid metadata: {exc}")

    identity = _record_identity(record)
    if record.get("record_id") != _record_id(identity):
        issues.append("invalid record id")
    signature = record.get("signature")
    if not isinstance(signature, dict):
        issues.append("missing signature mode")
    elif signature.get("mode") == "unsigned":
        if set(signature) != {"mode"}:
            issues.append("malformed unsigned signature")
    elif signature.get("mode") == "hmac-sha256":
        if secret is None:
            issues.append("signature key unavailable")
        else:
            expected = hmac.new(secret, _canonical_bytes(identity), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, str(signature.get("value", ""))):
                issues.append("invalid receipt signature")
    else:
        issues.append("unknown signature mode")
    return issues


def _read_receipts(path: Path, secret: bytes | None) -> tuple[list[dict[str, Any]], list[Finding]]:
    if not path.exists():
        return [], []
    records: list[dict[str, Any]] = []
    findings: list[Finding] = []
    previous = GENESIS_HASH
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [], [Finding("error", "receipts_unreadable", str(path), str(exc))]

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        display = f"{path}:{line_number}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            findings.append(Finding("error", "receipt_json", display, str(exc)))
            continue
        if not isinstance(record, dict):
            findings.append(Finding("error", "receipt_shape", display, "record is not an object"))
            continue
        for issue in _receipt_issues(record, previous, secret):
            findings.append(Finding("error", "receipt_invalid", display, issue))
        records.append(record)
        previous = _record_hash(record)
    return records, findings


@contextlib.contextmanager
def _receipt_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def append_receipt(path: Path, record: Mapping[str, Any], secret: bytes | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _receipt_lock(path):
        records, findings = _read_receipts(path, secret)
        if findings:
            raise BufftagError("refusing to append to an invalid receipt log")
        previous = _record_hash(records[-1]) if records else GENESIS_HASH
        if record.get("previous") != previous:
            raise BufftagError("receipt chain changed while appending")
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _secret_from_env(name: str | None) -> bytes | None:
    if not name:
        return None
    value = os.environ.get(name)
    if not value:
        raise BufftagError(f"signing key environment variable is empty: {name}")
    return value.encode("utf-8")


def _legacy_marker(text: str) -> bool:
    return "[DNA_TAG]" in text[:4096] or "[/DNA_TAG]" in text[:4096]


def _python_proposal(path: Path, text: str) -> tuple[str, list[str]]:
    role = "unclassified"
    deps: set[str] = set()
    try:
        tree = ast.parse(text)
        docstring = ast.get_docstring(tree)
        if docstring:
            role = docstring.strip().splitlines()[0][:200]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                deps.add(node.module.split(".")[0])
    except (SyntaxError, ValueError):
        role = "unclassified:python-parse-failed"
    return role, sorted(deps)


def propose(root: Path, file_path: str | Path) -> dict[str, Any]:
    root = root.resolve()
    target = _safe_target(root, file_path)
    text = target.read_text(encoding="utf-8", errors="strict")
    relative = target.relative_to(root)
    pillar = relative.parts[0] if len(relative.parts) > 1 else "root"
    role = "unclassified"
    deps: list[str] = []
    if target.suffix == ".py":
        role, deps = _python_proposal(target, text)
    warnings = [
        "origin is not inferred",
        "author is not inferred",
        "role and dependencies are proposals, not verified facts",
    ]
    if _legacy_marker(text):
        warnings.append("legacy DNA_TAG found; its claims were not imported")
    return {
        "schema": "bufftag/proposal/v1",
        "path": relative.as_posix(),
        "metadata": {
            "origin": "unverified",
            "pillar": pillar,
            "deps": ",".join(deps) if deps else "none",
            "role": role,
            "author": "unverified",
            "recorded_at": _now(),
        },
        "warnings": warnings,
    }


def stamp(
    *,
    root: Path,
    file_path: str | Path,
    metadata: Mapping[str, str],
    receipts_path: Path,
    secret: bytes | None,
) -> dict[str, Any]:
    root = root.resolve()
    target = _safe_target(root, file_path)
    if target.suffix not in SUPPORTED_SUFFIXES:
        raise BufftagError(f"unsupported file type: {target.suffix}")
    if target.stat().st_size > DEFAULT_MAX_BYTES:
        raise BufftagError(f"file exceeds {DEFAULT_MAX_BYTES} bytes")

    before = target.stat()
    original = target.read_text(encoding="utf-8", errors="strict")
    if parse_header(original, target.suffix) is not None:
        raise BufftagError("file already has a Bufftag header")
    newline = "\r\n" if "\r\n" in original else "\n"
    prefix_count = _prefix_line_count(original.splitlines(keepends=True), target.suffix)
    lines = original.splitlines(keepends=True)
    header = render_header(metadata, newline, target.suffix)
    stamped = "".join(lines[:prefix_count]) + header + newline + "".join(lines[prefix_count:])
    parsed = parse_header(stamped, target.suffix)
    if parsed is None:
        raise BufftagError("internal error: generated header did not parse")
    digest = content_sha256(stamped, parsed)

    records, findings = _read_receipts(receipts_path, secret)
    if findings:
        raise BufftagError("refusing to stamp while the receipt log is invalid")
    previous = _record_hash(records[-1]) if records else GENESIS_HASH
    relative = target.relative_to(root).as_posix()
    receipt = _make_receipt(
        path=relative,
        digest=digest,
        metadata=parsed.metadata,
        previous=previous,
        secret=secret,
    )
    after = target.stat()
    unchanged = (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        and target.read_text(encoding="utf-8", errors="strict") == original
    )
    if not unchanged:
        raise BufftagError("file changed while it was being stamped; refusing to overwrite")
    _atomic_write(target, stamped.encode("utf-8"))
    try:
        append_receipt(receipts_path, receipt, secret)
    except Exception:
        # The header remains parseable; the missing receipt is deliberately loud
        # during verification and can be retried after the log is repaired.
        raise
    return {"path": relative, "sha256": digest, "receipt": receipt}


def _iter_files(root: Path, excluded: set[str]) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in excluded and not (current / name).is_symlink()
        )
        for name in sorted(filenames):
            path = current / name
            if path.suffix in SUPPORTED_SUFFIXES:
                yield path


def verify(
    *,
    root: Path,
    receipts_path: Path,
    secret: bytes | None,
    require_complete: bool = False,
    excluded: set[str] | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Report:
    root = root.resolve()
    excluded = DEFAULT_EXCLUDED_DIRS if excluded is None else set(excluded)
    records, findings = _read_receipts(receipts_path, secret)
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        receipt_path = record.get("path")
        if isinstance(receipt_path, str):
            latest[receipt_path] = record

    seen: set[str] = set()
    scanned = 0
    for path in _iter_files(root, excluded):
        scanned += 1
        relative = path.relative_to(root).as_posix()
        seen.add(relative)
        if path.is_symlink():
            findings.append(Finding("warn", "symlink_skipped", relative, "symlinks are never followed"))
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            findings.append(Finding("error", "file_stat_failed", relative, str(exc)))
            continue
        if size > max_bytes:
            findings.append(Finding("error", "file_too_large", relative, f"{size} > {max_bytes} bytes"))
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            findings.append(Finding("error", "file_unreadable", relative, str(exc)))
            continue

        record = latest.get(relative)
        try:
            header = parse_header(text, path.suffix)
        except HeaderError as exc:
            findings.append(Finding("error", exc.code, relative, str(exc)))
            continue
        if header is None:
            if record is not None:
                findings.append(
                    Finding("error", "header_removed", relative, "receipt exists but strict header is missing")
                )
            if _legacy_marker(text):
                findings.append(
                    Finding(
                        "warn" if not require_complete else "error",
                        "legacy_dna_tag",
                        relative,
                        "legacy metadata is untrusted and was not migrated",
                    )
                )
            else:
                findings.append(
                    Finding(
                        "warn" if not require_complete else "error",
                        "untagged",
                        relative,
                        "no strict Bufftag header",
                    )
                )
            continue
        if _legacy_marker(text):
            findings.append(
                Finding("warn", "legacy_dna_tag", relative, "legacy metadata remains beside Bufftag")
            )

        if record is None:
            findings.append(Finding("error", "receipt_missing", relative, "header has no receipt"))
            continue
        digest = content_sha256(text, header)
        if digest != record.get("sha256"):
            findings.append(Finding("error", "content_drift", relative, "content hash differs from receipt"))
        if header.metadata != record.get("metadata"):
            findings.append(Finding("error", "metadata_drift", relative, "header metadata differs from receipt"))

    for receipt_path in sorted(set(latest) - seen):
        findings.append(Finding("error", "file_missing", receipt_path, "receipt points to a missing file"))
    return Report(str(root), scanned, len(records), findings)


def _print_report(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return
    for finding in report.findings:
        print(f"{finding.severity.upper()} {finding.code} {finding.path}: {finding.message}")
    status = "OK" if report.ok else "FAILED"
    print(
        f"{status}: scanned={report.files_scanned} receipts={report.receipt_count} "
        f"errors={sum(f.severity == 'error' for f in report.findings)} "
        f"warnings={sum(f.severity == 'warn' for f in report.findings)}"
    )


def _receipts_for(root: Path, value: str | None) -> Path:
    return (root / value).resolve() if value else root / ".bufftag" / "receipts.jsonl"


def _watch(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    secret = _secret_from_env(args.signing_key_env)
    previous: str | None = None
    while True:
        report = verify(
            root=root,
            receipts_path=_receipts_for(root, args.receipts),
            secret=secret,
            require_complete=args.require_complete,
        )
        fingerprint = hashlib.sha256(
            _canonical_bytes(report.as_dict())
        ).hexdigest()
        if not args.quiet or fingerprint != previous:
            _print_report(report, args.json)
        previous = fingerprint
        if args.once:
            return 0 if report.ok else 1
        time.sleep(args.interval)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bufftag", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    propose_parser = sub.add_parser("propose", help="print untrusted metadata proposals; writes nothing")
    propose_parser.add_argument("root")
    propose_parser.add_argument("file")

    stamp_parser = sub.add_parser("stamp", help="atomically add a strict header and content receipt")
    stamp_parser.add_argument("root")
    stamp_parser.add_argument("file")
    stamp_parser.add_argument("--origin", required=True)
    stamp_parser.add_argument("--pillar", required=True)
    stamp_parser.add_argument("--role", required=True)
    stamp_parser.add_argument("--author", required=True)
    stamp_parser.add_argument("--deps", default="none")
    stamp_parser.add_argument("--recorded-at")
    stamp_parser.add_argument("--receipts")
    stamp_parser.add_argument(
        "--signing-key-env",
        help="environment variable containing an HMAC key; the key value is never accepted on the command line",
    )

    verify_parser = sub.add_parser("verify", help="verify headers, content drift, receipt chain, and optional signatures")
    verify_parser.add_argument("root")
    verify_parser.add_argument("--receipts")
    verify_parser.add_argument("--signing-key-env")
    verify_parser.add_argument("--require-complete", action="store_true")
    verify_parser.add_argument("--json", action="store_true")

    watch_parser = sub.add_parser("watch", help="opt-in polling monitor; use --once for a single pass")
    watch_parser.add_argument("root")
    watch_parser.add_argument("--receipts")
    watch_parser.add_argument("--signing-key-env")
    watch_parser.add_argument("--require-complete", action="store_true")
    watch_parser.add_argument("--interval", type=float, default=30.0)
    watch_parser.add_argument("--once", action="store_true")
    watch_parser.add_argument("--quiet", action="store_true")
    watch_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "propose":
            print(json.dumps(propose(Path(args.root), args.file), indent=2, sort_keys=True))
            return 0
        if args.command == "stamp":
            root = Path(args.root).resolve()
            metadata = {
                "origin": args.origin,
                "pillar": args.pillar,
                "deps": args.deps,
                "role": args.role,
                "author": args.author,
                "recorded_at": args.recorded_at or _now(),
            }
            result = stamp(
                root=root,
                file_path=args.file,
                metadata=metadata,
                receipts_path=_receipts_for(root, args.receipts),
                secret=_secret_from_env(args.signing_key_env),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "verify":
            root = Path(args.root).resolve()
            report = verify(
                root=root,
                receipts_path=_receipts_for(root, args.receipts),
                secret=_secret_from_env(args.signing_key_env),
                require_complete=args.require_complete,
            )
            _print_report(report, args.json)
            return 0 if report.ok else 1
        if args.command == "watch":
            return _watch(args)
    except BufftagError as exc:
        print(f"bufftag: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
