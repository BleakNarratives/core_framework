#!/usr/bin/env python3
"""Standalone, offline Termux scout collector; Python standard library only.

Scans a small set of likely fixture directories under RootBase, normalizes
market/filing/news JSON, and persists evidence in SQLite plus a JSON report.
It does not fetch the network or claim that a signal predicts an outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

NAMES = {"market_signals.json", "sec_filings.json", "news_feed.json"}
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "cache", "dist", "build"}


def find_inputs(root: Path, explicit: list[Path]) -> list[Path]:
    found = {p.resolve() for p in explicit if p.is_file()}
    # Scope the walk to likely data locations: don't crawl the whole phone.
    candidates = [root, root / "data", root / "fixtures", root / "chronoscouts", root / "core_framework"]
    for base in candidates:
        if not base.is_dir():
            continue
        for current, dirs, files in os.walk(base):
            here = Path(current)
            depth = len(here.relative_to(base).parts)
            dirs[:] = [d for d in dirs if d not in SKIP] if depth < 4 else []
            for name in files:
                if name in NAMES:
                    found.add((here / name).resolve())
    return sorted(found)


def records_from(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Skip {path}: {exc}")
        return []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = next((payload[k] for k in ("signals", "targets", "items", "filings") if isinstance(payload.get(k), list)), [])
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def normalize(path: Path, raw: dict) -> dict:
    title = str(raw.get("title") or raw.get("summary") or raw.get("name") or "Untitled signal").strip()
    url = str(raw.get("url") or raw.get("link") or "").strip()
    source = str(raw.get("source") or path.stem.removesuffix("_feed") or "local").strip()
    ticker = str(raw.get("ticker") or raw.get("entity") or "UNKNOWN").strip().upper()
    observed = str(raw.get("observed") or raw.get("timestamp") or raw.get("date") or "").strip()
    severity = str(raw.get("severity") or "UNASSESSED").strip().upper()
    signals = raw.get("signals") or raw.get("tags") or []
    if not isinstance(signals, list):
        signals = [str(signals)]
    identity = "\n".join((source, url or title, observed, ticker))
    return {
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_file": str(path), "source": source, "ticker": ticker,
        "title": title, "url": url, "observed": observed,
        "severity": severity, "signals": [str(s) for s in signals],
        "confidence": raw.get("confidence"),
    }


def main() -> int:
    default_root = Path("/storage/emulated/0/RootBase")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root if default_root.is_dir() else Path.cwd())
    parser.add_argument("--input", type=Path, action="append", default=[], help="JSON fixture path; repeatable")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Root directory does not exist: {root}")
    output = (args.output.expanduser().resolve() if args.output else root / "data" / "scout")
    output.mkdir(parents=True, exist_ok=True)
    sources = find_inputs(root, [p.expanduser() for p in args.input])
    findings = [normalize(p, item) for p in sources for item in records_from(p)]
    now = datetime.now(timezone.utc).isoformat()
    db_path = output / "scout_ledger.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, source_file TEXT NOT NULL, source TEXT NOT NULL, ticker TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, observed TEXT NOT NULL, severity TEXT NOT NULL, signals_json TEXT NOT NULL, confidence TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY, ran_at TEXT NOT NULL, root TEXT NOT NULL, files INTEGER NOT NULL, findings INTEGER NOT NULL)")
        inserted = 0
        for row in findings:
            before = db.total_changes
            db.execute("INSERT OR IGNORE INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (row["id"], now, row["source_file"], row["source"], row["ticker"], row["title"], row["url"], row["observed"], row["severity"], json.dumps(row["signals"], ensure_ascii=False), None if row["confidence"] is None else str(row["confidence"])))
            inserted += db.total_changes - before
        db.execute("INSERT INTO runs (ran_at, root, files, findings) VALUES (?, ?, ?, ?)", (now, str(root), len(sources), len(findings)))
    report = {
        "generated_at": now, "root": str(root), "mode": "offline-local-files",
        "files_scanned": [str(p) for p in sources], "records_seen": len(findings),
        "new_records": inserted,
        "note": "Collected source records only. No live fetch, prediction, accuracy claim, or investment advice.",
        "findings": findings,
    }
    report_path = output / "latest_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Scanned {len(sources)} JSON files; found {len(findings)} records ({inserted} new).")
    print(f"Report: {report_path}\nLedger: {db_path}")
    if not sources:
        print("No known fixture files found. Try --input /path/to/market_signals.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
