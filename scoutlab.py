#!/usr/bin/env python3
"""ScoutLab: a private, offline scout that learns what *you* find useful.

Python standard library only. No network, APIs, paid model, or code self-editing.
The learner ranks source records for relevance to your goal from your feedback;
it does not claim to predict markets or real-world outcomes.

Quick start (from your project directory):
  python scoutlab.py init
  python scoutlab.py goal "find early signs of company financial distress"
  python scoutlab.py scan
  python scoutlab.py rate FINDING_ID yes   # or: no
  python scoutlab.py report
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(".scoutlab")
DEFAULT_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "cache", "dist", "build"}
JSON_NAMES = {"market_signals.json", "sec_filings.json", "news_feed.json"}
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{1,30}")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def words(text: str) -> list[str]:
    return [w.lower() for w in TOKEN_RE.findall(text)]


def app_paths(root: Path) -> tuple[Path, Path, Path]:
    home = root / APP_DIR
    return home, home / "config.json", home / "scoutlab.sqlite3"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS findings (
        id TEXT PRIMARY KEY, source_file TEXT NOT NULL, source TEXT NOT NULL,
        title TEXT NOT NULL, url TEXT NOT NULL, observed TEXT NOT NULL,
        severity TEXT NOT NULL, body TEXT NOT NULL, first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY, finding_id TEXT NOT NULL, relevant INTEGER NOT NULL,
        rated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS weights (
        feature TEXT PRIMARY KEY, value REAL NOT NULL
      );
    """)
    return db


def load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {"goal": "", "terms": [], "scan_dirs": ["."]}


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def iter_inputs(root: Path, configured_dirs: list[str], explicit: list[str]) -> list[Path]:
    found: set[Path] = set()
    for raw in explicit:
        p = Path(raw).expanduser()
        p = (root / p).resolve() if not p.is_absolute() else p.resolve()
        if p.is_file() and p.suffix.lower() == ".json":
            found.add(p)
    for raw in configured_dirs:
        base = Path(raw).expanduser()
        base = (root / base).resolve() if not base.is_absolute() else base.resolve()
        if not base.is_dir():
            continue
        for path in base.rglob("*.json"):
            try:
                relative = path.relative_to(base)
            except ValueError:
                continue
            if any(part in DEFAULT_SKIP for part in relative.parts):
                continue
            if len(relative.parts) > 5:
                continue
            if path.name in JSON_NAMES or path.name.endswith(("_signals.json", "_feed.json", "_filings.json")):
                found.add(path.resolve())
    return sorted(found)


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = next((payload.get(k) for k in ("signals", "targets", "items", "filings", "results") if isinstance(payload.get(k), list)), [])
    else:
        candidates = []
    return [x for x in candidates if isinstance(x, dict)]


def normalize(path: Path, item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("title") or item.get("summary") or item.get("name") or "Untitled").strip()
    body_value = item.get("body") or item.get("content") or item.get("description") or ""
    signals = item.get("signals") or item.get("tags") or []
    if not isinstance(signals, list):
        signals = [signals]
    body = " ".join([str(body_value), *(str(s) for s in signals)]).strip()
    url = str(item.get("url") or item.get("link") or "").strip()
    observed = str(item.get("observed") or item.get("timestamp") or item.get("date") or "").strip()
    source = str(item.get("source") or path.stem.removesuffix("_feed") or path.stem).strip()
    severity = str(item.get("severity") or "UNASSESSED").strip().upper()
    identity = "\n".join((source, url or title, observed, body))
    return {"id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
            "source_file": str(path), "source": source, "title": title, "url": url,
            "observed": observed, "severity": severity, "body": body}


def feature_vector(row: dict[str, Any], terms: list[str]) -> dict[str, float]:
    text = f"{row['title']} {row['body']} {row['source']} {row['severity']}".lower()
    tokens = set(words(text))
    features = {"bias": 1.0}
    for token in tokens:
        features[f"word:{token}"] = 1.0
    for term in terms:
        clean = " ".join(words(term))
        if clean and clean in text:
            features[f"goal:{clean}"] = 1.0
    if row["severity"] in {"CRITICAL", "HIGH", "WARNING"}:
        features["severity:flagged"] = 1.0
    return features


def sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def score(db: sqlite3.Connection, row: dict[str, Any], terms: list[str]) -> float:
    vector = feature_vector(row, terms)
    weights = {r["feature"]: float(r["value"]) for r in db.execute("SELECT feature, value FROM weights")}
    # Transparent cold-start ranking: goal matches matter before feedback exists.
    raw = -1.25
    for feature, value in vector.items():
        if feature.startswith("goal:"):
            raw += 1.4 * value
        elif feature.startswith("word:") and feature[5:] in {w for t in terms for w in words(t)}:
            raw += 0.45 * value
        raw += weights.get(feature, 0.0) * value
    return sigmoid(raw)


def scan(root: Path, paths: list[Path], db: sqlite3.Connection, terms: list[str]) -> int:
    now = utcnow()
    count = 0
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"Skip {path}: {exc}", file=sys.stderr)
            continue
        for item in extract_items(payload):
            row = normalize(path, item)
            db.execute("""INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,
              source_file=excluded.source_file, title=excluded.title,
              url=excluded.url, observed=excluded.observed, severity=excluded.severity,
              body=excluded.body""",
              (row["id"], row["source_file"], row["source"], row["title"], row["url"],
               row["observed"], row["severity"], row["body"], now, now))
            count += 1
    db.commit()
    print(f"Scanned {len(paths)} files; indexed {count} records. Database: {db_path_display(root)}")
    show_report(db, terms, limit=15)
    return count


def db_path_display(root: Path) -> str:
    return str(root / APP_DIR / "scoutlab.sqlite3")


def show_report(db: sqlite3.Connection, terms: list[str], limit: int = 20) -> None:
    rows = [dict(r) for r in db.execute("SELECT * FROM findings ORDER BY last_seen DESC")]
    ranked = sorted(((score(db, row, terms), row) for row in rows), key=lambda x: x[0], reverse=True)[:limit]
    if not ranked:
        print("No findings yet. Add JSON inputs and run: python scoutlab.py scan")
        return
    print("\nTOP MATCHES (relevance ranking, not prediction confidence)")
    for probability, row in ranked:
        print(f"{probability:5.0%}  id={row['id']}  [{row['severity']}] {row['title']}")
        print(f"      {row['source']} | {row['observed'] or 'date unknown'} | {row['url'] or row['source_file']}")
    print("Rate a result to personalize ranking: python scoutlab.py rate ID yes|no")


def train_feedback(db: sqlite3.Connection, row: dict[str, Any], terms: list[str], label: int) -> None:
    vector = feature_vector(row, terms)
    weights = {r["feature"]: float(r["value"]) for r in db.execute("SELECT feature, value FROM weights")}
    probability = sigmoid(sum(weights.get(k, 0.0) * v for k, v in vector.items()))
    # One conservative online logistic-regression update per explicit user rating.
    rate = 0.18
    error = label - probability
    for feature, value in vector.items():
        updated = weights.get(feature, 0.0) + rate * (error * value - 0.002 * weights.get(feature, 0.0))
        db.execute("INSERT INTO weights(feature,value) VALUES(?,?) ON CONFLICT(feature) DO UPDATE SET value=excluded.value", (feature, updated))
    db.execute("INSERT INTO feedback(finding_id,relevant,rated_at) VALUES(?,?,?)", (row["id"], label, utcnow()))
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline, user-trainable scout ranking tool")
    parser.add_argument("command", choices=("init", "goal", "scan", "rate", "report", "stats"))
    parser.add_argument("args", nargs="*")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project directory; default is current directory")
    parser.add_argument("--input", action="append", default=[], help="JSON path, repeatable; for scan")
    ns = parser.parse_args()
    root = ns.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")
    home, config_path, db_path = app_paths(root)
    home.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    db = connect(db_path)
    try:
        if ns.command == "init":
            save_config(config_path, config)
            print(f"Ready. Private state: {home}\nNext: python scoutlab.py goal \"your scouting goal\"")
        elif ns.command == "goal":
            goal = " ".join(ns.args).strip()
            if not goal:
                parser.error('goal needs text, e.g. goal "find local grant opportunities"')
            config["goal"] = goal
            config["terms"] = list(dict.fromkeys(words(goal)))
            save_config(config_path, config)
            print(f"Goal saved: {goal}\nTerms: {', '.join(config['terms'])}")
        elif ns.command == "scan":
            paths = iter_inputs(root, config.get("scan_dirs", ["."]), ns.input)
            scan(root, paths, db, config.get("terms", []))
        elif ns.command == "rate":
            if len(ns.args) != 2 or ns.args[1].lower() not in {"yes", "no"}:
                parser.error("rate requires FINDING_ID yes|no")
            record = db.execute("SELECT * FROM findings WHERE id=?", (ns.args[0],)).fetchone()
            if not record:
                parser.error(f"unknown finding id: {ns.args[0]}; run scan/report and copy its id")
            train_feedback(db, dict(record), config.get("terms", []), int(ns.args[1].lower() == "yes"))
            print("Feedback saved. Future rankings are personalized to your ratings; this does not train a market predictor.")
        elif ns.command == "report":
            show_report(db, config.get("terms", []), 30)
        elif ns.command == "stats":
            total = db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            rated = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            print(f"findings={total} ratings={rated} goal={config.get('goal') or '(not set)'}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
