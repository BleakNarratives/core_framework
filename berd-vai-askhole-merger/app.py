"""Loopback-only web UI for the local lead/draft workbench."""
from __future__ import annotations

import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup

import workbench
from type3_potential import get_type3_potentials

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=workbench.MAX_CSV_BYTES + 64_000,
    SECRET_KEY=os.environ.get("WORKBENCH_SESSION_KEY") or os.urandom(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    TRUSTED_HOSTS=["localhost", "127.0.0.1"],
)
DB_PATH = Path(os.environ.get("WORKBENCH_DB", str(workbench.DEFAULT_DB))).expanduser()
PROJECT_ROOT = workbench.PROJECT_DIR.parent
PYTCH_DB_PATH = PROJECT_ROOT / "Pytch" / "pytch" / "pytch.db"
WHORL_HOME = Path(os.environ.get("WHORL_HOME", "~/.whorl")).expanduser()
WHORL_DB_PATH = WHORL_HOME / "whorl.db"
ASKHOLE_ROOT = PROJECT_ROOT / "UNPACKED" / "intake_2026-08-22-rclone-ready-for-cloud_AskHole-V-3" / "AskHole-V-3"

# Fixed catalog: routes expose only these curated project notes/source files, never arbitrary paths.
RESOURCE_CATALOG = {
    "berd": {"name": "Berd", "lane": "HOST", "status": "Handoff only", "path": "berd-vai-askhole-merger/berd/README.md", "source": workbench.PROJECT_DIR / "berd" / "README.md", "mode": "project briefs; no Berd app connection", "summary": "Berd is the agent host, not a badge. This workspace ships inspectable persona/skill briefs; the CLI refused project creation outside a Berd desktop session.", "read_only": True, "connected": False},
    "meboard": {"name": "Pivot / TILT / SCRYING / Ring", "lane": "VISOR", "status": "Pattern reference", "path": "RootBase/Meboard/src/components/", "source": PROJECT_ROOT / "RootBase" / "Meboard" / "src" / "components" / "RingSwitcher.tsx", "mode": "source inspected; not running inside this workbench", "summary": "The ring is a saved view mask; the Indicator Board separates reveal/normal; Pivot is described as a charter gate. This page adopts the navigation/control pattern, not a pretend Meboard runtime connection.", "read_only": True, "connected": False},
    "pytch": {"name": "Pytch", "lane": "CAMPAIGNS", "status": "Read-only SQLite", "path": "Pytch/pytch/pytch.db", "source": PROJECT_ROOT / "Pytch" / "README.md", "mode": "read-only local database; sender never invoked", "summary": "Inspect campaign, lead, outreach-queue, reply, and deal counts from Pytch's actual SQLite database. SMTP sending and campaign writes are not exposed here.", "read_only": True, "connected": False},
    "twoie": {"name": "Twoie", "lane": "SCOUT", "status": "Quarantined source", "path": "projects/agents/scouts/AgentTwoie.py", "source": PROJECT_ROOT / "projects" / "agents" / "scouts" / "AgentTwoie.py", "mode": "source view only; never execute", "summary": "The inspected legacy strategy module includes fabricated social proof and manufactured urgency. It is deliberately quarantined from lead messaging; open the source to audit it, not to run it.", "read_only": True, "connected": False},
    "hotseat": {"name": "Hotseat · Whorl", "lane": "DEBATE", "status": "Read-only SQLite", "path": "~/.whorl/whorl.db · hotseat_sessions", "source": PROJECT_ROOT / "Whorl" / "README.md", "mode": "read-only local database; no model invocation", "summary": "Three-voice idea stress-tests live in Whorl. This wormhole reports persisted session counts only; starting a session would invoke local models and is intentionally not a dashboard click.", "read_only": True, "connected": False},
    "vertical-ai": {"name": "Vertical AI", "lane": "OUTREACH", "status": "Prototype · locked", "path": "vertical_ai/manifest.json", "source": PROJECT_ROOT / "vertical_ai" / "manifest.json", "mode": "catalog only; scrape and SMTP disabled", "summary": "The actual manifest marks review scraping and email delivery as live network/SMTP entrypoints. This console makes neither action callable; it links the source/provenance boundary.", "read_only": True, "connected": False},
    "askhole": {"name": "AskHole", "lane": "ECONOMICS", "status": "Local scenario tool", "path": "integrations/economics.json ← AskHole v3", "source": ASKHOLE_ROOT / "README.md", "mode": "offline scenario math; imported estimates unverified", "summary": "Use the local AskHole economics table to explore a transparent, user-entered scenario. Legacy estimates are context—not verified current market data or a business-specific prediction.", "read_only": True, "connected": True},
    "vertical-engine": {"name": "Vertical AI Engine · Veritas", "lane": "ARCHIVE", "status": "Legacy archive", "path": "vertical_ai_engine/manifest.json", "source": PROJECT_ROOT / "vertical_ai_engine" / "manifest.json", "mode": "catalog only; optional Gemini/document tools not invoked", "summary": "The manifest labels this a legacy prototype with optional service dependencies. It stays an archive wormhole; no document, FOIA, profiling, or Gemini operation is run here.", "read_only": True, "connected": False},
}
    "whorl-refinery": {
        "name": "Whorl Refinery · Ollama",
        "lane": "REFINE",
        "status": "Governed local service · opt-in",
        "path": "127.0.0.1:8765/health",
        "source": PROJECT_ROOT / "Whorl" / "README.md",
        "mode": "loopback-only governed model routing; policy-gated",
        "summary": "Local Ollama refinery via Whorl skills. Pre/post processing, task-based routing, and versioned state snapshotter.",
        "read_only": False,
        "connected": False,
    },
RESOURCE_SOURCE_PATHS = {
    "berd": workbench.PROJECT_DIR / "berd" / "README.md",
    "meboard": PROJECT_ROOT / "RootBase" / "Meboard" / "src" / "components" / "RingSwitcher.tsx",
    "pytch": PROJECT_ROOT / "Pytch" / "README.md",
    "twoie": PROJECT_ROOT / "projects" / "agents" / "scouts" / "AgentTwoie.py",
    "hotseat": PROJECT_ROOT / "Whorl" / "README.md",
    "vertical-ai": PROJECT_ROOT / "vertical_ai" / "manifest.json",
    "askhole": ASKHOLE_ROOT / "README.md",
    "vertical-engine": PROJECT_ROOT / "vertical_ai_engine" / "manifest.json",
}


def _readonly_table_counts(
    db_path: Path, queries: dict[str, str], required_tables: set[str]
) -> dict[str, int] | None:
    """Run fixed SELECTs against a local SQLite file without initializing or writing it."""
    if not db_path.is_file():
        return None
    try:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.4) as db:
            db.execute("PRAGMA query_only = ON")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required_tables.issubset(tables):
                return None
            result = {}
            for key, sql in queries.items():
                if key == "queued" and "sent_at" not in {row[1] for row in db.execute("PRAGMA table_info(outreach)")}:
                    return None
                if key == "replies" and "replied" not in {row[1] for row in db.execute("PRAGMA table_info(outreach)")}:
                    return None
                result[key] = int(db.execute(sql).fetchone()[0])
            return result
    except (OSError, sqlite3.Error, ValueError):
        return None


def _read_askhole_economics() -> dict:
    try:
        raw = json.loads((workbench.PROJECT_DIR / "integrations" / "economics.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw.get("verticals", {}) if raw.get("trust") == "unverified_legacy_context" else {}


def control_room_snapshot() -> dict:
    counts = workbench.summary_counts(DB_PATH)
    with workbench.connect(DB_PATH) as local_db:
        draft_counts = {
            state: int(local_db.execute("SELECT COUNT(*) FROM drafts WHERE status = ?", (state,)).fetchone()[0])
            for state in ("draft", "reviewed", "approved-for-manual-export")
        }
    pytch = _readonly_table_counts(PYTCH_DB_PATH, {
        "campaigns": "SELECT COUNT(*) FROM campaigns",
        "leads": "SELECT COUNT(*) FROM leads",
        "outreach": "SELECT COUNT(*) FROM outreach",
        "queued": "SELECT COUNT(*) FROM outreach WHERE sent_at IS NULL",
        "replies": "SELECT COUNT(*) FROM outreach WHERE replied = 1",
        "deals": "SELECT COUNT(*) FROM deals",
    }, {"campaigns", "leads", "outreach", "deals"})
    whorl = _readonly_table_counts(WHORL_DB_PATH, {
        "signals": "SELECT COUNT(*) FROM signals",
        "unverified_signals": "SELECT COUNT(*) FROM signals WHERE COALESCE(verified, 0) = 0",
        "hotseat_sessions": "SELECT COUNT(*) FROM hotseat_sessions",
        "pitches": "SELECT COUNT(*) FROM pitches",
    }, {"signals", "hotseat_sessions", "pitches"})
    economics = _read_askhole_economics()
    services = {
        "berd": {"available": (workbench.PROJECT_DIR / "berd" / "README.md").is_file(), "connected": False, "counts": {}},
        "meboard": {"available": (RESOURCE_CATALOG["meboard"]["source"]).is_file(), "connected": False, "counts": {}},
        "pytch": {"available": pytch is not None, "connected": pytch is not None, "counts": pytch or {}},
        "twoie": {"available": RESOURCE_CATALOG["twoie"]["source"].is_file(), "connected": False, "counts": {}},
        "hotseat": {"available": whorl is not None, "connected": whorl is not None, "counts": {"sessions": whorl["hotseat_sessions"]} if whorl else {}},
        "vertical-ai": {"available": (PROJECT_ROOT / "vertical_ai" / "manifest.json").is_file(), "connected": False, "counts": {}},
        "askhole": {"available": bool(economics), "connected": bool(economics), "counts": {"verticals": len(economics)}},
        "vertical-engine": {"available": (PROJECT_ROOT / "vertical_ai_engine" / "manifest.json").is_file(), "connected": False, "counts": {}},
    }
    signals = []
    if counts["unverified_evidence"]:
        signals.append({"id": "evidence-review", "level": "review", "title": f"{counts['unverified_evidence']} evidence items still unverified", "detail": "These came from local lead intake; check provenance before relying on them.", "next_move": "Review local evidence", "href": "/#intake"})
    if draft_counts["draft"] or draft_counts["reviewed"]:
        signals.append({"id": "draft-gate", "level": "review", "title": f"{draft_counts['draft'] + draft_counts['reviewed']} drafts need a human gate", "detail": f"{draft_counts['draft']} draft · {draft_counts['reviewed']} reviewed · delivery is disabled.", "next_move": "Open the draft queue", "href": "/#intake"})
    if pytch and pytch["queued"]:
        signals.append({"id": "pytch-queue", "level": "action", "title": f"Pytch has {pytch['queued']} unsent outreach records", "detail": "Read from Pytch SQLite. Review each exact item before staging; send remains disabled.", "next_move": "Review Pytch queue", "href": "/wormholes/pytch"})
    if whorl and whorl["unverified_signals"]:
        signals.append({"id": "whorl-signals", "level": "review", "title": f"Whorl has {whorl['unverified_signals']} unverified signals", "detail": f"{whorl['signals']} total persisted signals; verified status is read as stored, not independently audited.", "next_move": "Inspect Whorl signals", "href": "/wormholes/hotseat"})
    if economics:
        signals.append({"id": "economics-context", "level": "info", "title": f"AskHole economics: {len(economics)} legacy verticals", "detail": "Historical assumptions are explicitly unverified and must not be presented as lead facts.", "next_move": "Open scenario calculator", "href": "/wormholes/askhole"})
    signals.sort(key=lambda signal: ("action", "review", "info").index(signal["level"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workbench": {"counts": counts, "drafts": draft_counts, "leads": len(workbench.list_leads(DB_PATH))},
        "services": services,
        "signals": signals,
        "ring_modes": ["glass", "forge", "air"],
        "scrying_mode": "local rules from live SQLite/file state; no model call",
    }


@app.before_request
def protect_form_posts():
    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="Invalid form token. Reload the page and try again.")


@app.after_request
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.context_processor
def template_helpers():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_field": lambda: Markup('<input type="hidden" name="_csrf_token" value="{}">').format(session["_csrf_token"])}


@app.get("/docs/safety")
def safety_document():
    return app.response_class(
        (workbench.PROJECT_DIR / "docs" / "SAFETY.md").read_text(encoding="utf-8"),
        mimetype="text/markdown; charset=utf-8",
    )


@app.get("/")
@app.get("/control-room", endpoint="control_room")
def control_room():
    snapshot = control_room_snapshot()
    return render_template(
        "control_room.html",
        snapshot=snapshot,
        catalog=RESOURCE_CATALOG,
    )


@app.get("/intake")
def index():
    snapshot = control_room_snapshot()
    return render_template(
        "index.html",
        leads=workbench.list_leads(DB_PATH),
        drafts=workbench.get_drafts(DB_PATH),
        counts=snapshot["workbench"]["counts"],
    )


@app.get("/api/control-room")
def control_room_api():
    response = jsonify(control_room_snapshot())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/wormholes/<slug>")
def wormhole(slug: str):
    resource = RESOURCE_CATALOG.get(slug)
    if resource is None:
        abort(404)
    if slug == "askhole" and not resource["source"].is_file():
        abort(503, description="AskHole source directory is unavailable")
    snapshot = control_room_snapshot()
    records = []
    if slug == "pytch" and snapshot["services"][slug]["available"]:
        try:
            with sqlite3.connect(f"file:{PYTCH_DB_PATH.as_posix()}?mode=ro", uri=True, timeout=0.4) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only = ON")
                campaign_columns = {row[1] for row in db.execute("PRAGMA table_info(campaigns)")}
                campaign_fields = {"id", "wrapper_name", "target_persona", "status", "emails_sent", "replies", "demos_booked", "deals_closed", "revenue"}
                if campaign_fields.issubset(campaign_columns):
                    records = [dict(row) for row in db.execute(
                        """SELECT wrapper_name, target_persona, status, emails_sent, replies,
                                  demos_booked, deals_closed, revenue FROM campaigns ORDER BY id DESC LIMIT 12"""
                    )]
                outreach_columns = {row[1] for row in db.execute("PRAGMA table_info(outreach)")}
                lead_columns = {row[1] for row in db.execute("PRAGMA table_info(leads)")}
                required_outreach = {"id", "lead_id", "campaign", "subject", "body", "sent_at"}
                required_lead = {"id", "company", "email"}
                if required_outreach.issubset(outreach_columns) and required_lead.issubset(lead_columns):
                    queue_sql = """SELECT o.id, o.lead_id, o.campaign, o.subject, o.body, o.sent_at,
                                          l.company, l.contact_name, l.email, l.source, l.industry
                                   FROM outreach o LEFT JOIN leads l ON l.id=o.lead_id
                                   WHERE o.sent_at IS NULL ORDER BY o.id LIMIT 50"""
                    queue = [dict(row) for row in db.execute(queue_sql)]
        except sqlite3.Error:
            records = []
            queue = []
    elif slug == "hotseat" and snapshot["services"][slug]["available"]:
        try:
            with sqlite3.connect(f"file:{WHORL_DB_PATH.as_posix()}?mode=ro", uri=True, timeout=0.4) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only = ON")
                records = [dict(row) for row in db.execute(
                    "SELECT timestamp, topic, vertical, score FROM hotseat_sessions ORDER BY timestamp DESC LIMIT 10"
                )]
        except sqlite3.Error:
            records = []
    elif slug == "askhole":
        records = sorted(_read_askhole_economics().items())
    queue = locals().get("queue", [])
    source_exists = resource["source"].is_file()
    source_path = RESOURCE_SOURCE_PATHS[slug]
    if slug == "meboard":
        source_path = PROJECT_ROOT / "RootBase" / "Meboard" / "src" / "components" / "IndicatorBoard.tsx"
    elif slug == "berd":
        source_path = workbench.PROJECT_DIR / "berd" / "README.md"
    return render_template(
        "wormhole.html",
        resource={**resource, "slug": slug, "state": snapshot["services"][slug], "source_exists": source_exists},
        source_path=source_path,
        economics=_read_askhole_economics() if slug == "askhole" else {},
        records=records,
        queue=queue,
        snapshot=snapshot,
    )


@app.get("/wormholes/<slug>/source")
def wormhole_source(slug: str):
    source_path = RESOURCE_SOURCE_PATHS.get(slug)
    if source_path is None or not source_path.is_file():
        abort(404)
    if source_path.stat().st_size > 128_000:
        abort(413, description="Curated source view exceeds the 128 KB limit")
    return app.response_class(
        source_path.read_text(encoding="utf-8"),
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": "inline"},
    )


@app.post("/pytch/<int:record_id>/stage")
def stage_pytch(record_id: int):
    if not PYTCH_DB_PATH.is_file():
        return jsonify({"error": "Pytch database is unavailable"}), 503
    try:
        with sqlite3.connect(f"file:{PYTCH_DB_PATH.as_posix()}?mode=ro", uri=True, timeout=0.5) as source_db:
            source_db.row_factory = sqlite3.Row
            source_db.execute("PRAGMA query_only = ON")
            outreach_columns = {row[1] for row in source_db.execute("PRAGMA table_info(outreach)")}
            lead_columns = {row[1] for row in source_db.execute("PRAGMA table_info(leads)")}
            if not {"id", "lead_id", "campaign", "subject", "body", "sent_at"}.issubset(outreach_columns):
                return jsonify({"error": "Pytch outreach schema is not recognized"}), 503
            if not {"id", "company", "email", "industry"}.issubset(lead_columns):
                return jsonify({"error": "Pytch lead schema is not recognized"}), 503
            row = source_db.execute(
                """SELECT o.id, o.campaign, o.subject, o.body, o.sent_at,
                          l.company, l.email, l.industry
                   FROM outreach o LEFT JOIN leads l ON l.id=o.lead_id
                   WHERE o.id=? AND o.sent_at IS NULL""",
                (record_id,),
            ).fetchone()
            if row is None:
                return jsonify({"error": "Pytch record is no longer unsent, or does not exist"}), 409
            source_record = dict(row)
        lead_id = workbench.stage_pytch_record(DB_PATH, source_record)
    except (sqlite3.Error, OSError, ValueError) as exc:
        return jsonify({"error": f"Could not stage Pytch record: {exc}"}), 400
    draft_id = _draft_for_lead(lead_id)
    response = jsonify({"lead_id": lead_id, "redirect": url_for("draft_detail", draft_id=draft_id)})
    response.headers["Cache-Control"] = "no-store"
    return response


def _draft_for_lead(lead_id: int) -> int:
    record = workbench.get_lead(DB_PATH, lead_id)
    if record is None:
        raise ValueError("staged lead disappeared before draft creation")
    drafts = record["drafts"]
    return int(drafts[0]["id"]) if drafts else workbench.create_draft(DB_PATH, lead_id)


@app.post("/tools/askhole/scenario")
def askhole_scenario():
    if not RESOURCE_CATALOG["askhole"]["source"].is_file():
        abort(503, description="AskHole source directory is unavailable")
    vertical = request.form.get("vertical", "")
    try:
        missed_calls = int(request.form.get("missed_calls", "0"))
        recovery_rate = float(request.form.get("recovery_rate", "0"))
    except ValueError:
        abort(400, description="Scenario values must be valid numbers")
    economics = _read_askhole_economics().get(vertical)
    if economics is None:
        abort(400, description="Choose a vertical in the imported AskHole table")
    if not 0 <= missed_calls <= 10_000 or not 0 <= recovery_rate <= 1:
        abort(400, description="Missed calls must be 0–10,000 and recovery rate 0–1")
    per_call = economics.get("missed_call_cost")
    if not isinstance(per_call, (int, float)) or per_call < 0:
        abort(400, description="This vertical has no usable missed-call assumption")
    gross_context = round(missed_calls * per_call * recovery_rate, 2)
    return jsonify({
        "vertical": vertical,
        "missed_calls": missed_calls,
        "recovery_rate": recovery_rate,
        "legacy_assumption_per_missed_call": per_call,
        "scenario_context_not_forecast": gross_context,
        "trust": "unverified_legacy_context",
        "source": economics.get("source", "not provided"),
        "formula": "missed calls × imported per-call assumption × user-entered recovery rate",
    })


@app.post("/leads")
def add_lead():
    fields = {key: request.form.get(key, "") for key in (
        "name", "vertical", "city", "website", "rating", "review_count", "notes", "source"
    )}
    try:
        lead_id = workbench.add_lead(DB_PATH, fields)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    flash(f"Lead added as #{lead_id}. Supplied fields are unverified.", "success")
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.post("/leads/import")
def import_leads():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        flash("Choose a CSV file to import.", "error")
        return redirect(url_for("index"))
    if not upload.filename.lower().endswith(".csv"):
        flash("Only CSV files are accepted.", "error")
        return redirect(url_for("index"))
    try:
        ids = workbench.import_csv(DB_PATH, upload.stream.read(workbench.MAX_CSV_BYTES + 1))
    except (ValueError, UnicodeError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))
    flash(f"Imported {len(ids)} leads. All imported fields are unverified.", "success")
    return redirect(url_for("lead_detail", lead_id=ids[0]))


@app.post("/drafts/<int:draft_id>/edit")
def edit_draft(draft_id: int):
    try:
        workbench.update_draft_body(DB_PATH, draft_id, request.form.get("body", ""))
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash("Draft updated. Prior review and approval were revoked.", "success")
    return redirect(url_for("draft_detail", draft_id=draft_id))


@app.get("/leads/<int:lead_id>")
def lead_detail(lead_id: int):
    record = workbench.get_lead(DB_PATH, lead_id)
    if record is None:
        abort(404)
    draft_id = None
    if record["lead"].get("source_system") == "pytch" and not record["drafts"]:
        draft_id = workbench.create_draft(DB_PATH, lead_id)
        return redirect(url_for("draft_detail", draft_id=draft_id))
    return render_template(
        "lead.html",
        record=record,
        type3_potentials=get_type3_potentials(record["lead"], record["evidence"]),
    )


@app.post("/leads/<int:lead_id>/drafts")
def make_draft(lead_id: int):
    try:
        draft_id = workbench.create_draft(DB_PATH, lead_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("lead_detail", lead_id=lead_id))
    flash("Draft created. No message has been sent.", "success")
    return redirect(url_for("draft_detail", draft_id=draft_id))


@app.get("/drafts/<int:draft_id>")
def draft_detail(draft_id: int):
    draft = _find_draft(draft_id)
    if draft is None:
        abort(404)
    record = workbench.get_lead(DB_PATH, int(draft["lead_id"]))
    if record is None:
        abort(404)
    return render_template("draft.html", draft=draft, lead=record["lead"])


@app.post("/drafts/<int:draft_id>/review")
def review(draft_id: int):
    try:
        workbench.review_draft(
            DB_PATH,
            draft_id,
            request.form.get("reviewer", ""),
            request.form.get("notes", ""),
            request.form.get("recipient", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash("Review recorded. This is not permission to send.", "success")
    return redirect(url_for("draft_detail", draft_id=draft_id))


@app.post("/drafts/<int:draft_id>/approve")
def approve(draft_id: int):
    if request.form.get("confirm") != "yes":
        flash("Confirm that you reviewed this exact text before approving export.", "error")
        return redirect(url_for("draft_detail", draft_id=draft_id))
    try:
        draft = _find_draft(draft_id)
        lead = workbench.get_lead(DB_PATH, int(draft["lead_id"])) if draft else None
        if lead and lead["lead"].get("source_system") == "pytch" and request.form.get("confirm_recipient") != "yes":
            raise ValueError("Confirm that you rechecked the Pytch recipient against its source row")
        workbench.approve_manual_export(DB_PATH, draft_id)
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash("Approved for manual copy/export only. The app cannot send messages.", "success")
    return redirect(url_for("draft_detail", draft_id=draft_id))


@app.get("/drafts/<int:draft_id>/export")
def export(draft_id: int):
    try:
        body = workbench.export_draft(DB_PATH, draft_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("draft_detail", draft_id=draft_id))
    draft = _find_draft(draft_id)
    if draft and draft.get("source_system") == "pytch":
        with workbench.connect(DB_PATH) as db:
            approval = db.execute("SELECT approved_recipient_sha256 FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not approval or not approval["approved_recipient_sha256"]:
            abort(403, description="Pytch recipient must be verified and approved before export")
    return app.response_class(
        body,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="draft-{draft_id}.txt"'},
    )


def _find_draft(draft_id: int):
    return workbench.get_draft(DB_PATH, draft_id)


@app.get("/health")
def health():
    return {"status": "ok", "mode": "local-only", "delivery": "disabled"}


if __name__ == "__main__":
    workbench.initialize(DB_PATH)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8765")), debug=False)
