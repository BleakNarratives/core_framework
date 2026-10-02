#!/usr/bin/env python3
"""
core_framework/tests/test_live_sources.py

Live sources are network-gated; these tests NEVER touch the network. They verify
the offline parser and that un-gated fetches refuse to run.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core_framework.adapters.ingest_adapter import IngestAdapter  # noqa: E402
from core_framework.adapters.live_sources import (  # noqa: E402
    HttpJsonTrendSource,
    LiveSourceError,
    SecEdgarFullTextSource,
    parse_sec_edgar_hits,
)

PAYLOAD = {
    "hits": {
        "hits": [
            {
                "_id": "0000320193-26-000001:aapl-8k.htm",
                "_score": 12.5,
                "_source": {
                    "display_names": ["Apple Inc. (AAPL) (CIK 0000320193)"],
                    "file_date": "2026-01-15",
                    "form_type": "8-K",
                    "ciks": ["0000320193"],
                    "root_forms": ["8-K"],
                },
            },
            {
                "_id": "0000789019-26-000002:msft-10q.htm",
                "_score": 3.0,
                "_source": {
                    "display_names": ["Microsoft Corp"],
                    "file_date": "2026-01-20",
                    "form_type": "10-Q",
                    "ciks": ["0000789019"],
                    "root_forms": ["10-Q"],
                },
            },
        ]
    }
}


def test_parse_edgar_hits_offline():
    items = parse_sec_edgar_hits(PAYLOAD)
    assert len(items) == 2

    first = items[0]
    assert first.source == "sec"
    assert first.title == "8-K: Apple Inc. (AAPL) (CIK 0000320193)"
    assert first.observed == "2026-01-15"
    assert first.score == 12.5
    assert first.tags == ("8-K",)
    assert "Archives/edgar/data/320193/000032019326000001/aapl-8k.htm" in first.url


def test_parse_handles_empty_and_garbage():
    assert parse_sec_edgar_hits({}) == []
    assert parse_sec_edgar_hits({"hits": {"hits": [None, "x"]}}) == []
    assert parse_sec_edgar_hits(None) == []


def test_ingest_adapter_consumes_parsed_items():
    findings = IngestAdapter("sec").findings_from_items(parse_sec_edgar_hits(PAYLOAD))
    assert len(findings) == 2
    assert all(f["medium"] == "filings" for f in findings)
    assert findings[0]["scout_type"] in {"distress", "regulatory", "general"}


def test_fetch_is_network_gated():
    source = SecEdgarFullTextSource("debt covenant")
    with pytest.raises(LiveSourceError):
        source.fetch(limit=5)


def test_generic_http_source_is_network_gated():
    source = HttpJsonTrendSource("x", "https://example.invalid", lambda p: [])
    with pytest.raises(LiveSourceError):
        source.fetch()
