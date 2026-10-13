"""Local-first data and workflow layer for the Berd/Vertical AI/AskHole workbench."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_DIR / "workbench_data" / "workbench.sqlite3"
ECONOMICS_FILE = PROJECT_DIR / "integrations" / "economics.json"
MAX_FIELD_CHARS = 4_000
MAX_LEADS_PER_IMPORT = 500
MAX_CSV_BYTES = 1_000_000
ALLOWED_CSV_FIELDS = {
    "name", "vertical", "city", "website", "rating", "review_count", "notes", "source"
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any, field: str, *, required: bool = False, limit: int = MAX_FIELD_CHARS) -> str:
    if value is None:
        value = ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be text")
    result = str(value).strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in result):
        raise ValueError(f"{field} contains unsupported control characters")
    return result


@contextmanager
def connect(db_path: str | Path = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() == (PROJECT_DIR / "workbench_data").resolve():
        os.chmod(path.parent, 0o700)
    connection = sqlite3.connect(path, timeout=5)
    try:
        os.chmod(path, 0o600)
    except OSError:
        connection.close()
        raise
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _validated_website(value: Any) -> str:
    website = _text(value, "website", limit=500)
    if not website:
        return ""
    try:
        parts = urlsplit(website)
        valid = parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)
        valid = valid and parts.username is None and parts.password is None
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("website must be an http(s) URL without embedded credentials")
    return website


def initialize(db_path: str | Path = DEFAULT_DB) -> None:
    with connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                vertical TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                rating TEXT NOT NULL DEFAULT '',
                review_count TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'user-provided',
                source_system TEXT NOT NULL DEFAULT '',
                source_record_id TEXT NOT NULL DEFAULT '',
                recipient_sha256 TEXT NOT NULL DEFAULT '',
                source_body_sha256 TEXT NOT NULL DEFAULT '',
                source_recipient_hash TEXT NOT NULL DEFAULT '',
                source_body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                field_name TEXT NOT NULL,
                claim TEXT NOT NULL,
                source TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                trust TEXT NOT NULL DEFAULT 'unverified',
                UNIQUE(lead_id, field_name, sha256)
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                content_sha256 TEXT NOT NULL,
                reviewer TEXT NOT NULL DEFAULT '',
                review_notes TEXT NOT NULL DEFAULT '',
                approved_sha256 TEXT NOT NULL DEFAULT '',
                reviewed_recipient_sha256 TEXT NOT NULL DEFAULT '',
                approved_recipient_sha256 TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                reviewed_at TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL DEFAULT '',
                economics_snapshot TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY,
                event TEXT NOT NULL,
                record_type TEXT NOT NULL,
                record_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS evidence_lead_idx ON evidence(lead_id);
            CREATE INDEX IF NOT EXISTS drafts_lead_idx ON drafts(lead_id, id DESC);
            CREATE TABLE IF NOT EXISTS pytch_staging (
                id INTEGER PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                source_system TEXT NOT NULL,
                source_record_id TEXT NOT NULL,
                staged_at TEXT NOT NULL,
                UNIQUE(source_system, source_record_id)
            );
            """
        )
        lead_columns = {row["name"] for row in db.execute("PRAGMA table_info(leads)")}
        for column in ("source_system", "source_record_id", "recipient_sha256", "source_body_sha256", "source_recipient_hash", "source_body"):
            if column not in lead_columns:
                db.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        db.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS leads_source_origin_idx
               ON leads(source_system, source_record_id)
               WHERE source_system != '' AND source_record_id != ''"""
        )
        draft_columns = {row["name"] for row in db.execute("PRAGMA table_info(drafts)")}
        for column in ("economics_snapshot", "reviewed_recipient_sha256", "approved_recipient_sha256"):
            if column not in draft_columns:
                db.execute(f"ALTER TABLE drafts ADD COLUMN {column} TEXT NOT NULL DEFAULT '{{}}'")


def _audit(db: sqlite3.Connection, event: str, record_type: str, record_id: int | None) -> None:
    db.execute(
        "INSERT INTO audit_events(event, record_type, record_id, created_at) VALUES (?, ?, ?, ?)",
        (event, record_type, record_id, utc_now()),
    )


def _insert_lead(db: sqlite3.Connection, raw: dict[str, Any]) -> int:
    lead = {
        "name": _text(raw.get("name"), "name", required=True, limit=200),
        "vertical": _text(raw.get("vertical"), "vertical", limit=100),
        "city": _text(raw.get("city"), "city", limit=200),
        "website": _validated_website(raw.get("website")),
        "rating": _text(raw.get("rating"), "rating", limit=30),
        "review_count": _text(raw.get("review_count"), "review_count", limit=30),
        "source": _text(raw.get("source") or "user-provided", "source", limit=300),
        "source_system": _text(raw.get("source_system"), "source system", limit=80),
        "source_record_id": _text(raw.get("source_record_id"), "source record id", limit=120),
        "recipient_sha256": _text(raw.get("recipient_sha256"), "recipient hash", limit=64),
        "source_body_sha256": _text(raw.get("source_body_sha256"), "source body hash", limit=64),
        "source_recipient_hash": _text(raw.get("source_recipient_hash"), "source recipient hash", limit=64),
        "source_body": _text(raw.get("source_body"), "source body", limit=MAX_FIELD_CHARS),
    }
    notes = _text(raw.get("notes"), "notes")
    cursor = db.execute(
        """INSERT INTO leads(name, vertical, city, website, rating, review_count, source,
                            source_system, source_record_id, recipient_sha256, source_body_sha256,
                            source_recipient_hash, source_body, created_at)
           VALUES (:name, :vertical, :city, :website, :rating, :review_count, :source,
                   :source_system, :source_record_id, :recipient_sha256, :source_body_sha256,
                   :source_recipient_hash, :source_body, :created_at)""",
        {**lead, "created_at": utc_now()},
    )
    lead_id = int(cursor.lastrowid)
    for field in ("vertical", "city", "website", "rating", "review_count"):
        value = lead[field]
        if value:
            _insert_evidence(db, lead_id, field, value, lead["source"])
    if notes:
        _insert_evidence(db, lead_id, "notes", notes, lead["source"])
    _audit(db, "lead.created", "lead", lead_id)
    return lead_id


def _insert_evidence(db: sqlite3.Connection, lead_id: int, field_name: str, claim: str, source: str) -> int:
    digest = hashlib.sha256(claim.encode("utf-8")).hexdigest()
    db.execute(
        """INSERT OR IGNORE INTO evidence(lead_id, field_name, claim, source, captured_at, sha256, trust)
           VALUES (?, ?, ?, ?, ?, ?, 'unverified')""",
        (lead_id, field_name, claim, source, utc_now(), digest),
    )
    row = db.execute(
        "SELECT id FROM evidence WHERE lead_id = ? AND field_name = ? AND sha256 = ?",
        (lead_id, field_name, digest),
    ).fetchone()
    return int(row["id"])


def add_lead(db_path: str | Path, raw: dict[str, Any]) -> int:
    if not isinstance(raw, dict):
        raise ValueError("lead must be an object")
    initialize(db_path)
    with connect(db_path) as db:
        return _insert_lead(db, raw)


def stage_pytch_record(db_path: str | Path, record: dict[str, Any]) -> int:
    """Copy one user-selected unsent Pytch record and provenance into the local review ledger."""
    if not isinstance(record, dict):
        raise ValueError("Pytch record must be an object")
    source_id = _text(record.get("id"), "Pytch record id", required=True, limit=120)
    recipient = _text(record.get("email"), "recipient", limit=320)
    body = _text(record.get("body"), "source draft", limit=MAX_FIELD_CHARS)
    if not body:
        raise ValueError("Pytch record has no body to review")
    source_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    recipient_hash = hashlib.sha256(recipient.casefold().encode("utf-8")).hexdigest() if recipient else ""
    fields = {
        "name": _text(record.get("company") or f"Pytch outreach #{source_id}", "business name", required=True, limit=200),
        "vertical": _text(record.get("industry"), "vertical", limit=100),
        "city": "",
        "website": "",
        "rating": "",
        "review_count": "",
        "notes": f"Imported unsent Pytch item #{source_id}. Original subject: {_text(record.get('subject'), 'subject', limit=300)}. Recipient is not copied; recipient SHA-256: {recipient_hash or 'not supplied'}. Original message is stored as evidence, unverified.",
        "source": f"Pytch local SQLite · outreach #{source_id}",
        "source_system": "pytch",
        "source_record_id": source_id,
        "recipient_sha256": recipient_hash,
        "source_recipient_hash": recipient_hash,
        "source_body_sha256": source_hash,
        "source_body": body,
    }
    initialize(db_path)
    with connect(db_path) as db:
        existing = db.execute(
            "SELECT lead_id FROM pytch_staging WHERE source_system='pytch' AND source_record_id=?",
            (source_id,),
        ).fetchone()
        if existing:
            return int(existing["lead_id"])
        lead_id = _insert_lead(db, fields)
        _insert_evidence(db, lead_id, "pytch_original_body", body, fields["source"])
        db.execute(
            "INSERT INTO pytch_staging(lead_id, source_system, source_record_id, staged_at) VALUES (?, 'pytch', ?, ?)",
            (lead_id, source_id, utc_now()),
        )
        _audit(db, "pytch.unsent_item_staged", "lead", lead_id)
        return lead_id


def import_csv(db_path: str | Path, content: str | bytes) -> list[int]:
    if isinstance(content, bytes):
        if len(content) > MAX_CSV_BYTES:
            raise ValueError("CSV exceeds the 1 MB import limit")
        try:
            content = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must be UTF-8 encoded") from exc
    elif not isinstance(content, str):
        raise ValueError("CSV content must be text")
    if len(content.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 1 MB import limit")
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    if not headers or "name" not in headers:
        raise ValueError("CSV requires a name column")
    unknown = set(headers) - ALLOWED_CSV_FIELDS
    if unknown:
        raise ValueError("unsupported CSV columns: " + ", ".join(sorted(unknown)))
    rows = list(reader)
    if len(rows) > MAX_LEADS_PER_IMPORT:
        raise ValueError(f"CSV exceeds the {MAX_LEADS_PER_IMPORT}-lead import limit")
    if not rows:
        raise ValueError("CSV contains no lead rows")
    initialize(db_path)
    ids: list[int] = []
    with connect(db_path) as db:
        with db:
            for row in rows:
                lead_data = {key: row.get(key, "") for key in headers}
                lead_data["source"] = lead_data.get("source") or "CSV import (user-provided)"
                ids.append(_insert_lead(db, lead_data))
            _audit(db, "leads.csv_imported", "batch", len(ids))
    return ids


def summary_counts(db_path: str | Path = DEFAULT_DB) -> dict[str, int]:
    """Return uncapped local counts for dashboard metrics."""
    initialize(db_path)
    with connect(db_path) as db:
        counts = db.execute(
            """SELECT
                 (SELECT COUNT(*) FROM leads) AS lead_records,
                 (SELECT COUNT(*) FROM evidence WHERE trust='unverified') AS unverified_evidence,
                 (SELECT COUNT(*) FROM drafts) AS drafts
            """
        ).fetchone()
    return {key: int(counts[key]) for key in ("lead_records", "unverified_evidence", "drafts")}


def list_leads(db_path: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        rows = db.execute(
            """SELECT l.*, (SELECT COUNT(*) FROM evidence e WHERE e.lead_id=l.id) AS evidence_count,
                      (SELECT COUNT(*) FROM drafts d WHERE d.lead_id=l.id) AS draft_count
               FROM leads l ORDER BY l.id DESC"""
        ).fetchall()
    return [dict(row) for row in rows]


def get_lead(db_path: str | Path, lead_id: int) -> dict[str, Any] | None:
    initialize(db_path)
    with connect(db_path) as db:
        lead = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead is None:
            return None
        evidence = db.execute(
            "SELECT * FROM evidence WHERE lead_id = ? ORDER BY id", (lead_id,)
        ).fetchall()
        drafts = db.execute(
            "SELECT * FROM drafts WHERE lead_id = ? ORDER BY id DESC", (lead_id,)
        ).fetchall()
    return {"lead": dict(lead), "evidence": [dict(row) for row in evidence], "drafts": [dict(row) for row in drafts]}


def _load_economics() -> dict[str, Any]:
    try:
        data = json.loads(ECONOMICS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("verticals", {}) if data.get("trust") == "unverified_legacy_context" else {}


def _draft_body(lead: dict[str, Any]) -> str:
    if lead.get("source_system") == "pytch" and lead.get("source_body"):
        return str(lead["source_body"])
    business = lead["name"]
    vertical = lead["vertical"] or "customer inquiries"
    greeting = f"Hello {business},"
    city_line = f" I’m reaching out to businesses in {lead['city']}." if lead["city"] else ""
    return (
        f"Subject: A question about {vertical} intake\n\n"
        f"{greeting}\n\n"
        f"I’m exploring how businesses handle {vertical} inquiries.{city_line} "
        "I don’t know whether intake or follow-up is a problem for your business, "
        "so I don’t want to assume. If it is something you’re looking at, would "
        "you be open to a brief conversation?\n\n"
        "If this isn’t relevant, no reply is needed.\n\n"
        "[Add your name and accurate business identity before any manual use.]"
    )


def create_draft(db_path: str | Path, lead_id: int) -> int:
    initialize(db_path)
    with connect(db_path) as db:
        lead_row = db.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if lead_row is None:
            raise ValueError("lead not found")
        lead = dict(lead_row)
        evidence = db.execute(
            "SELECT id FROM evidence WHERE lead_id = ? ORDER BY id", (lead_id,)
        ).fetchall()
        body = _draft_body(lead)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        economics = {} if lead.get("source_system") == "pytch" else _load_economics().get(lead["vertical"].strip().lower(), {})
        economics_snapshot = json.dumps(economics, sort_keys=True)
        cursor = db.execute(
            """INSERT INTO drafts(lead_id, body, evidence_ids, status, content_sha256, created_at, economics_snapshot)
               VALUES (?, ?, ?, 'draft', ?, ?, ?)""",
            (lead_id, body, json.dumps([int(row["id"]) for row in evidence]), digest, utc_now(), economics_snapshot),
        )
        draft_id = int(cursor.lastrowid)
        _audit(db, "draft.created", "draft", draft_id)
        return draft_id


def review_draft(
    db_path: str | Path, draft_id: int, reviewer: str, notes: str, recipient: str = ""
) -> None:
    reviewer = _text(reviewer, "reviewer", required=True, limit=120)
    notes = _text(notes, "review notes", required=True, limit=MAX_FIELD_CHARS)
    recipient = _text(recipient, "recipient", limit=320)
    initialize(db_path)
    with connect(db_path) as db:
        row = db.execute(
            """SELECT d.status, d.body, d.content_sha256, l.source_system,
                      l.source_recipient_hash
               FROM drafts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?""",
            (draft_id,),
        ).fetchone()
        if row is None:
            raise ValueError("draft not found")
        if row["status"] == "approved-for-manual-export":
            raise ValueError("approved drafts are immutable; create a new draft to review changes")
        if hashlib.sha256(row["body"].encode("utf-8")).hexdigest() != row["content_sha256"]:
            raise ValueError("draft content changed outside the review flow; create a fresh draft")
        recipient_digest = ""
        if row["source_system"] == "pytch":
            if not recipient or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", recipient):
                raise ValueError("verify and enter the recipient address from the original Pytch row")
            recipient_digest = hashlib.sha256(recipient.casefold().encode("utf-8")).hexdigest()
            if not row["source_recipient_hash"] or not hmac.compare_digest(recipient_digest, row["source_recipient_hash"]):
                raise ValueError("recipient does not match the staged Pytch source; verify the source row")
        db.execute(
            """UPDATE drafts SET status='reviewed', reviewer=?, review_notes=?, reviewed_at=?,
                      reviewed_recipient_sha256=?, approved_sha256='', approved_recipient_sha256='', approved_at=''
               WHERE id=?""",
            (reviewer, notes, utc_now(), recipient_digest, draft_id),
        )
        _audit(db, "draft.reviewed", "draft", draft_id)


def update_draft_body(db_path: str | Path, draft_id: int, body: str) -> None:
    body = _text(body, "draft body", required=True, limit=MAX_FIELD_CHARS)
    initialize(db_path)
    with connect(db_path) as db:
        row = db.execute("SELECT status FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise ValueError("draft not found")
        if row["status"] == "approved-for-manual-export":
            raise ValueError("approved drafts are immutable; create a new draft to edit")
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        db.execute(
            """UPDATE drafts SET body=?, content_sha256=?, status='draft', reviewer='', review_notes='',
                      reviewed_at='', reviewed_recipient_sha256='', approved_sha256='',
                      approved_recipient_sha256='', approved_at='' WHERE id=?""",
            (body, digest, draft_id),
        )
        _audit(db, "draft.edited", "draft", draft_id)


def approve_manual_export(db_path: str | Path, draft_id: int) -> None:
    initialize(db_path)
    with connect(db_path) as db:
        row = db.execute(
            """SELECT d.status, d.content_sha256, d.body, d.reviewed_recipient_sha256,
                      l.source_system, l.source_recipient_hash
               FROM drafts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?""",
            (draft_id,),
        ).fetchone()
        if row is None:
            raise ValueError("draft not found")
        if row["status"] != "reviewed":
            raise ValueError("a draft must be reviewed before manual export approval")
        if hashlib.sha256(row["body"].encode("utf-8")).hexdigest() != row["content_sha256"]:
            raise ValueError("draft body no longer matches its content hash")
        if row["source_system"] == "pytch" and (
            not row["reviewed_recipient_sha256"]
            or not row["source_recipient_hash"]
            or not hmac.compare_digest(row["reviewed_recipient_sha256"], row["source_recipient_hash"])
        ):
            raise ValueError("Pytch recipient verification is missing or no longer matches")
        db.execute(
            """UPDATE drafts SET status='approved-for-manual-export', approved_sha256=?,
                      approved_recipient_sha256=reviewed_recipient_sha256, approved_at=? WHERE id=?""",
            (row["content_sha256"], utc_now(), draft_id),
        )
        _audit(db, "draft.approved_for_manual_export", "draft", draft_id)


def export_draft(db_path: str | Path, draft_id: int) -> str:
    initialize(db_path)
    with connect(db_path) as db:
        row = db.execute(
            "SELECT d.*, l.source_system, l.source_record_id, l.source_recipient_hash, l.source_body_sha256 FROM drafts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?",
            (draft_id,),
        ).fetchone()
    if row is None:
        raise ValueError("draft not found")
    if row["status"] != "approved-for-manual-export" or row["approved_sha256"] != row["content_sha256"]:
        raise ValueError("draft is not approved for manual export")
    if hashlib.sha256(row["body"].encode("utf-8")).hexdigest() != row["content_sha256"]:
        raise ValueError("draft body no longer matches its content hash")
    if row["source_system"] == "pytch" and (
        not row["approved_recipient_sha256"]
        or not hmac.compare_digest(row["approved_recipient_sha256"], row["source_recipient_hash"])
    ):
        raise ValueError("Pytch recipient approval is missing or invalid")
    return str(row["body"])


def get_draft(db_path: str | Path, draft_id: int) -> dict[str, Any] | None:
    initialize(db_path)
    with connect(db_path) as db:
        row = db.execute(
            "SELECT d.*, l.name AS lead_name FROM drafts d JOIN leads l ON l.id=d.lead_id WHERE d.id=?",
            (draft_id,),
        ).fetchone()
    return dict(row) if row else None


def get_drafts(db_path: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        rows = db.execute(
            """SELECT d.*, l.name AS lead_name FROM drafts d JOIN leads l ON l.id=d.lead_id
               ORDER BY d.id DESC LIMIT 100"""
        ).fetchall()
    return [dict(row) for row in rows]


def list_audit_events(db_path: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    initialize(db_path)
    with connect(db_path) as db:
        rows = db.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
    return [dict(row) for row in rows]
