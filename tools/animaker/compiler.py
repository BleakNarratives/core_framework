"""Pure Diff Theater animation proposal compiler.

Diff text and event metadata are untrusted data. This module normalizes bounded
inputs into a declarative ``diff-theater.animation/v1`` proposal. It performs no
I/O, subprocess calls, network access, or model execution.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

SCHEMA = "diff-theater.animation/v1"
COMPILER_VERSION = "diff-theater.compiler/1.0.0"
# This identity is part of the output contract. Change it whenever the schema or
# timeline semantics change; clients can then reject stale proposals explicitly.
SCHEMA_HASH = hashlib.sha256(b"diff-theater.animation/v1|source_diff+timeline+reduced_motion").hexdigest()
MAX_DIFF_BYTES = 1_048_576
MAX_FILES = 100
MAX_TIMELINE = 64
MAX_LABEL = 500
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_PROMPT_WRAPPER = re.compile(r"(?i)(?:<\|[^|]{0,80}\|>|\[\/?INST\]|###\s*(?:system|assistant|user)\s*:|(?:^|\n)\s*(?:system|assistant|user)\s*:|(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+instructions)")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")

_RISK_NAMES = {"low", "medium", "high", "critical"}
_EASINGS = {"linear", "ease-in-out", "ease-out", "ease-in", "spring"}
_KINDS = {"ribbon-rise", "ribbon-fall", "nexus-pulse", "dependency-pulse", "risk-shift"}


class ProposalError(ValueError):
    """The input cannot produce a bounded animation proposal."""


def _sanitize_untrusted_text(value: str, limit: int) -> str:
    """Remove executable/control framing before a value reaches the compiler.

    This is deliberately a character boundary, not an instruction parser. ANSI
    escapes, terminal controls, bidi/zero-width tricks, and common chat-template
    wrappers are removed. Remaining prose and code are still data, never policy.
    """
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _ANSI_ESCAPE.sub("", value)
    value = _ZERO_WIDTH.sub("", value)
    value = _PROMPT_WRAPPER.sub("[redacted-untrusted-wrapper]", value)
    value = "".join(
        char for char in value
        if char in "\\n\\t" or unicodedata.category(char) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )
    encoded = value.encode("utf-8")
    if len(encoded) > limit:
        encoded = encoded[:limit]
        value = encoded.decode("utf-8", errors="ignore")
    return value


def _bounded_text(value: Any, name: str, limit: int = MAX_LABEL) -> str:
    if not isinstance(value, str):
        raise ProposalError(f"{name} must be text")
    if len(value.encode("utf-8")) > limit * 2 + 128:
        raise ProposalError(f"{name} is too large before sanitization")
    value = _sanitize_untrusted_text(value, limit)
    if not value:
        raise ProposalError(f"{name} is empty after sanitization")
    return value


def _number(value: Any, name: str, low: float = 0.0, high: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProposalError(f"{name} must be numeric")
    number = float(value)
    if not low <= number <= high:
        raise ProposalError(f"{name} must be between {low} and {high}")
    return round(number, 4)


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise ProposalError(f"{name} must be a bounded non-negative integer")
    return value


def _safe_path(value: Any) -> str:
    path = _bounded_text(value, "affected file path", 500).strip()
    candidate = PurePosixPath(path)
    if not path or candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
        raise ProposalError("affected file paths must be relative and non-escaping")
    return path


def normalize_event(event: Mapping[str, Any], diff_text: str) -> dict[str, Any]:
    """Return bounded event metadata; text is hashed and never interpreted."""
    if not isinstance(event, Mapping):
        raise ProposalError("event must be an object")
    if len(diff_text.encode("utf-8")) > MAX_DIFF_BYTES:
        raise ProposalError("diff text exceeds the 1 MiB source limit")
    diff = _sanitize_untrusted_text(_bounded_text(diff_text, "diff text", MAX_DIFF_BYTES), MAX_DIFF_BYTES)
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else event
    line_changes = payload.get("line_changes", {}) if isinstance(payload, Mapping) else {}
    if not isinstance(line_changes, Mapping):
        raise ProposalError("line_changes must be an object")
    narration = payload.get("agent_narration", {}) if isinstance(payload, Mapping) else {}
    if not isinstance(narration, Mapping):
        narration = {}
    risk = payload.get("risk_level", "low") if isinstance(payload, Mapping) else "low"
    if risk not in _RISK_NAMES:
        raise ProposalError("unsupported risk_level")
    files = payload.get("affected_files", []) if isinstance(payload, Mapping) else []
    if not isinstance(files, Sequence) or isinstance(files, (str, bytes)) or len(files) > MAX_FILES:
        raise ProposalError("affected_files must be a bounded list")
    normalized_files = []
    for item in files:
        if not isinstance(item, Mapping):
            raise ProposalError("each affected file must be an object")
        normalized_files.append({
            "path": _safe_path(item.get("file_path", item.get("path"))),
            "importance": _number(item.get("importance", 0.5), "file importance"),
        })
    dependencies = payload.get("dependency_order", []) if isinstance(payload, Mapping) else []
    if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)) or len(dependencies) > MAX_FILES:
        raise ProposalError("dependency_order must be a bounded list")
    normalized_dependencies = [_bounded_text(item, "dependency", 200) for item in dependencies]
    return {
        "event_id": _bounded_text(event.get("task_id", event.get("event_id", "diff-event")), "event_id", 200),
        "agent_id": _bounded_text(event.get("agent_id", "unknown-agent"), "agent_id", 200),
        "risk_level": risk,
        "confidence": _number(narration.get("confidence", payload.get("confidence", 0.6)), "confidence"),
        "line_changes": {
            "added": _count(line_changes.get("added", line_changes.get("added_lines", 0)), "added"),
            "deleted": _count(line_changes.get("deleted", line_changes.get("deleted_lines", 0)), "deleted"),
            "modified": _count(line_changes.get("modified", 0), "modified"),
        },
        "affected_files": normalized_files,
        "dependency_order": normalized_dependencies,
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "diff_bytes": len(diff.encode("utf-8")),
    }


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _timeline(event: Mapping[str, Any]) -> list[dict[str, Any]]:
    additions = event["line_changes"]["added"]
    deletions = event["line_changes"]["deleted"]
    total = max(1, additions + deletions + event["line_changes"]["modified"])
    confidence = event["confidence"]
    intensity = round(_clip(0.25 + total / 400 + (1 - confidence) * 0.2, 0, 1), 4)
    entries: list[dict[str, Any]] = []
    if additions:
        entries.append({"id": "additions", "at_ms": 0, "duration_ms": 800, "kind": "ribbon-rise", "lane": "additions", "intensity": intensity, "easing": "ease-out", "source_label": f"{additions} added lines"})
    if deletions:
        entries.append({"id": "deletions", "at_ms": 120, "duration_ms": 800, "kind": "ribbon-fall", "lane": "deletions", "intensity": intensity, "easing": "ease-in-out", "source_label": f"{deletions} deleted lines"})
    for index, dependency in enumerate(event["dependency_order"][:12]):
        entries.append({"id": f"dependency-{index + 1}", "at_ms": min(30000, 400 + index * 180), "duration_ms": 600, "kind": "dependency-pulse", "lane": dependency, "intensity": round(_clip(0.35 + confidence * 0.4, 0, 1), 4), "easing": "spring", "source_label": dependency})
    if event["risk_level"] in {"high", "critical"}:
        entries.append({"id": "risk-shift", "at_ms": 200, "duration_ms": 900, "kind": "risk-shift", "lane": "risk", "intensity": 0.8 if event["risk_level"] == "critical" else 0.6, "easing": "ease-out", "source_label": event["risk_level"]})
    if not entries:
        entries.append({"id": "quiet-settle", "at_ms": 0, "duration_ms": 500, "kind": "nexus-pulse", "lane": "quiet", "intensity": 0.2, "easing": "ease-in-out", "source_label": "no line changes"})
    return entries[:MAX_TIMELINE]


def compile_animation(event: Mapping[str, Any], diff_text: str, render_targets: Sequence[str] = ("native",)) -> dict[str, Any]:
    """Compile one event into a schema-compatible, proposal-only animation."""
    targets = tuple(render_targets)
    if not targets or len(targets) > 3 or len(set(targets)) != len(targets) or any(t not in {"native", "css", "tailwind"} for t in targets):
        raise ProposalError("render_targets must contain unique native/css/tailwind values")
    normalized = normalize_event(event, diff_text)
    timeline = _timeline(normalized)
    risk = normalized["risk_level"]
    if risk == "critical":
        intent_name = "risk-weather"
    elif normalized["dependency_order"]:
        intent_name = "dependency-pulse"
    elif normalized["line_changes"]["deleted"]:
        intent_name = "calm-ribbon"
    else:
        intent_name = "quiet-settle"
    timeline_json = json.dumps(timeline, sort_keys=True, separators=(",", ":"))
    return {
        "schema": SCHEMA,
        "schema_hash": SCHEMA_HASH,
        "compiler_version": COMPILER_VERSION,
        "source_diff": {"sha256": normalized["diff_sha256"], "bytes": normalized["diff_bytes"], "text_storage": "proposal_payload_only"},
        "source_event": {key: normalized[key] for key in ("event_id", "agent_id", "risk_level", "confidence", "line_changes", "affected_files", "dependency_order")},
        "intent": {"name": intent_name, "summary": f"Visualize {normalized['line_changes']['added']} additions and {normalized['line_changes']['deleted']} deletions as bounded proposal data.", "trust": "derived_from_untrusted_diff"},
        "timeline": timeline,
        "timeline_sha256": hashlib.sha256(timeline_json.encode("utf-8")).hexdigest(),
        "reduced_motion": {"mode": "static", "animation": "none", "show_static_state": True, "description": "Render a static summary of additions, deletions, dependencies, and risk."},
        "render_targets": list(targets),
        "proposal_only": True,
    }


def render_css(proposal: Mapping[str, Any]) -> str:
    """Render a safe, declarative CSS proposal; it is not applied to disk."""
    if proposal.get("schema") != SCHEMA or proposal.get("proposal_only") is not True:
        raise ProposalError("not a diff-theater.animation/v1 proposal")
    lines = [".diff-theater-stage {", "  --dt-duration: 1200ms;", "  --dt-easing: cubic-bezier(.2,.8,.2,1);", "}"]
    for entry in proposal["timeline"]:
        if not _IDENTIFIER.fullmatch(entry["id"]):
            raise ProposalError("timeline id is invalid")
        kind = entry["kind"]
        transform = {"ribbon-rise": "translateY(12px)", "ribbon-fall": "translateY(-12px)", "nexus-pulse": "scale(.98)", "dependency-pulse": "scale(1.02)", "risk-shift": "translateX(6px)"}[kind]
        lines.extend([f"@keyframes dt-{entry['id']} {{", "  from { opacity: 0; transform: " + transform + "; }", "  to { opacity: 1; transform: none; }", "}"])
        lines.append(f".dt-lane-{entry['id']} {{ animation: dt-{entry['id']} {entry['duration_ms']}ms {entry['easing']} both; }}")
    lines.extend(["@media (prefers-reduced-motion: reduce) {", "  .diff-theater-stage *, .diff-theater-stage *::before, .diff-theater-stage *::after { animation: none !important; }", "}"])
    return "\n".join(lines) + "\n"


def render_tailwind(proposal: Mapping[str, Any]) -> str:
    """Render Tailwind class suggestions; no framework or CDN is required."""
    classes = ["motion-safe:transition-all", "motion-reduce:transition-none", "motion-reduce:transform-none"]
    for entry in proposal["timeline"]:
        if entry["kind"] in {"ribbon-rise", "dependency-pulse", "nexus-pulse"}:
            classes.append("motion-safe:animate-pulse")
        if entry["kind"] == "risk-shift":
            classes.append("motion-safe:animate-pulse")
    return " ".join(dict.fromkeys(classes))


def to_json(proposal: Mapping[str, Any]) -> str:
    return json.dumps(proposal, indent=2, sort_keys=True, ensure_ascii=False)


__all__ = ["COMPILER_VERSION", "ProposalError", "SCHEMA", "SCHEMA_HASH", "compile_animation", "normalize_event", "render_css", "render_tailwind", "to_json"]
