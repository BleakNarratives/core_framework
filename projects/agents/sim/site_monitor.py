"""Polite local monitor for public agent and AI-tool discovery pages.

Stores compact listing metadata only. The monitor follows robots.txt, limits
request frequency and work per run, backs off on rate limits, and never trains a
model or executes content found on monitored pages.
"""
from __future__ import annotations

import argparse
import email.utils
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable


USER_AGENT = "TideglassScout/0.1 (local public listing monitor)"
MAX_RESPONSE_BYTES = 2_000_000
MAX_STATE_BYTES = 32_000_000
MAX_ITEMS_PER_SOURCE = 20_000
MAX_PAGES_PER_RUN = 30
MAX_TITLE_CHARS = 300
MAX_SUMMARY_CHARS = 1_000
MAX_RESPONSE_HEADERS = 32
DEFAULT_BACKOFF_SECONDS = 3_600
MAX_BACKOFF_SECONDS = 86_400
MAX_EVENT_HISTORY = 10_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _report_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _markdown_escape(value: str) -> str:
    value = html.escape(value, quote=False)
    special = set("\\`*_{}[]()#+-.!|>")
    return "".join("\\" + char if char in special else char for char in value)


def _trend_category(source: str, url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    first_path_segment = parts.path.strip("/").split("/", 1)[0].lower()
    categories = {
        "agent": "Agents",
        "prompt": "Prompts",
        "tool": "Tools",
        "bundle": "Bundles",
        "ai": "AI tools",
        "gpt": "GPTs",
        "mcp": "MCP tools",
        "model": "Models",
        "robot": "Robotics",
    }
    category = categories.get(first_path_segment)
    if category:
        return category
    return "AI tools" if source == "theresanaiforthat" else "Other"


def daily_trend_report(state_path: str | Path, day: str | None = None) -> str:
    """Summarize recorded new-listing events for a UTC calendar day."""
    if day is not None and (not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)):
        raise ValueError("report date must use YYYY-MM-DD")
    try:
        report_day = date.fromisoformat(day) if day else datetime.now(timezone.utc).date()
    except (TypeError, ValueError) as exc:
        raise ValueError("report date must use YYYY-MM-DD") from exc
    state = _load_state(Path(state_path))
    events = state.get("events", [])
    if not isinstance(events, list):
        raise ValueError("monitor event history has an invalid shape")

    discoveries = []
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "new":
            continue
        try:
            observed_day = _parse_time(event.get("observed_at")).date()
        except (TypeError, ValueError):
            continue
        if observed_day != report_day:
            continue
        source = _report_text(event.get("site", "unknown source"), 80) or "unknown source"
        url = _report_text(event.get("url", ""), 500)
        title = _report_text(event.get("title", ""), MAX_TITLE_CHARS)
        discoveries.append({
            "source": source,
            "url": url,
            "title": title or url or "Untitled listing",
            "category": _trend_category(source, url),
        })

    lines = [f"Daily AI discovery trends — {report_day.isoformat()} UTC", f"New listings recorded: {len(discoveries)}"]
    if not discoveries:
        lines.extend(("Categories: none recorded", "Examples: none"))
    else:
        source_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for item in discoveries:
            source_counts[item["source"]] = source_counts.get(item["source"], 0) + 1
            category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
        source_summary = ", ".join(
            f"{name} {count}" for name, count in sorted(source_counts.items())
        )
        category_summary = ", ".join(
            f"{name} {count}"
            for name, count in sorted(category_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        lines.extend((f"Sources: {source_summary}", f"Categories: {category_summary}", "Examples:"))
        for item in discoveries[:5]:
            example = (
                f"- [{_markdown_escape(item['source'])} / "
                f"{_markdown_escape(item['category'])}] "
                f"{_markdown_escape(item['title'])}"
            )
            if item["url"]:
                example += f" — {_markdown_escape(item['url'])}"
            lines.append(example)
        if len(discoveries) > 5:
            lines.append(f"- … and {len(discoveries) - 5} more")
    lines.append("Unverified listing metadata; categories are inferred from URL paths.")
    return "\n".join(lines)


def _normalize_url(url: str, allowed_host: str) -> str | None:
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme.lower() != "https"
        or host != allowed_host
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
    ):
        return None
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(("https", host, path, parts.query, ""))


def _retry_until(retry_after: str | None, now: datetime) -> str:
    delay = DEFAULT_BACKOFF_SECONDS
    if retry_after:
        try:
            delay = int(retry_after.strip())
        except ValueError:
            try:
                date = email.utils.parsedate_to_datetime(retry_after)
                if date.tzinfo is None:
                    date = date.replace(tzinfo=timezone.utc)
                delay = max(0, int((date.astimezone(timezone.utc) - now).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                delay = DEFAULT_BACKOFF_SECONDS
    delay = min(max(delay, 60), MAX_BACKOFF_SECONDS)
    return (now + timedelta(seconds=delay)).isoformat()


@dataclass(frozen=True)
class SiteSource:
    name: str
    base_url: str
    seed_urls: tuple[str, ...]
    item_path_prefixes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("site source name must not be blank")
        if not isinstance(self.base_url, str):
            raise ValueError("site source base_url must be a string")
        base = urllib.parse.urlsplit(self.base_url)
        if base.scheme != "https" or not base.hostname:
            raise ValueError("site source must have an HTTPS base URL")
        if base.path not in ("", "/") or base.query or base.fragment:
            raise ValueError("site source base URL must be an origin, not a path or query")
        host = base.hostname.lower().rstrip(".")
        if _normalize_url(self.base_url, host) is None:
            raise ValueError("site source base URL must be an HTTPS origin URL")
        if not self.seed_urls or any(_normalize_url(url, host) is None for url in self.seed_urls):
            raise ValueError("site seeds must be HTTPS URLs on the base host")
        if not self.item_path_prefixes or any(
            not isinstance(prefix, str) or not prefix.startswith("/")
            for prefix in self.item_path_prefixes
        ):
            raise ValueError("item path prefixes must be absolute paths")

    @property
    def host(self) -> str:
        hostname = urllib.parse.urlsplit(self.base_url).hostname
        assert hostname is not None
        return hostname.lower().rstrip(".")

    def is_item_url(self, url: str) -> bool:
        normalized = _normalize_url(url, self.host)
        if normalized is None:
            return False
        path = urllib.parse.urlsplit(normalized).path
        return any(
            path.startswith(prefix) and path != prefix.rstrip("/")
            for prefix in self.item_path_prefixes
        )


DEFAULT_SOURCES = (
    SiteSource(
        name="swarms-world",
        base_url="https://swarms.world/",
        seed_urls=(
            "https://swarms.world/",
            "https://swarms.world/?category=agents",
            "https://swarms.world/?category=prompts",
            "https://swarms.world/?category=tools",
            "https://swarms.world/?category=bundles",
        ),
        item_path_prefixes=("/agent/", "/prompt/", "/tool/", "/bundle/"),
    ),
    SiteSource(
        name="theresanaiforthat",
        base_url="https://theresanaiforthat.com/",
        seed_urls=("https://theresanaiforthat.com/just-released/",),
        item_path_prefixes=("/ai/", "/gpt/", "/mcp/", "/model/", "/robot/"),
    ),
)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Listing:
    url: str
    title: str
    summary: str


@dataclass(frozen=True)
class SiteChange:
    site: str
    status: str
    url: str
    title: str
    summary: str
    observed_at: str
    content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "status": self.status,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "observed_at": self.observed_at,
            "content_sha256": self.content_sha256,
            "verified": False,
        }


class _PageParser(HTMLParser):
    def __init__(self, source: SiteSource, page_url: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.page_url = page_url
        self.anchors: list[tuple[str, str]] = []
        self.pagination_urls: list[str] = []
        self.description = ""
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    @staticmethod
    def _clean(text: str, limit: int) -> str:
        return re.sub(r"\s+", " ", text).strip()[:limit]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag.lower() == "a":
            self._anchor_href = attrs_dict.get("href")
            self._anchor_parts = []
        elif tag.lower() == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.description = self._clean(attrs_dict.get("content") or "", MAX_SUMMARY_CHARS)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._anchor_href:
            return
        href = urllib.parse.urljoin(self.page_url, self._anchor_href)
        normalized = _normalize_url(href, self.source.host)
        text = self._clean(" ".join(self._anchor_parts), MAX_TITLE_CHARS)
        if normalized and self.source.is_item_url(normalized) and text:
            if len(self.anchors) < MAX_ITEMS_PER_SOURCE:
                self.anchors.append((normalized, text))
        elif normalized and self._is_pagination(normalized):
            if len(self.pagination_urls) < MAX_PAGES_PER_RUN:
                self.pagination_urls.append(normalized)
        self._anchor_href = None
        self._anchor_parts = []

    def _is_pagination(self, url: str) -> bool:
        current = urllib.parse.urlsplit(self.page_url)
        candidate = urllib.parse.urlsplit(url)
        if current.path.rstrip("/") != candidate.path.rstrip("/"):
            return False
        params = urllib.parse.parse_qs(candidate.query)
        page_values = params.get("page", []) + params.get("p", [])
        return any(value.isdigit() and int(value) > 1 for value in page_values)

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_parts.append(data)


def parse_listings(source: SiteSource, page_url: str, html: str) -> tuple[list[Listing], list[str]]:
    parser = _PageParser(source, page_url)
    parser.feed(html)
    listings: dict[str, Listing] = {}
    for url, title in parser.anchors:
        listings.setdefault(url, Listing(url, title, parser.description))
    return list(listings.values()), parser.pagination_urls


def parse_sitemap(body: bytes, source: SiteSource) -> tuple[list[str], list[str]]:
    """Return same-host, in-scope listing URLs and child sitemap URLs."""
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("sitemap exceeds response size limit")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError("invalid sitemap XML") from exc
    urls: list[str] = []
    children: list[str] = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
            continue
        normalized = _normalize_url(node.text.strip(), source.host)
        if not normalized:
            continue
        target = children if urllib.parse.urlsplit(normalized).path.lower().endswith(".xml") else urls
        if target is children or source.is_item_url(normalized):
            if normalized not in target and len(target) < MAX_ITEMS_PER_SOURCE:
                target.append(normalized)
    return urls, children


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _normalize_url(newurl, self.host) is None:
            raise urllib.error.HTTPError(
                newurl, code, "cross-origin redirect refused", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_fetch(
    url: str, headers: dict[str, str], timeout: float, max_bytes: int
) -> HttpResponse:
    host = urllib.parse.urlsplit(url).hostname or ""
    opener = urllib.request.build_opener(_SameOriginRedirect(host))
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html, application/xml, text/xml;q=0.9, */*;q=0.1",
            **headers,
        },
    )
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("response exceeds configured size limit")
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        if len(response_headers) > MAX_RESPONSE_HEADERS:
            response_headers = dict(list(response_headers.items())[:MAX_RESPONSE_HEADERS])
        return HttpResponse(response.status, response_headers, body)


def _new_state() -> dict[str, Any]:
    return {"version": 1, "sources": {}, "events": []}


def _load_state(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as state_file:
            raw = state_file.read(MAX_STATE_BYTES + 1)
    except FileNotFoundError:
        return _new_state()
    if len(raw) > MAX_STATE_BYTES:
        raise ValueError("monitor state exceeds size limit; refusing to overwrite it")
    try:
        state = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("monitor state is unreadable; refusing to overwrite it") from exc
    if (
        not isinstance(state, dict)
        or state.get("version") != 1
        or not isinstance(state.get("sources"), dict)
    ):
        raise ValueError("monitor state has an unsupported shape; refusing to overwrite it")
    state.setdefault("events", [])
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


class _MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.in_title = False
        self._ignored_depth = 0
        self._content_depth = 0
        self._summary_parts: list[str] = []
        self._summary_length = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer", "header", "noscript"}:
            self._ignored_depth += 1
        elif tag in {"main", "article"} and self._ignored_depth == 0:
            self._content_depth += 1
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and values.get("name", "").lower() == "description":
            self.description = values.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "nav", "footer", "header", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        elif tag in {"main", "article"} and self._ignored_depth == 0:
            self._content_depth = max(0, self._content_depth - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._content_depth and not self._ignored_depth and self._summary_length < MAX_SUMMARY_CHARS:
            cleaned = re.sub(r"\s+", " ", data).strip()
            if cleaned:
                remaining = MAX_SUMMARY_CHARS - self._summary_length
                part = cleaned[:remaining]
                self._summary_parts.append(part)
                self._summary_length += len(part) + 1

    @property
    def visible_summary(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._summary_parts)).strip()[:MAX_SUMMARY_CHARS]


def _detail_metadata(html: str) -> tuple[str, str]:
    parser = _MetadataParser()
    parser.feed(html)
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()[:MAX_TITLE_CHARS]
    summary = (
        re.sub(r"\s+", " ", parser.description).strip()
        or parser.visible_summary
    )[:MAX_SUMMARY_CHARS]
    return title, summary


class SiteMonitor:
    def __init__(
        self,
        state_path: str | Path,
        *,
        sources: tuple[SiteSource, ...] = DEFAULT_SOURCES,
        fetcher: Callable[[str, dict[str, str], float, int], HttpResponse] = _default_fetch,
        clock: Callable[[], str] = _utc_now,
        min_request_interval_seconds: float = 1.5,
        timeout_seconds: float = 15.0,
        max_pages_per_run: int = MAX_PAGES_PER_RUN,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        detail_refresh_seconds: int = 21_600,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        if not sources:
            raise ValueError("at least one source is required")
        if (
            isinstance(min_request_interval_seconds, bool)
            or not isinstance(min_request_interval_seconds, (int, float))
            or not 0.5 <= min_request_interval_seconds <= 60
        ):
            raise ValueError("request interval must be between 0.5 and 60 seconds")
        if (
            isinstance(max_pages_per_run, bool)
            or not isinstance(max_pages_per_run, int)
            or not 1 <= max_pages_per_run <= MAX_PAGES_PER_RUN
        ):
            raise ValueError(f"max_pages_per_run must be between 1 and {MAX_PAGES_PER_RUN}")
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
        ):
            raise ValueError(f"max_response_bytes must be between 1 and {MAX_RESPONSE_BYTES}")
        if (
            isinstance(detail_refresh_seconds, bool)
            or not isinstance(detail_refresh_seconds, int)
            or detail_refresh_seconds < 60
        ):
            raise ValueError("detail_refresh_seconds must be an integer of at least 60")
        self.state_path = Path(state_path)
        self.sources = sources
        self.fetcher = fetcher
        self.clock = clock
        self.min_request_interval_seconds = float(min_request_interval_seconds)
        self.timeout_seconds = timeout_seconds
        self.max_pages_per_run = max_pages_per_run
        self.max_response_bytes = max_response_bytes
        self.detail_refresh_seconds = detail_refresh_seconds
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.state = _load_state(self.state_path)
        self._last_request_at: dict[str, float] = {}
        self._host_intervals: dict[str, float] = {}
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _fetch(self, url: str, headers: dict[str, str]) -> HttpResponse:
        host = urllib.parse.urlsplit(url).hostname or ""
        previous = self._last_request_at.get(host)
        if previous is not None:
            interval = max(
                self.min_request_interval_seconds,
                self._host_intervals.get(host, self.min_request_interval_seconds),
            )
            wait = interval - (self.monotonic() - previous)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at[host] = self.monotonic()
        response = self.fetcher(url, headers, self.timeout_seconds, self.max_response_bytes)
        if len(response.body) > self.max_response_bytes:
            raise ValueError("response exceeds configured size limit")
        return response

    def _robots(self, source: SiteSource, now: datetime) -> urllib.robotparser.RobotFileParser:
        cached = self._robots_cache.get(source.name)
        if cached is not None:
            return cached
        source_state = self.state["sources"].setdefault(source.name, {})
        robots_saved = source_state.get("robots")
        if isinstance(robots_saved, dict):
            try:
                if now < _parse_time(robots_saved["expires_at"]):
                    parser = urllib.robotparser.RobotFileParser()
                    parser.set_url(urllib.parse.urljoin(source.base_url, "/robots.txt"))
                    parser.parse(robots_saved["lines"])
                    self._robots_cache[source.name] = parser
                    return parser
            except (KeyError, TypeError, ValueError):
                pass
        robots_url = urllib.parse.urljoin(source.base_url, "/robots.txt")
        response = self._fetch(robots_url, {})
        if response.status in (429, 503):
            source_state["backoff_until"] = _retry_until(response.headers.get("retry-after"), now)
            raise RuntimeError(f"robots_http_{response.status}")
        if response.status != 200:
            raise RuntimeError(f"robots_http_{response.status}")
        lines = response.body.decode("utf-8", errors="replace").splitlines()[:10_000]
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(lines)
        crawl_delay = parser.crawl_delay(USER_AGENT)
        if crawl_delay is not None:
            self._host_intervals[source.host] = min(
                max(crawl_delay, self.min_request_interval_seconds), 60.0
            )
        source_state["robots"] = {
            "fetched_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=24)).isoformat(),
            "lines": lines,
        }
        self._robots_cache[source.name] = parser
        return parser

    @staticmethod
    def _headers_for(record: dict[str, Any] | None) -> dict[str, str]:
        if not record:
            return {}
        headers = {}
        if record.get("etag"):
            headers["If-None-Match"] = record["etag"]
        if record.get("last_modified"):
            headers["If-Modified-Since"] = record["last_modified"]
        return headers

    @staticmethod
    def _safe_headers(response: HttpResponse) -> dict[str, str]:
        return {
            key.lower(): value[:1_000]
            for key, value in list(response.headers.items())[:MAX_RESPONSE_HEADERS]
            if key.lower() in {"etag", "last-modified", "retry-after", "content-type"}
        }

    def run_once(self, *, as_of: str | None = None) -> dict[str, Any]:
        observed_at = as_of or self.clock()
        now = _parse_time(observed_at)
        changes: list[SiteChange] = []
        errors: list[dict[str, str]] = []
        processed_pages = 0
        remaining_by_source: dict[str, int] = {}

        total_pages_remaining = self.max_pages_per_run
        for source_index, source in enumerate(self.sources):
            if total_pages_remaining <= 0:
                source_state = self.state["sources"].get(source.name, {})
                remaining_by_source[source.name] = len(source_state.get("pending", []))
                continue
            source_state = self.state["sources"].setdefault(
                source.name,
                {"initialized": False, "pages": {}, "items": {}, "pending": []},
            )
            backoff_until = source_state.get("backoff_until")
            if backoff_until:
                try:
                    if now < _parse_time(backoff_until):
                        errors.append({"site": source.name, "error_type": "BackoffActive", "detail": "site is in persisted rate-limit backoff"})
                        remaining_by_source[source.name] = len(source_state.get("pending", []))
                        continue
                except ValueError:
                    source_state.pop("backoff_until", None)

            pages = source_state.setdefault("pages", {})
            known_items = source_state.setdefault("items", {})
            pending_items = source_state.setdefault("pending", [])
            if not isinstance(pages, dict) or not isinstance(known_items, dict) or not isinstance(pending_items, list):
                raise ValueError(f"invalid listing state for {source.name}")
            try:
                robots = self._robots(source, now)
            except Exception as exc:
                errors.append({"site": source.name, "error_type": type(exc).__name__, "detail": str(exc)[:120]})
                remaining_by_source[source.name] = len(pending_items)
                continue

            queue: list[tuple[str, str]] = []
            queued: set[tuple[str, str]] = set()

            def enqueue(url: str, kind: str) -> None:
                normalized = _normalize_url(url, source.host)
                pair = (normalized, kind) if normalized else None
                if pair and pair not in queued:
                    queued.add(pair)
                    queue.append(pair)

            for seed in source.seed_urls:
                enqueue(seed, "seed")
            for line in source_state.get("robots", {}).get("lines", []):
                if line.strip().lower().startswith("sitemap:"):
                    enqueue(line.split(":", 1)[1].strip(), "sitemap")
            for pending in pending_items:
                if isinstance(pending, dict):
                    enqueue(pending.get("url", ""), pending.get("kind", "item"))
                elif isinstance(pending, str):
                    enqueue(pending, "item")
            source_state["pending"] = []

            due_items = []
            for url, item in known_items.items():
                if not isinstance(item, dict):
                    continue
                try:
                    due = not item.get("last_checked") or (
                        now - _parse_time(item["last_checked"])
                    ).total_seconds() >= self.detail_refresh_seconds
                except ValueError:
                    due = True
                if due:
                    due_items.append(url)
            for url in sorted(due_items):
                enqueue(url, "item")

            source_pages = 0
            rate_limited = False
            was_initialized = bool(source_state.get("initialized"))
            sources_remaining = len(self.sources) - source_index
            source_budget = min(
                total_pages_remaining,
                max(1, total_pages_remaining // sources_remaining),
            )
            while queue and source_pages < source_budget:
                url, kind = queue.pop(0)
                if not robots.can_fetch(USER_AGENT, url):
                    errors.append({"site": source.name, "error_type": "RobotsDisallowed", "detail": urllib.parse.urlsplit(url).path[:120]})
                    continue
                page_record = pages.get(url)
                try:
                    response = self._fetch(url, self._headers_for(page_record))
                    source_pages += 1
                    processed_pages += 1
                except Exception as exc:
                    errors.append({"site": source.name, "error_type": type(exc).__name__, "detail": str(exc)[:120]})
                    queue.insert(0, (url, kind))
                    break

                if response.status in (429, 503):
                    rate_limited = True
                    source_state["backoff_until"] = _retry_until(response.headers.get("retry-after"), now)
                    errors.append({"site": source.name, "error_type": f"HTTP{response.status}", "detail": "site rate limited; remaining requests deferred"})
                    queue.insert(0, (url, kind))
                    break
                if response.status == 304:
                    if page_record is not None:
                        page_record["last_checked"] = observed_at
                    if kind == "item" and url in known_items:
                        known_items[url]["last_checked"] = observed_at
                    continue
                if response.status != 200:
                    errors.append({"site": source.name, "error_type": f"HTTP{response.status}", "detail": urllib.parse.urlsplit(url).path[:120]})
                    if response.status >= 500:
                        queue.insert(0, (url, kind))
                    continue

                content_type = response.headers.get("content-type", "").lower()
                digest = hashlib.sha256(response.body).hexdigest()
                safe_headers = self._safe_headers(response)
                pages[url] = {
                    "sha256": digest,
                    "last_checked": observed_at,
                    "etag": safe_headers.get("etag"),
                    "last_modified": safe_headers.get("last-modified"),
                    "content_type": content_type[:120],
                }
                if "xml" in content_type or url.lower().endswith(".xml"):
                    try:
                        listing_urls, child_sitemaps = parse_sitemap(response.body, source)
                    except ValueError as exc:
                        errors.append({"site": source.name, "error_type": "InvalidSitemap", "detail": str(exc)[:120]})
                        continue
                    for child in child_sitemaps:
                        enqueue(child, "sitemap")
                    listings = [Listing(value, value.rsplit("/", 1)[-1], "") for value in listing_urls]
                    next_pages: list[str] = []
                elif kind == "item":
                    title, summary = _detail_metadata(response.body.decode("utf-8", errors="replace"))
                    self._update_detail(source, known_items, url, title, summary, observed_at, changes)
                    listings, next_pages = [], []
                else:
                    listings, next_pages = parse_listings(
                        source, url, response.body.decode("utf-8", errors="replace")
                    )

                if kind in {"seed", "sitemap"}:
                    for listing in listings:
                        if listing.url not in known_items and len(known_items) >= MAX_ITEMS_PER_SOURCE:
                            errors.append({"site": source.name, "error_type": "ItemLimitReached", "detail": "local metadata cap reached"})
                            break
                        previous = known_items.get(listing.url)
                        listing_hash = hashlib.sha256(
                            f"{listing.title}\n{listing.summary}".encode("utf-8")
                        ).hexdigest()
                        listing_changed = (
                            previous is None
                            or previous.get("listing_sha256") != listing_hash
                        )
                        self._observe_listing(
                            source, known_items, listing, observed_at,
                            initialized=was_initialized, changes=changes,
                        )
                        item = known_items[listing.url]
                        try:
                            detail_due = not item.get("last_checked") or (
                                now - _parse_time(item["last_checked"])
                            ).total_seconds() >= self.detail_refresh_seconds
                        except ValueError:
                            detail_due = True
                        if listing_changed or detail_due:
                            enqueue(listing.url, "item")
                    for next_page in next_pages:
                        enqueue(next_page, "seed")

            source_state["pending"] = [
                {"url": url, "kind": kind} for url, kind in queue
            ][:MAX_ITEMS_PER_SOURCE]
            if not source_state["pending"] and not rate_limited and not was_initialized:
                source_state["initialized"] = True
                for item in known_items.values():
                    if isinstance(item, dict):
                        item["baseline_pending"] = False
            remaining_by_source[source.name] = len(source_state["pending"])
            total_pages_remaining -= source_pages

        events = self.state.setdefault("events", [])
        if not isinstance(events, list):
            raise ValueError("monitor event history has an invalid shape")
        events.extend(change.to_dict() for change in changes)
        self.state["events"] = events[-MAX_EVENT_HISTORY:]
        _save_state(self.state_path, self.state)
        return {
            "observed_at": observed_at,
            "changes": [change.to_dict() for change in changes],
            "errors": errors,
            "pages_checked": processed_pages,
            "pending_urls": remaining_by_source,
            "request_min_interval_seconds": self.min_request_interval_seconds,
            "storage": "metadata_only_unverified",
        }

    @staticmethod
    def _observe_listing(
        source: SiteSource,
        items: dict[str, Any],
        listing: Listing,
        observed_at: str,
        *,
        initialized: bool,
        changes: list[SiteChange],
    ) -> None:
        listing_hash = hashlib.sha256(
            f"{listing.title}\n{listing.summary}".encode("utf-8")
        ).hexdigest()
        old = items.get(listing.url)
        if old is None:
            status = "new" if initialized else "baseline"
            items[listing.url] = {
                "title": listing.title,
                "summary": listing.summary,
                "listing_sha256": listing_hash,
                "detail_sha256": "",
                "first_seen": observed_at,
                "last_seen": observed_at,
                "last_checked": "",
            }
            changes.append(SiteChange(source.name, status, listing.url, listing.title, listing.summary, observed_at, listing_hash))
            return
        old["last_seen"] = observed_at
        if old.get("listing_sha256") != listing_hash:
            old["title"] = listing.title
            old["summary"] = listing.summary
            old["listing_sha256"] = listing_hash
            changes.append(SiteChange(source.name, "updated", listing.url, listing.title, listing.summary, observed_at, listing_hash))

    @staticmethod
    def _update_detail(
        source: SiteSource,
        items: dict[str, Any],
        url: str,
        title: str,
        summary: str,
        observed_at: str,
        changes: list[SiteChange],
    ) -> None:
        item = items.get(url)
        if item is None:
            return
        item["last_checked"] = observed_at
        if title:
            item["title"] = title
        if summary:
            item["summary"] = summary
        detail_hash = hashlib.sha256(f"{title}\n{summary}".encode("utf-8")).hexdigest()
        previous_hash = item.get("detail_sha256", "")
        item["detail_sha256"] = detail_hash
        if previous_hash and previous_hash != detail_hash:
            changes.append(SiteChange(source.name, "updated", url, item.get("title", title), item.get("summary", summary), observed_at, detail_hash))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Poll public Swarms and TAAFT listings politely; keep local metadata history."
    )
    parser.add_argument("--state", default=".tideglass-monitor.json")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_RUN)
    parser.add_argument("--min-interval", type=float, default=1.5)
    parser.add_argument(
        "--daily-report", action="store_true",
        help="print a report from stored events without crawling",
    )
    parser.add_argument("--date", help="UTC report date (YYYY-MM-DD; defaults to today)")
    args = parser.parse_args(argv)
    try:
        if args.daily_report:
            print(daily_trend_report(args.state, args.date))
            return 0
        if args.date:
            parser.error("--date is only valid with --daily-report")
        monitor = SiteMonitor(
            args.state,
            max_pages_per_run=args.max_pages,
            min_request_interval_seconds=args.min_interval,
        )
        result = monitor.run_once()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"tideglass-monitor: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
