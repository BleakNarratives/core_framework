"""Public metadata adapters for Foxwood Research Ledger.

Adapters return bounded bibliographic evidence only. They do not generate
claims, execute response content, or import the foreign ScholarScout project.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .ledger import ResearchLedger, SourceRecord

DEFAULT_TIMEOUT_SECONDS = 12


@dataclass(frozen=True)
class SearchCandidate:
    provider: str
    title: str
    url: str
    publisher: str
    excerpt: str
    license_note: str = "metadata license; verify before redistribution"


class MetadataAdapter:
    provider = "metadata"

    def __init__(self, fetch_json: Optional[Callable[[str], dict]] = None):
        self._fetch_json = fetch_json or self._fetch

    def search(self, query: str, limit: int = 5) -> list[SearchCandidate]:
        raise NotImplementedError

    @staticmethod
    def _fetch(url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "Foxwood-Research/0.1"},
        )
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            return json.loads(response.read(1_000_000).decode("utf-8"))

    @staticmethod
    def _limit(limit: int) -> int:
        return max(1, min(25, int(limit)))

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()


class OpenAlexAdapter(MetadataAdapter):
    """Search OpenAlex works using public bibliographic metadata."""

    provider = "openalex"
    endpoint = "https://api.openalex.org/works"

    def search(self, query: str, limit: int = 5) -> list[SearchCandidate]:
        params = urllib.parse.urlencode({"search": query, "per-page": self._limit(limit)})
        payload = self._fetch_json(f"{self.endpoint}?{params}")
        candidates: list[SearchCandidate] = []
        for item in payload.get("results", [])[: self._limit(limit)]:
            title = self._text(item.get("title"))
            url = self._text(item.get("doi")) or self._text(item.get("id"))
            if not title or not url:
                continue
            publication = item.get("publication_year") or "year unavailable"
            cited = item.get("cited_by_count", 0)
            authors = [self._text(a.get("author", {}).get("display_name")) for a in item.get("authorships", [])[:3]]
            author_text = ", ".join(a for a in authors if a) or "authors unavailable"
            excerpt = f"Title: {title}. Authors: {author_text}. Publication year: {publication}. Cited by: {cited}."
            candidates.append(SearchCandidate(self.provider, title, url, "OpenAlex", excerpt))
        return candidates


class CrossrefAdapter(MetadataAdapter):
    """Search Crossref works using public DOI metadata."""

    provider = "crossref"
    endpoint = "https://api.crossref.org/works"

    def search(self, query: str, limit: int = 5) -> list[SearchCandidate]:
        params = urllib.parse.urlencode({"query": query, "rows": self._limit(limit)})
        payload = self._fetch_json(f"{self.endpoint}?{params}")
        candidates: list[SearchCandidate] = []
        for item in payload.get("message", {}).get("items", [])[: self._limit(limit)]:
            title_values = item.get("title") or []
            title = self._text(title_values[0] if title_values else "")
            doi = self._text(item.get("DOI"))
            if not title or not doi:
                continue
            url = f"https://doi.org/{doi}"
            publisher = self._text(item.get("publisher")) or "Crossref"
            date_parts = (item.get("published-print") or item.get("published-online") or {}).get("date-parts", [])
            year = date_parts[0][0] if date_parts and date_parts[0] else "year unavailable"
            excerpt = f"Title: {title}. Publisher: {publisher}. Publication year: {year}. DOI: {doi}."
            candidates.append(SearchCandidate(self.provider, title, url, publisher, excerpt))
        return candidates


def discover(
    query: str,
    ledger: ResearchLedger,
    adapters: Iterable[MetadataAdapter],
    limit: int = 5,
) -> list[SourceRecord]:
    """Search adapters and persist deduplicated candidates as source records."""
    seen_urls: set[str] = set()
    records: list[SourceRecord] = []
    for adapter in adapters:
        for candidate in adapter.search(query, limit=limit):
            normalized_url = candidate.url.rstrip("/").lower()
            if normalized_url in seen_urls:
                continue
            seen_urls.add(normalized_url)
            records.append(
                ledger.add_source(
                    title=candidate.title,
                    url=candidate.url,
                    publisher=candidate.publisher,
                    excerpt=candidate.excerpt,
                    license_note=candidate.license_note,
                    origin=f"adapter:{candidate.provider}",
                )
            )
    return records
