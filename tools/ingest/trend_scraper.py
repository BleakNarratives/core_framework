#!/usr/bin/env python3
"""
trend_scraper — aggregate external AI trends for predictive modeling.

SCAFFOLD. The shape is fixed; the live sources are stubs on purpose.

Design rules (load-bearing):
  * Offline by default. Tests and CI must stay deterministic, so every source
    that touches the network is opt-in via `allow_network=True` and is never
    exercised by the unit tests. `LocalJsonSource` is the network-free path.
  * Pluggable. A source is anything with `.name` and `.fetch(limit) -> list[TrendItem]`,
    so a new feed is a small class, not an edit to the aggregator.
  * Provenance kept. Every item carries its source and an `observed` date; the
    digest never invents a timestamp it was not given.

Usage:
    python3 -m tools.ingest.trend_scraper --local fixtures/trends.json --out digest.md
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol, Sequence, Tuple


@dataclass(frozen=True)
class TrendItem:
    """One observed trend. Frozen: an item is a fact, not a workspace."""
    source: str
    title: str
    url: str = ""
    observed: str = ""          # ISO-8601 date as reported by the source
    score: float = 0.0          # source-native signal (points, stars, rank…)
    tags: Tuple[str, ...] = ()


class TrendSource(Protocol):
    """Anything that can yield trend items. Structural, so no base class needed."""
    name: str
    def fetch(self, limit: int = 20) -> List[TrendItem]: ...


@dataclass
class LocalJsonSource:
    """Network-free source: reads a pre-fetched JSON list of items.

    Expected shape: [{"title": ..., "url": ..., "observed": ..., "score": ...,
    "tags": [...]}, ...]. This is the path used by tests and by any caller that
    wants to feed already-harvested data.
    """
    name: str
    path: Path

    def fetch(self, limit: int = 20) -> List[TrendItem]:
        rows = json.loads(Path(self.path).read_text(encoding="utf-8"))
        items: List[TrendItem] = []
        for row in rows[:limit]:
            items.append(TrendItem(
                source=self.name,
                title=str(row.get("title", "")),
                url=str(row.get("url", "")),
                observed=str(row.get("observed", "")),
                score=float(row.get("score", 0) or 0),
                tags=tuple(row.get("tags", []) or ()),
            ))
        return items


@dataclass
class HttpJsonSource:
    """Live source stub. Refuses to run unless `allow_network` is set.

    Wiring a real feed (HN, arXiv, a vendor changelog) belongs here: implement
    `_endpoint()` and `_parse()` and keep the `allow_network` guard.
    """
    name: str
    url: str
    allow_network: bool = False

    def fetch(self, limit: int = 20) -> List[TrendItem]:
        if not self.allow_network:
            raise RuntimeError(
                f"HttpJsonSource({self.name!r}) is network-gated; pass allow_network=True"
            )
        raise NotImplementedError(
            "Live source not implemented yet — implement _endpoint()/_parse()."
        )


def aggregate(sources: Sequence[TrendSource], limit_per_source: int = 20,
              dedupe: bool = True) -> List[TrendItem]:
    """Merge items from every source, dedupe, and rank by score (desc)."""
    seen: set = set()
    merged: List[TrendItem] = []
    for src in sources:
        for item in src.fetch(limit_per_source):
            key = (item.title.strip().lower(), item.url)
            if dedupe and key in seen:
                continue
            seen.add(key)
            merged.append(item)
    merged.sort(key=lambda i: i.score, reverse=True)
    return merged


def to_dicts(items: Iterable[TrendItem]) -> List[Dict[str, Any]]:
    return [asdict(i) for i in items]


def write_digest(items: Sequence[TrendItem], path: Path, generated: str = "") -> Path:
    """Write a markdown digest. `generated` is passed in, never invented here."""
    lines = ["# AI trend digest", ""]
    if generated:
        lines.append(f"_generated: {generated}_")
        lines.append("")
    lines.append("| score | source | title | observed |")
    lines.append("|---:|---|---|---|")
    for i in items:
        title = f"[{i.title}]({i.url})" if i.url else i.title
        lines.append(f"| {i.score:g} | {i.source} | {title} | {i.observed} |")
    out = Path(path)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _cli() -> int:
    ap = argparse.ArgumentParser(description="Aggregate AI trend items (offline by default).")
    ap.add_argument("--local", action="append", default=[], metavar="NAME=FILE",
                    help="network-free source, repeatable")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", help="write a markdown digest here")
    args = ap.parse_args()

    sources: List[TrendSource] = []
    for spec in args.local:
        name, _, path = spec.partition("=")
        sources.append(LocalJsonSource(name=name or "local", path=Path(path)))

    items = aggregate(sources, limit_per_source=args.limit)
    if args.out:
        write_digest(items, Path(args.out))
        print(f"wrote {args.out}: {len(items)} item(s)")
    else:
        print(json.dumps(to_dicts(items), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
