"""Bounded BI scout coordination for Tideglass.

This is an adapter boundary, not an LLM runtime: callers inject one runner per
specialist. Findings remain unverified evidence and never become probabilities.
"""
from __future__ import annotations

import hashlib
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable


MAX_SCOUTS = 12
MAX_PARALLEL_SCOUTS = 4
MAX_FINDINGS_PER_SCOUT = 20
MAX_FINDING_CHARS = 4_000
MAX_SOURCE_CHARS = 2_000


@dataclass(frozen=True)
class ScoutTask:
    market_id: str
    question: str
    as_of: str
    action: str = ""

    def __post_init__(self) -> None:
        for name, value, limit in (
            ("market_id", self.market_id, 256),
            ("question", self.question, 4_000),
            ("as_of", self.as_of, 64),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")
            if len(value) > limit:
                raise ValueError(f"{name} exceeds {limit} characters")
        if not isinstance(self.action, str) or len(self.action) > 4_000:
            raise ValueError("action must be a string of at most 4000 characters")
        _parse_time(self.as_of, "as_of")


@dataclass(frozen=True)
class ScoutFinding:
    scout_name: str
    claim: str
    source: str
    observed_at: str
    confidence: float | None = None
    content_sha256: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.scout_name, str) or not self.scout_name.strip():
            raise ValueError("scout_name must not be blank")
        if not isinstance(self.claim, str) or not self.claim.strip():
            raise ValueError("claim must not be blank")
        if len(self.claim) > MAX_FINDING_CHARS:
            raise ValueError(f"claim exceeds {MAX_FINDING_CHARS} characters")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must not be blank")
        if len(self.source) > MAX_SOURCE_CHARS:
            raise ValueError(f"source exceeds {MAX_SOURCE_CHARS} characters")
        _parse_time(self.observed_at, "observed_at")
        if self.confidence is not None:
            try:
                valid = (
                    not isinstance(self.confidence, bool)
                    and isinstance(self.confidence, (int, float))
                    and math.isfinite(self.confidence)
                    and 0 <= self.confidence <= 1
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("confidence must be a finite number between 0 and 1")
        if not isinstance(self.content_sha256, str) or (
            self.content_sha256
            and (len(self.content_sha256) != 64 or any(
                char not in "0123456789abcdef" for char in self.content_sha256
            ))
        ):
            raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")

    @property
    def digest(self) -> str:
        """Hash the claim locally when no content digest was supplied.

        The digest records content identity; it does not verify the source or
        prove when, where, or by whom the claim was published.
        """
        if self.content_sha256:
            return self.content_sha256
        return hashlib.sha256(self.claim.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "scout_name": self.scout_name,
            "claim": self.claim,
            "source": self.source,
            "observed_at": self.observed_at,
            "confidence": self.confidence,
            "content_sha256": self.digest,
            "verified": False,
        }


@dataclass(frozen=True)
class ScoutFailure:
    scout_name: str
    error_type: str

    def to_dict(self) -> dict[str, str]:
        return {"scout_name": self.scout_name, "error_type": self.error_type}


@dataclass(frozen=True)
class ScoutRunReport:
    task: ScoutTask
    findings: tuple[ScoutFinding, ...]
    failures: tuple[ScoutFailure, ...]
    completed_scouts: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "market_id": self.task.market_id,
            "question": self.task.question,
            "as_of": self.task.as_of,
            "action": self.task.action,
            "completed_scouts": list(self.completed_scouts),
            "findings": [finding.to_dict() for finding in self.findings],
            "failures": [failure.to_dict() for failure in self.failures],
            "trust": "unverified_evidence_only",
            "forecast_generated": False,
        }


ScoutRunner = Callable[[ScoutTask], Iterable[ScoutFinding]]


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _collect_one(
    task: ScoutTask, name: str, runner: ScoutRunner, as_of: datetime
) -> tuple[str, list[ScoutFinding], ScoutFailure | None]:
    scout_findings: list[ScoutFinding] = []
    try:
        result = runner(task)
        iterator = iter(result)
        for index in range(MAX_FINDINGS_PER_SCOUT + 1):
            try:
                finding = next(iterator)
            except StopIteration:
                break
            if index == MAX_FINDINGS_PER_SCOUT:
                raise ValueError("finding_limit_exceeded")
            if not isinstance(finding, ScoutFinding):
                raise TypeError("invalid_finding_type")
            if finding.scout_name != name:
                raise ValueError("scout_identity_mismatch")
            if _parse_time(finding.observed_at, "observed_at") > as_of:
                raise ValueError("future_dated_finding")
            scout_findings.append(finding)
    except Exception as exc:
        return name, [], ScoutFailure(name, type(exc).__name__)
    return name, scout_findings, None


def run_scouts(
    task: ScoutTask,
    scouts: dict[str, ScoutRunner],
    *,
    max_workers: int | None = None,
) -> ScoutRunReport:
    """Run injected specialist scouts concurrently and collect unverified findings.

    Runner code is supplied by the caller and may itself have side effects; use
    only trusted adapters with their own explicit network/model permissions.
    This coordinator makes no external calls. Exceptions are isolated per scout,
    and exception text is omitted to avoid leaking credentials or prompt data.
    Findings are returned in declared scout order, regardless of completion order.
    A scout cannot claim another scout's identity.
    """
    if not isinstance(task, ScoutTask):
        raise ValueError("task must be a ScoutTask")
    if not isinstance(scouts, dict):
        raise ValueError("scouts must be a mapping of names to runner callables")
    if not scouts:
        raise ValueError("at least one scout runner is required")
    if len(scouts) > MAX_SCOUTS:
        raise ValueError(f"at most {MAX_SCOUTS} scouts are supported")
    if any(not isinstance(name, str) or not name.strip() for name in scouts):
        raise ValueError("scout names must be non-blank strings")
    if any(not callable(runner) for runner in scouts.values()):
        raise ValueError("every scout runner must be callable")
    if max_workers is None:
        max_workers = min(MAX_PARALLEL_SCOUTS, len(scouts))
    elif (
        isinstance(max_workers, bool)
        or not isinstance(max_workers, int)
        or not 1 <= max_workers <= min(MAX_PARALLEL_SCOUTS, len(scouts))
    ):
        raise ValueError(
            f"max_workers must be between 1 and min({MAX_PARALLEL_SCOUTS}, scout count)"
        )

    as_of = _parse_time(task.as_of, "as_of")
    names = list(scouts)
    results: dict[str, tuple[list[ScoutFinding], ScoutFailure | None]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            name: pool.submit(_collect_one, task, name, runner, as_of)
            for name, runner in scouts.items()
        }
        for name in names:
            _, items, failure = futures[name].result()
            results[name] = (items, failure)

    findings = [finding for name in names for finding in results[name][0]]
    failures = [results[name][1] for name in names if results[name][1] is not None]
    completed = [name for name in names if results[name][1] is None]
    return ScoutRunReport(
        task=task,
        findings=tuple(findings),
        failures=tuple(failures),
        completed_scouts=tuple(completed),
    )
