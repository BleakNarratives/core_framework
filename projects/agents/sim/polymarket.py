"""Offline Polymarket quote-versus-forecast analysis for Tideglass.

This module compares supplied data only. It does not fetch market data, make
forecasts, infer news sentiment, or place trades.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from projects.agents.sim.tideglass import ProbabilityRange


def _probability(value: Any, label: str) -> None:
    try:
        valid = (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            and 0 <= value <= 1
        )
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be a finite number between 0 and 1")


def _timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class MarketQuote:
    """A timestamped binary market quote, using prices in [0, 1] dollars."""

    market_id: str
    question: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    observed_at: str
    source: str
    expires_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.market_id, str) or not self.market_id.strip():
            raise ValueError("market_id must not be blank")
        if not isinstance(self.question, str) or not self.question.strip():
            raise ValueError("question must not be blank")
        if len(self.market_id) > 256 or len(self.question) > 4_000:
            raise ValueError("market_id or question exceeds its size limit")
        if not isinstance(self.source, str) or not self.source.strip() or len(self.source) > 2_000:
            raise ValueError("source must be a non-blank string of at most 2000 characters")
        for name in ("yes_bid", "yes_ask", "no_bid", "no_ask"):
            _probability(getattr(self, name), name)
        if self.yes_bid > self.yes_ask:
            raise ValueError("yes_bid must not exceed yes_ask")
        if self.no_bid > self.no_ask:
            raise ValueError("no_bid must not exceed no_ask")
        observed = _timestamp(self.observed_at, "observed_at")
        if self.expires_at is not None:
            expiry = _timestamp(self.expires_at, "expires_at")
            if expiry <= observed:
                raise ValueError("expires_at must be later than observed_at")


@dataclass(frozen=True)
class ForecastEstimate:
    """An independently supplied, explicitly uncalibrated probability range."""

    probability: ProbabilityRange
    source: str
    issued_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.probability, ProbabilityRange):
            raise ValueError("probability must be a ProbabilityRange")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("forecast source must not be blank")
        if len(self.source) > 2_000:
            raise ValueError("forecast source exceeds 2000 characters")
        _timestamp(self.issued_at, "issued_at")


@dataclass(frozen=True)
class SideEdge:
    """Per-share edge range after supplied fees and slippage assumptions."""

    net_edge_low: float
    net_edge_likely: float
    net_edge_high: float

    def to_dict(self) -> dict[str, float]:
        return {"low": self.net_edge_low, "likely": self.net_edge_likely, "high": self.net_edge_high}


@dataclass(frozen=True)
class PolymarketAnalysis:
    market_id: str
    question: str
    quote_source: str
    quote_observed_at: str
    forecast_source: str
    forecast_issued_at: str
    as_of: str
    quote_age_seconds: float
    forecast_age_seconds: float
    data_status: str
    forecast_probability: dict[str, float]
    market_yes_midpoint: float
    yes_spread: float
    no_spread: float
    estimated_cost_per_share: float
    edges: dict[str, SideEdge]
    candidate_side: str | None
    minimum_edge: float
    time_to_resolution_seconds: float | None
    model_confidence: str
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "question": self.question,
            "quote_source": self.quote_source,
            "quote_observed_at": self.quote_observed_at,
            "forecast_source": self.forecast_source,
            "forecast_issued_at": self.forecast_issued_at,
            "as_of": self.as_of,
            "quote_age_seconds": self.quote_age_seconds,
            "forecast_age_seconds": self.forecast_age_seconds,
            "data_status": self.data_status,
            "forecast_probability": self.forecast_probability,
            "market_yes_midpoint": self.market_yes_midpoint,
            "yes_spread": self.yes_spread,
            "no_spread": self.no_spread,
            "estimated_cost_per_share": self.estimated_cost_per_share,
            "net_edge_per_share": {side: edge.to_dict() for side, edge in self.edges.items()},
            "candidate_side": self.candidate_side,
            "minimum_edge": self.minimum_edge,
            "time_to_resolution_seconds": self.time_to_resolution_seconds,
            "model_confidence": self.model_confidence,
            "findings": list(self.findings),
            "trade_execution": "not performed",
            "caveat": (
                "A candidate is a conditional model comparison, not a trade instruction. "
                "Forecast quality, liquidity/depth, market rules, and actual fees must be checked."
            ),
        }


def analyze_market(
    market: MarketQuote,
    forecast: ForecastEstimate,
    *,
    as_of: str,
    estimated_fee_per_share: float = 0.0,
    estimated_slippage_per_share: float = 0.0,
    minimum_edge: float = 0.0,
    max_quote_age_seconds: int = 300,
    max_forecast_age_seconds: int = 86_400,
) -> PolymarketAnalysis:
    """Compare a supplied probability range with supplied binary market quotes.

    A side is a candidate only when its low-end forecast edge (YES), or low-end
    complementary forecast edge (NO), after provided per-share costs clears
    ``minimum_edge``. Stale/expired inputs block candidate selection. Costs are
    explicit inputs: no external fee schedule or slippage model is assumed.
    """
    if not isinstance(market, MarketQuote) or not isinstance(forecast, ForecastEstimate):
        raise ValueError("market and forecast must be MarketQuote and ForecastEstimate values")
    now = _timestamp(as_of, "as_of")
    quote_time = _timestamp(market.observed_at, "observed_at")
    forecast_time = _timestamp(forecast.issued_at, "issued_at")
    quote_age = (now - quote_time).total_seconds()
    forecast_age = (now - forecast_time).total_seconds()
    if quote_age < 0 or forecast_age < 0:
        raise ValueError("quote and forecast timestamps must not be in the future")
    for value, name in (
        (estimated_fee_per_share, "estimated_fee_per_share"),
        (estimated_slippage_per_share, "estimated_slippage_per_share"),
        (minimum_edge, "minimum_edge"),
    ):
        _probability(value, name)
    for value, name in (
        (estimated_fee_per_share, "estimated_fee_per_share"),
        (estimated_slippage_per_share, "estimated_slippage_per_share"),
    ):
        if value < 0:
            raise ValueError(f"{name} must not be negative")
    for value, name in (
        (max_quote_age_seconds, "max_quote_age_seconds"),
        (max_forecast_age_seconds, "max_forecast_age_seconds"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    expires_at = _timestamp(market.expires_at, "expires_at") if market.expires_at else None
    expired = expires_at is not None and now >= expires_at
    quote_stale = quote_age > max_quote_age_seconds
    forecast_stale = forecast_age > max_forecast_age_seconds
    status_parts = []
    if expired:
        status_parts.append("expired")
    if quote_stale:
        status_parts.append("stale_quote")
    if forecast_stale:
        status_parts.append("stale_forecast")
    data_status = ",".join(status_parts) if status_parts else "fresh"

    probability = forecast.probability
    cost = estimated_fee_per_share + estimated_slippage_per_share
    edges = {
        "YES": SideEdge(
            probability.low - market.yes_ask - cost,
            probability.likely - market.yes_ask - cost,
            probability.high - market.yes_ask - cost,
        ),
        "NO": SideEdge(
            (1 - probability.high) - market.no_ask - cost,
            (1 - probability.likely) - market.no_ask - cost,
            (1 - probability.low) - market.no_ask - cost,
        ),
    }
    viable = [] if status_parts else [
        (edge.net_edge_low, side)
        for side, edge in edges.items()
        if edge.net_edge_low > minimum_edge
    ]
    candidate = max(viable, key=lambda entry: (entry[0], entry[1]))[1] if viable else None

    findings = []
    if candidate:
        findings.append(
            f"{candidate} has a conservative supplied-model net edge of "
            f"${edges[candidate].net_edge_low:.4f}/share after the supplied costs."
        )
    else:
        findings.append("No side clears the conservative net-edge threshold with current inputs.")
    if status_parts:
        findings.append("Candidate selection blocked by: " + ", ".join(status_parts) + ".")
    findings.append("No sentiment or news model was run.")
    findings.append("Cross-market arbitrage was not evaluated; no related-market quotes were supplied.")
    findings.append("Time to resolution is reported only; no generic time-decay adjustment was applied.")

    return PolymarketAnalysis(
        market_id=market.market_id,
        question=market.question,
        quote_source=market.source,
        quote_observed_at=market.observed_at,
        forecast_source=forecast.source,
        forecast_issued_at=forecast.issued_at,
        as_of=as_of,
        quote_age_seconds=quote_age,
        forecast_age_seconds=forecast_age,
        data_status=data_status,
        forecast_probability=probability.to_dict(),
        market_yes_midpoint=(market.yes_bid + market.yes_ask) / 2,
        yes_spread=market.yes_ask - market.yes_bid,
        no_spread=market.no_ask - market.no_bid,
        estimated_cost_per_share=cost,
        edges=edges,
        candidate_side=candidate,
        minimum_edge=minimum_edge,
        time_to_resolution_seconds=(expires_at - now).total_seconds() if expires_at else None,
        model_confidence="not_calibrated",
        findings=tuple(findings),
    )
