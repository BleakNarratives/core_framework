#!/usr/bin/env python3
"""
core_framework/adapters/ingest_adapter.py

Offline-first ingestion bridge: external trend items -> scout findings.

This binds to the *existing* `tools/ingest/trend_scraper.py` contract instead of
inventing a parallel mock. A source is anything with ``.name`` and
``.fetch(limit) -> list[TrendItem]``; ``LocalJsonSource`` is the network-free
path used by tests and by anything that wants to feed pre-harvested data.

No network I/O happens here. The mapping is deterministic so the adaptive loop
can be exercised end-to-end without credentials.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_trend_scraper():
    """Reuse the canonical `tools/ingest/trend_scraper.py` scaffold.

    Prefers a normal package import, then falls back to binding the file by
    explicit path. The path fallback exists because pytest's package-import
    context can shadow the outer `tools` package name; binding the exact file
    keeps the offline ingestion contract stable regardless of how tests run.
    """
    try:
        from tools.ingest.trend_scraper import LocalJsonSource, TrendItem
        return LocalJsonSource, TrendItem
    except Exception:
        pass

    path = _REPO_ROOT / "tools" / "ingest" / "trend_scraper.py"
    if not path.exists():
        return None, None
    spec = importlib.util.spec_from_file_location("core_framework._trend_scraper", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return None, None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses looks itself up via sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.LocalJsonSource, module.TrendItem


LocalJsonSource, TrendItem = _load_trend_scraper()

# ---------------------------------------------------------------------------
# Heuristics (deterministic; no network, no model calls)
# ---------------------------------------------------------------------------
SOURCE_MEDIUM = {
    "sec": "filings",
    "sec_8k": "filings",
    "edgar": "filings",
    "filings": "filings",
    "regulatory": "filings",
    "news": "news",
    "hn": "news",
    "social": "news",
    "twitter": "news",
    "reddit": "news",
}

SCOUT_KEYWORDS = {
    "distress": ("distress", "default", "covenant", "liquidity", "solvency", "bankrupt", "layoff"),
    "regulatory": ("regulatory", "sec", "compliance", "enforcement", "fine", "probe", "subpoena"),
    "competitive": ("competitor", "rival", "market share", "displacement", "pricing war"),
    "sentiment": ("sentiment", "chatter", "backlash", "outage", "recall"),
    "opportunity": ("opportunity", "expansion", "acquisition", "partnership", "launch"),
}

_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")


def derive_medium(source_name: str) -> str:
    return SOURCE_MEDIUM.get((source_name or "").lower(), "general")


def derive_scout_type(text: str, tags: Iterable[str] = ()) -> str:
    haystack = f"{text} {' '.join(tags)}".lower()
    for scout_type, words in SCOUT_KEYWORDS.items():
        if any(w in haystack for w in words):
            return scout_type
    return "general"


def derive_severity(score: float, text: str) -> str:
    lowered = text.lower()
    if any(w in lowered for w in ("default", "covenant", "bankrupt", "enforcement")):
        return "CRITICAL"
    if score >= 80:
        return "CRITICAL"
    if score >= 50:
        return "WARNING"
    return "INFO"


def _ticker_from(title: str, tags: Iterable[str]) -> str:
    for tag in tags:
        if isinstance(tag, str) and _TICKER_RE.fullmatch(tag.strip()):
            return tag.strip()
    match = _TICKER_RE.search(title or "")
    return match.group(0) if match else "UNKNOWN"


class IngestAdapter:
    """Convert trend items into AxeScout-shaped findings."""

    def __init__(self, source_name: str, medium: str | None = None,
                 critical_score: float = 80.0, warning_score: float = 50.0):
        self.source_name = source_name
        self.medium = medium or derive_medium(source_name)
        self.critical_score = critical_score
        self.warning_score = warning_score

    def finding_from_item(self, item: Any) -> Dict[str, Any]:
        title = str(getattr(item, "title", "") or "")
        score = float(getattr(item, "score", 0.0) or 0.0)
        tags = tuple(getattr(item, "tags", ()) or ())

        ticker = _ticker_from(title, tags)
        scout_type = derive_scout_type(title, tags)
        severity = derive_severity(score, title)
        confidence = min(1.0, abs(score) / 100.0) if score else 0.5

        return {
            "ticker": ticker,
            "scout_type": scout_type,
            "severity": severity,
            "signals": [title] if title else [],
            "confidence": round(confidence, 4),
            "medium": self.medium,
            "source": self.source_name,
        }

    def findings_from_items(self, items: Iterable[Any]) -> List[Dict[str, Any]]:
        return [self.finding_from_item(i) for i in items]

    def collect(self, source: Any, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetch from a TrendSource and return findings.

        Works with the `tools.ingest.trend_scraper.TrendSource` protocol or any
        object exposing ``.fetch(limit)``.
        """
        return self.findings_from_items(source.fetch(limit))


def collect_offline(local_specs: Iterable[str], limit: int = 20) -> List[Dict[str, Any]]:
    """Convenience: build `LocalJsonSource`s from ``NAME=PATH`` specs and collect.

    Network-free by construction. Raises if the canonical scaffold is absent.
    """
    if LocalJsonSource is None:
        raise RuntimeError(
            "tools.ingest.trend_scraper is not importable; offline ingestion needs it."
        )
    findings: List[Dict[str, Any]] = []
    for spec in local_specs:
        name, _, path = spec.partition("=")
        source = LocalJsonSource(name=name or "local", path=Path(path))
        findings.extend(IngestAdapter(name or "local").collect(source, limit=limit))
    return findings


# ---------------------------------------------------------------------------
# Market signal adapter (fixture-backed, offline-safe)
# ---------------------------------------------------------------------------
class MarketSignal:
    """Lightweight representation of an incoming market signal."""

    def __init__(self, ticker: str, scout_type: str, severity: str,
                 summary: str = "", signals: Iterable[str] | None = None,
                 confidence: float = 0.5, timestamp: str = ""):
        self.ticker = ticker
        self.scout_type = scout_type
        self.severity = severity
        self.summary = summary
        self.signals = list(signals or [])
        self.confidence = max(0.0, min(1.0, float(confidence or 0.5)))
        self.timestamp = timestamp


def _coerce_market_signal(item: Any) -> MarketSignal:
    if isinstance(item, MarketSignal):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"market signal must be a dict, got {type(item).__name__}")
    return MarketSignal(
        ticker=str(item.get("ticker", "UNKNOWN") or "UNKNOWN"),
        scout_type=str(item.get("scout_type", "general") or "general"),
        severity=str(item.get("severity", "INFO") or "INFO"),
        summary=str(item.get("summary", "") or ""),
        signals=item.get("signals") or [],
        confidence=float(item.get("confidence", 0.5) or 0.5),
        timestamp=str(item.get("timestamp", "") or ""),
    )


class MarketSignalAdapter:
    """Convert raw market signal payloads into AxeScout-shaped findings.

    Network-free. Works with any iterable of ``MarketSignal`` objects or
    ``dict``s with the same field names.
    """

    def __init__(self, source_name: str = "market_signals", medium: str = "general"):
        self.source_name = source_name
        self.medium = medium

    def finding_from_signal(self, signal: Any) -> Dict[str, Any]:
        signal = _coerce_market_signal(signal)
        severity = derive_severity(
            signal.confidence * 100.0,
            " ".join([signal.summary, *signal.signals]),
        )
        return {
            "ticker": signal.ticker,
            "scout_type": signal.scout_type,
            "severity": severity,
            "signals": [signal.summary] if signal.summary else signal.signals[:1],
            "confidence": round(signal.confidence, 4),
            "medium": self.medium,
            "source": self.source_name,
        }

    def findings_from_signals(self, signals: Iterable[Any]) -> List[Dict[str, Any]]:
        return [self.finding_from_signal(s) for s in signals]

    def collect(self, signals: Iterable[Any], limit: int = 20) -> List[Dict[str, Any]]:
        findings = self.findings_from_signals(signals)
        return findings[:limit]


def load_market_signals(path: str | Path) -> List[MarketSignal]:
    """Load ``market_signals.json``-style fixtures from ``path``."""
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise TypeError("market signal fixture must be a JSON array")
    return [_coerce_market_signal(item) for item in payload]
