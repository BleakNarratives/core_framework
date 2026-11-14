"""Offline source indexing and feedback-trained relevance ranking."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

STATE_DIRNAME = ".scoutlab"
DEFAULT_DIRS = ("data", "fixtures", "chronoscouts", "ChronoScouts", "Kronos-Scouts", "core_framework")
SKIP_DIRS = {".git", ".scoutlab", ".venv", "venv", "node_modules", "__pycache__", "cache", "dist", "build"}
SIGNAL_NAMES = {"market_signals.json", "sec_filings.json", "news_feed.json"}
SIGNAL_SUFFIXES = ("_signals.json", "_feed.json", "_filings.json")
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{1,39}")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> list[str]:
    return [word.lower() for word in TOKEN_RE.findall(text or "")]


def choose_default_root() -> Path:
    android_root = Path("/storage/emulated/0/RootBase")
    return android_root if android_root.is_dir() else Path.cwd()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS findings (
        id TEXT PRIMARY KEY, source_file TEXT NOT NULL, source TEXT NOT NULL,
        title TEXT NOT NULL, url TEXT NOT NULL, observed TEXT NOT NULL,
        severity TEXT NOT NULL, body TEXT NOT NULL, raw_json TEXT NOT NULL,
        first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id TEXT NOT NULL,
        relevant INTEGER NOT NULL CHECK(relevant IN (0,1)), rated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS weights (
        feature TEXT PRIMARY KEY, value REAL NOT NULL
      );
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT NOT NULL,
        files INTEGER NOT NULL, records INTEGER NOT NULL, new_records INTEGER NOT NULL
      );
    """)
    return db


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = next((payload.get(key) for key in ("signals", "targets", "items", "filings", "results") if isinstance(payload.get(key), list)), [])
    else:
        values = []
    return [value for value in values if isinstance(value, dict)]


def _normalize(path: Path, item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("title") or item.get("summary") or item.get("name") or "Untitled signal").strip()
    url = str(item.get("url") or item.get("link") or "").strip()
    observed = str(item.get("observed") or item.get("timestamp") or item.get("date") or "").strip()
    source = str(item.get("source") or path.stem.removesuffix("_feed") or path.stem).strip()
    severity = str(item.get("severity") or "UNASSESSED").strip().upper()
    body_value = item.get("body") or item.get("content") or item.get("description") or ""
    tags = item.get("signals") or item.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    body = " ".join([str(body_value), *(str(tag) for tag in tags)]).strip()
    stable_key = "\n".join((source.casefold(), url.casefold() or title.casefold(), observed, body.casefold()))
    return {"id": hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:16],
            "source_file": str(path), "source": source, "title": title, "url": url,
            "observed": observed, "severity": severity, "body": body,
            "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True)}


class ScoutLab:
    """Index local signal records and learn a personal relevance ranking."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        self.state_dir = self.root / STATE_DIRNAME
        self.config_path = self.state_dir / "config.json"
        self.db_path = self.state_dir / "scoutlab.sqlite3"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db = _connect(self.db_path)
        self.config = self._load_config()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "ScoutLab":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _load_config(self) -> dict[str, Any]:
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("goal", "")
                value.setdefault("terms", [])
                return value
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        return {"goal": "", "terms": []}

    def _save_config(self) -> None:
        self.config_path.write_text(json.dumps(self.config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def initialize(self) -> None:
        self.db.commit()
        self._save_config()

    def set_goal(self, goal: str) -> list[str]:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal cannot be empty")
        self.config["goal"] = goal
        self.config["terms"] = list(dict.fromkeys(tokenize(goal)))
        self._save_config()
        return self.config["terms"]

    def _input_paths(self, directories: Iterable[str], explicit: Iterable[str]) -> list[Path]:
        paths: set[Path] = set()
        for raw in explicit:
            candidate = Path(raw).expanduser()
            candidate = (self.root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            if candidate.is_file() and candidate.suffix.lower() == ".json":
                paths.add(candidate)
        for raw in directories:
            base = Path(raw).expanduser()
            base = (self.root / base).resolve() if not base.is_absolute() else base.resolve()
            if not base.is_dir():
                continue
            for current, dirs, filenames in os.walk(base):
                here = Path(current)
                depth = len(here.relative_to(base).parts)
                dirs[:] = [name for name in dirs if name not in SKIP_DIRS] if depth < 4 else []
                for name in filenames:
                    if name in SIGNAL_NAMES or name.endswith(SIGNAL_SUFFIXES):
                        paths.add((here / name).resolve())
        return sorted(paths)

    def scan(self, directories: Iterable[str] = DEFAULT_DIRS, explicit: Iterable[str] = (), per_file_limit: int = 20) -> tuple[int, list[Path]]:
        if per_file_limit < 1:
            raise ValueError("per_file_limit must be positive")
        paths = self._input_paths(directories, explicit)
        now = now_utc()
        seen = new = 0
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                print(f"Skipping unreadable JSON {path}: {exc}")
                continue
            for item in _items(payload)[:per_file_limit]:
                row = _normalize(path, item)
                existed = self.db.execute("SELECT 1 FROM findings WHERE id=?", (row["id"],)).fetchone() is not None
                self.db.execute("""INSERT INTO findings
                  (id,source_file,source,title,url,observed,severity,body,raw_json,first_seen,last_seen)
                  VALUES (:id,:source_file,:source,:title,:url,:observed,:severity,:body,:raw_json,:now,:now)
                  ON CONFLICT(id) DO UPDATE SET source_file=excluded.source_file,
                  title=excluded.title,url=excluded.url,observed=excluded.observed,
                  severity=excluded.severity,body=excluded.body,raw_json=excluded.raw_json,
                  last_seen=excluded.last_seen""", {**row, "now": now})
                seen += 1
                new += int(not existed)
        self.db.execute("INSERT INTO runs(ran_at,files,records,new_records) VALUES(?,?,?,?)", (now, len(paths), seen, new))
        self.db.commit()
        return seen, paths

    def _vector(self, row: dict[str, Any]) -> dict[str, float]:
        text = f"{row['title']} {row['body']} {row['source']} {row['severity']}".lower()
        vector = {f"word:{word}": 1.0 for word in set(tokenize(text))}
        vector["bias"] = 1.0
        for term in self.config.get("terms", []):
            if term and term in text:
                vector[f"goal:{term}"] = 1.0
        if row["severity"] in {"CRITICAL", "HIGH", "WARNING"}:
            vector["severity:flagged"] = 1.0
        return vector

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value))))

    def relevance(self, row: dict[str, Any]) -> float:
        weights = {record["feature"]: record["value"] for record in self.db.execute("SELECT feature,value FROM weights")}
        vector = self._vector(row)
        # Goal match is an explicit cold-start prior; feedback learns additional
        # word associations. This score is relevance, never prediction certainty.
        value = -1.1 + sum(weights.get(key, 0.0) * amount for key, amount in vector.items())
        value += 1.25 * sum(amount for key, amount in vector.items() if key.startswith("goal:"))
        goal_words = set(self.config.get("terms", []))
        value += 0.35 * sum(amount for key, amount in vector.items() if key.startswith("word:") and key[5:] in goal_words)
        return self._sigmoid(value)

    def ranked(self, limit: int = 20) -> list[tuple[float, dict[str, Any]]]:
        records = [dict(row) for row in self.db.execute("SELECT * FROM findings")]
        return sorted(((self.relevance(record), record) for record in records), key=lambda pair: (-pair[0], pair[1]["observed"], pair[1]["id"]))[:limit]

    def rate(self, finding_id: str, relevant: bool, learning_rate: float = 0.2) -> None:
        record = self.db.execute("SELECT * FROM findings WHERE id=?", (finding_id,)).fetchone()
        if record is None:
            raise ValueError(f"unknown finding id: {finding_id}")
        row = dict(record)
        vector = self._vector(row)
        weights = {r["feature"]: float(r["value"]) for r in self.db.execute("SELECT feature,value FROM weights")}
        prediction = self._sigmoid(sum(weights.get(key, 0.0) * amount for key, amount in vector.items()))
        error = int(relevant) - prediction
        for key, amount in vector.items():
            old = weights.get(key, 0.0)
            updated = old + learning_rate * (error * amount - 0.002 * old)
            self.db.execute("INSERT INTO weights(feature,value) VALUES(?,?) ON CONFLICT(feature) DO UPDATE SET value=excluded.value", (key, updated))
        self.db.execute("INSERT INTO feedback(finding_id,relevant,rated_at) VALUES(?,?,?)", (finding_id, int(relevant), now_utc()))
        self.db.commit()

    def write_report(self, limit: int = 100) -> Path:
        ranked = self.ranked(limit)
        report = {"generated_at": now_utc(), "goal": self.config.get("goal", ""),
                  "mode": "offline-local-data", "score_meaning": "personal relevance ranking, not predictive confidence",
                  "count": len(ranked), "findings": [{**row, "relevance": round(value, 6), "raw": json.loads(row.pop("raw_json"))} for value, row in ranked]}
        path = self.state_dir / "latest_report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def print_report(self, limit: int = 20) -> None:
        ranked = self.ranked(limit)
        if not ranked:
            print("No local findings indexed yet. Run: python -m scoutlab scan")
            return
        print("Ranked for your goal (relevance only; not a prediction):")
        for value, row in ranked:
            source_ref = row["url"] or row["source_file"]
            print(f"{value:5.0%}  id={row['id']}  [{row['severity']}] {row['title']}")
            print(f"       {row['source']} | {row['observed'] or 'date unknown'} | {source_ref}")

    def stats(self) -> dict[str, Any]:
        findings = self.db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        ratings = self.db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        runs = self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        return {"root": str(self.root), "goal": self.config.get("goal", ""), "findings": findings, "ratings": ratings, "runs": runs, "state_dir": str(self.state_dir)}
