#!/usr/bin/env python3
"""
core_framework/adapters/live_sources.py

Live ingestion sources — network-gated by construction.

Every source here implements the same `TrendSource` contract used offline by
`tools/ingest/trend_scraper.py` (``.name`` + ``.fetch(limit) -> list[TrendItem]``),
so `IngestAdapter.collect()` consumes live and offline sources identically.

Safety contract:
  * ``allow_network`` defaults to **False**. A source that is not explicitly
    unlocked raises ``LiveSourceError`` instead of touching the network, so
    tests, CI, and sandboxed agents can never accidentally make live calls.
  * Parsing (`parse_sec_edgar_hits`) is a pure function and is unit-tested
    offline. The HTTP call itself is UNVERIFIED in this environment — no live
    request was made while building it. Treat the endpoint as a starting point,
    not a guarantee.

SEC EDGAR requires a descriptive User-Agent and rate-limits to ~10 req/s; set
``SEC_USER_AGENT`` accordingly before enabling network access.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Sequence

from core_framework.adapters.ingest_adapter import TrendItem

EDGAR_FTS_URL = "https://efts.sec.gov/LATEST/search-index"
_DEFAULT_SEC_USER_AGENT = "core_framework-scout (contact: set SEC_USER_AGENT)"
DEFAULT_USER_AGENT = os.getenv("SEC_USER_AGENT", _DEFAULT_SEC_USER_AGENT)


class LiveSourceError(RuntimeError):
    """Raised when a live source is used without network authorization."""


class LiveSourceNetworkError(LiveSourceError):
    """Raised when a live request fails due to network or HTTP errors."""


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def require_sec_user_agent() -> None:
    """Raise ``LiveSourceError`` when ``SEC_USER_AGENT`` is unset or default."""
    agent = os.getenv("SEC_USER_AGENT")
    if not agent or agent == _DEFAULT_SEC_USER_AGENT:
        raise LiveSourceError(
            "SEC_USER_AGENT is not set. EDGAR requires a descriptive User-Agent. "
            "Export SEC_USER_AGENT='Your Name <your@email>' before live ingestion."
        )


def parse_sec_edgar_hits(payload: Dict[str, Any]) -> List[TrendItem]:
    """Parse an EDGAR full-text-search JSON payload into TrendItems.

    Pure and offline-testable. Expected shape (abridged)::

        {"hits": {"hits": [
            {"_id": "0000320193-26-000001:doc.htm", "_score": 12.5,
             "_source": {"display_names": ["Apple Inc."],
                         "file_date": "2026-01-01",
                         "form_type": "8-K",
                         "ciks": ["0000320193"],
                         "root_forms": ["8-K"]}}
        ]}}
    """
    if not isinstance(payload, dict):
        return []
    hits = ((payload.get("hits") or {}).get("hits")) or []
    items: List[TrendItem] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        src = hit.get("_source") or {}
        names = src.get("display_names") or []
        company = names[0] if names else "UNKNOWN"
        form = src.get("form_type") or src.get("root_form") or "filing"
        title = f"{form}: {company}"
        ciks = src.get("ciks") or []
        url = _edgar_url(hit.get("_id"), ciks[0] if ciks else None)
        items.append(
            TrendItem(
                source="sec",
                title=title,
                url=url,
                observed=str(src.get("file_date") or ""),
                score=float(hit.get("_score") or 0.0),
                tags=tuple(str(t) for t in (src.get("root_forms") or []) if t),
            )
        )
    return items


def _edgar_url(doc_id: Any, cik: Any) -> str:
    """Best-effort EDGAR archive URL from a ``_id`` of ``accession:filename``."""
    if not doc_id or not cik:
        return ""
    accession, _, filename = str(doc_id).partition(":")
    accession_nodash = accession.replace("-", "")
    cik_digits = str(_as_int(cik))
    if not filename:
        filename = f"{accession}-index.htm"
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik_digits}/"
        f"{accession_nodash}/{filename}"
    )


class HttpJsonTrendSource:
    """Generic network-gated JSON source.

    ``parser`` receives the decoded payload and returns ``list[TrendItem]``.
    """

    def __init__(
        self,
        name: str,
        url: str,
        parser: Callable[[Dict[str, Any]], List[TrendItem]],
        *,
        params: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
        allow_network: bool = False,
        timeout: float = 15.0,
    ):
        self.name = name
        self.url = url
        self.parser = parser
        self.params = params or {}
        self.headers = headers or {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        self.allow_network = allow_network
        self.timeout = timeout

    def _request_url(self) -> str:
        if not self.params:
            return self.url
        return f"{self.url}?{urllib.parse.urlencode(self.params)}"

    def fetch(self, limit: int = 20) -> List[TrendItem]:
        if not self.allow_network:
            raise LiveSourceError(
                f"source {self.name!r} is network-gated; pass allow_network=True "
                "(and set SEC_USER_AGENT for EDGAR) to enable live calls."
            )
        request = urllib.request.Request(self._request_url(), headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            raise LiveSourceNetworkError(
                f"live source {self.name!r} HTTP error: {exc.code} {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LiveSourceNetworkError(
                f"live source {self.name!r} network error: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LiveSourceNetworkError(
                f"live source {self.name!r} timed out after {self.timeout}s"
            ) from exc
        return self.parser(payload)[:limit]


class SecEdgarFullTextSource(HttpJsonTrendSource):
    """SEC EDGAR full-text search (filings medium). Network-gated.

    UNVERIFIED live: the request was never executed in this environment. The
    response parser is tested offline against a representative fixture.
    """

    def __init__(self, query: str, *, forms: Sequence[str] = ("8-K", "10-Q", "10-K"),
                 allow_network: bool = False, timeout: float = 15.0):
        params: Dict[str, Any] = {"q": f'"{query}"'}
        if forms:
            params["forms"] = ",".join(forms)
        super().__init__(
            name="sec",
            url=EDGAR_FTS_URL,
            parser=parse_sec_edgar_hits,
            params=params,
            allow_network=allow_network,
            timeout=timeout,
        )
        self.query = query
        if allow_network:
            require_sec_user_agent()
