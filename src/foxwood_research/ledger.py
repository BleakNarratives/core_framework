"""Foxwood Research Ledger.

This module is intentionally a ledger, not an idea generator. It preserves a
citation spine from source acquisition through exported claims, so an LLM can
be placed after the ledger without allowing uncited prose into the record.

The implementation is clean-room and uses only the Python standard library.
Fetched pages are untrusted evidence: they are stored as text, never executed,
and never treated as instructions.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

MAX_SOURCE_BYTES = 500_000
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_FOREIGN_ROOTS = ("ScholarScout", "ScholarScoutSwarm")
DEFAULT_FOREIGN_URL_MARKERS = (
    "github.com/neej4/scholarscout",
    "scholarscout.pages.dev",
)
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "::1"}

# ── the one decision log ─────────────────────────────────────────────────────
#
# A ledger root keeps every decision recorded against its evidence in a single
# append-only file. The name is kept from the first thing that wrote here -- pipe
# verdicts -- rather than changed to something honest like `decisions.jsonl`,
# because renaming a log is a way to lose the log. What it holds now is every
# decision anybody wrote down: pipe verdicts, and any other writer that agrees to
# the same two rules.
#
# THE TWO RULES, because a shared file only works if both ends agree:
#   1. One JSON object per line, self-describing, appended and never rewritten. A
#      reader that cannot parse a line skips it and carries on: a decision log is
#      a record of work already done, and failing to read one must not stop the
#      next person from working.
#   2. `kind` names the writer. It is for a human reading the file. Every reader
#      decides what it owns *structurally* -- by the fields it actually needs --
#      because a filter keyed on `kind` would ignore every entry written before
#      that field existed, which is the same class of mistake as a lock nobody
#      turned.
DECISION_LOG_FILENAME = "verdicts.jsonl"
KIND_VERDICT = "verdict"
KIND_DECISION = "decision"


class ForeignContentError(ValueError):
    """Raised when a known foreign workspace is presented as source material."""


class MissingCitationError(ValueError):
    """Raised when a claim cannot be tied to a registered source."""


@dataclass(frozen=True)
class SourceRecord:
    """A bounded, content-addressed source in the Foxwood ledger."""

    source_id: str
    title: str
    url: str
    publisher: str
    retrieved_at: str
    content_hash: str
    excerpt: str
    license_note: str = "unknown"
    origin: str = "network"


@dataclass(frozen=True)
class Claim:
    """A statement whose evidence is explicit and auditable."""

    claim_id: str
    text: str
    source_ids: tuple[str, ...]
    confidence: str = "unassessed"
    note: str = ""


@dataclass
class ResearchPacket:
    """An exportable research result with no uncited claim channel."""

    query: str
    created_at: str
    source_ids: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_markdown(self, ledger: "ResearchLedger") -> str:
        """Render a citation-preserving report from ledger records."""
        lines = [f"# Foxwood Research Packet: {self.query}", "", f"Created: {self.created_at}", ""]
        lines.append("## Claims")
        if not self.claims:
            lines.append("_No claims recorded._")
        for claim in self.claims:
            citations = ", ".join(f"[{source_id}]" for source_id in claim.source_ids)
            suffix = f" ({claim.confidence})" if claim.confidence else ""
            lines.append(f"- {claim.text}{suffix} {citations}".rstrip())
            if claim.note:
                lines.append(f"  - Note: {claim.note}")

        lines.extend(["", "## Open questions"])
        lines.extend(f"- {question}" for question in self.open_questions)
        if not self.open_questions:
            lines.append("_None recorded._")

        lines.extend(["", "## Sources"])
        for source_id in self.source_ids:
            source = ledger.get_source(source_id)
            lines.append(
                f"- [{source.source_id}] [{source.title}]({source.url}) — "
                f"{source.publisher}; retrieved {source.retrieved_at}; "
                f"SHA-256 `{source.content_hash}`; license: {source.license_note}."
            )
        return "\n".join(lines) + "\n"


class ResearchLedger:
    """Store source evidence and claims with a hard provenance boundary."""

    def __init__(
        self,
        root: str | Path,
        foreign_roots: Sequence[str] = DEFAULT_FOREIGN_ROOTS,
        fetcher: Optional[Callable[[str], bytes]] = None,
        admit: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.sources_path = self.root / "sources.jsonl"
        self.claims_path = self.root / "claims.jsonl"
        self.foreign_roots = tuple(foreign_roots)
        self._fetcher = fetcher or self._fetch_url
        # Optional external admission gate, called as admit(origin, url). The pipe
        # installs a PROVENANCE.md-backed gate here so a ledger's own writes are
        # checked against the repository registry and not only this module's list.
        self._admit = admit
        self._sources: dict[str, SourceRecord] = {}
        self._claims: dict[str, Claim] = {}
        self._load()

    def _load(self) -> None:
        for path, target, factory in (
            (self.sources_path, self._sources, SourceRecord),
            (self.claims_path, self._claims, Claim),
        ):
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = factory(**json.loads(line))
                target[record.source_id if isinstance(record, SourceRecord) else record.claim_id] = record

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _assert_not_foreign(self, origin: str, url: str = "") -> None:
        """Reject known foreign paths and URLs before any content is recorded.

        Two locks, and the split is deliberate. The configured gate (`admit`) is
        *data*: it reads PROVENANCE.md, so a newly classified project is blocked by
        editing a registry rather than a Python file. The list below is *code*, so
        an edited or truncated registry cannot switch the floor off. A stale
        registry is still caught here, and a segment this module never heard of is
        still caught by the registry.
        """
        if self._admit is not None:
            self._admit(origin, url)
        normalized = origin.replace("\\", "/").strip("/")
        parts = set(normalized.split("/"))
        blocked = parts.intersection(self.foreign_roots)
        normalized_url = url.lower().rstrip("/")
        blocked_url = next(
            (marker for marker in DEFAULT_FOREIGN_URL_MARKERS if marker in normalized_url),
            None,
        )
        if blocked or blocked_url:
            reason = ", ".join(sorted(blocked)) if blocked else blocked_url
            raise ForeignContentError(f"foreign source rejected: {reason}")

    def assert_not_foreign(self, origin: str, url: str = "") -> None:
        """Apply this ledger's hold to an origin, without adding anything.

        Public so a reader that re-checks stored evidence can apply the same two
        locks the writer did. Until this existed, the pipe's re-admission consulted
        only the registry, which meant that a registry edited to call ScholarScout
        OWNED was enough to get it framed into a prompt -- the code floor was never
        asked. A lock the reader forgets to turn is not a lock.
        """
        self._assert_not_foreign(origin, url)

    def add_source(
        self,
        *,
        title: str,
        url: str,
        publisher: str,
        excerpt: str,
        license_note: str = "unknown",
        origin: str = "network",
        source_id: Optional[str] = None,
    ) -> SourceRecord:
        """Register original evidence without permitting foreign workspace input."""
        self._assert_not_foreign(origin, url)
        if not title.strip() or not url.strip() or not excerpt.strip():
            raise ValueError("title, url, and excerpt are required")
        digest = self._digest(excerpt)
        identity_digest = self._digest(url.strip() + "|" + excerpt)
        record = SourceRecord(
            source_id=source_id or f"src-{identity_digest[:12]}",
            title=title.strip(),
            url=url.strip(),
            publisher=publisher.strip() or "unknown",
            retrieved_at=self._now(),
            content_hash=digest,
            excerpt=excerpt[:MAX_SOURCE_BYTES],
            license_note=license_note.strip() or "unknown",
            origin=origin,
        )
        existing = self._sources.get(record.source_id)
        if existing and existing.content_hash != record.content_hash:
            raise ValueError(f"source ID collision: {record.source_id}")
        if not existing:
            self._sources[record.source_id] = record
            self._append(self.sources_path, asdict(record))
        return self._sources[record.source_id]

    def fetch_source(
        self,
        *,
        title: str,
        url: str,
        publisher: str,
        license_note: str = "unknown",
    ) -> SourceRecord:
        """Fetch one public URL under strict size and private-network limits."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http and https sources are allowed")
        host = (parsed.hostname or "").lower()
        if host in _BLOCKED_HOSTS or host.startswith(("10.", "192.168.", "172.16.")):
            raise ValueError("private or local network sources are not allowed")
        raw = self._fetcher(url)
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("source exceeds the bounded payload limit")
        text = self._html_to_text(raw.decode("utf-8", errors="replace"))
        return self.add_source(
            title=title,
            url=url,
            publisher=publisher,
            excerpt=text,
            license_note=license_note,
            origin="network",
        )

    def add_claim(
        self,
        *,
        text: str,
        source_ids: Iterable[str],
        confidence: str = "unassessed",
        note: str = "",
        claim_id: Optional[str] = None,
    ) -> Claim:
        """Record a claim only when every cited source is already in the ledger."""
        ids = tuple(dict.fromkeys(source_ids))
        if not text.strip():
            raise ValueError("claim text is required")
        if not ids or any(source_id not in self._sources for source_id in ids):
            raise MissingCitationError("every claim needs at least one registered source")
        record = Claim(
            claim_id=claim_id or f"claim-{self._digest(text + '|' + '|'.join(ids))[:12]}",
            text=text.strip(),
            source_ids=ids,
            confidence=confidence.strip() or "unassessed",
            note=note.strip(),
        )
        existing = self._claims.get(record.claim_id)
        if existing and existing != record:
            raise ValueError(f"claim ID collision: {record.claim_id}")
        if not existing:
            self._claims[record.claim_id] = record
            self._append(self.claims_path, asdict(record))
        return self._claims[record.claim_id]

    def packet(self, query: str, claims: Iterable[Claim], open_questions: Iterable[str] = ()) -> ResearchPacket:
        """Assemble an export whose source list is derived from its claims."""
        selected = list(claims)
        for claim in selected:
            if claim.claim_id not in self._claims:
                raise MissingCitationError(f"claim is not registered: {claim.claim_id}")
        source_ids = list(dict.fromkeys(source_id for claim in selected for source_id in claim.source_ids))
        return ResearchPacket(
            query=query.strip(),
            created_at=self._now(),
            source_ids=source_ids,
            claims=selected,
            open_questions=[q.strip() for q in open_questions if q.strip()],
        )

    def get_source(self, source_id: str) -> SourceRecord:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise MissingCitationError(f"unknown source: {source_id}") from exc

    def get_claim(self, claim_id: str) -> Claim:
        try:
            return self._claims[claim_id]
        except KeyError as exc:
            raise MissingCitationError(f"unknown claim: {claim_id}") from exc

    @property
    def sources(self) -> tuple[SourceRecord, ...]:
        return tuple(self._sources.values())

    @property
    def claims(self) -> tuple[Claim, ...]:
        return tuple(self._claims.values())

    @staticmethod
    def _append(path: Path, value: Mapping[str, object]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")

    @staticmethod
    def _fetch_url(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "Foxwood-Research/0.1"})
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return response.read(MAX_SOURCE_BYTES + 1)

    @staticmethod
    def _html_to_text(value: str) -> str:
        value = re.sub(r"<script[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<style[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
        value = re.sub(r"<[^>]+>", " ", value)
        return re.sub(r"\s+", " ", value).strip()


# ── reading and writing the one log ──────────────────────────────────────────

def decision_log_path(ledger_root: str | Path) -> Path:
    """The ledger root's one append-only decision log.

    Defined once, here, so two writers cannot disagree about where "the same place"
    is. Both `pipe.record_verdict` and the Cutting Room floor resolve through this,
    which is what makes them one log rather than two logs that happen to sit in the
    same directory.
    """
    return Path(ledger_root).resolve() / DECISION_LOG_FILENAME


def read_decisions(path: str | Path,
                   owns: Callable[[Mapping[str, object]], bool]) -> list:
    """Every readable entry in this log that `owns` claims, in written order.

    `owns` is a structural predicate, not a check on `kind` or on the writer's
    name. An entry this reader does not recognise is passed over in silence -- one
    writer's decisions are not another writer's business, and a log that made them
    each other's business would force every writer to know every other writer.
    """
    path = Path(path)
    if not path.is_file():
        return []
    out: list = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and owns(entry):
            out.append(entry)
    return out


def append_decisions(path: str | Path,
                     entries: Iterable[Mapping[str, object]]) -> int:
    """Append entries one self-describing JSON object per line; return the count.

    Append-only and never rewritten. A decision that was later superseded is still
    a decision somebody made, and the history is the only thing that says so.
    """
    materialized = [entry for entry in entries if entry]
    if not materialized:
        return 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for entry in materialized:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return len(materialized)
