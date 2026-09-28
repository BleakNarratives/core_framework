from __future__ import annotations

import json
import unittest

from projects.agents.sim.polymarket import (
    ForecastEstimate,
    MarketQuote,
    analyze_market,
)
from projects.agents.sim.tideglass import ProbabilityRange


AS_OF = "2026-09-27T12:00:00Z"


def market(**overrides) -> MarketQuote:
    values = {
        "market_id": "market-1",
        "question": "Will the event occur?",
        "yes_bid": 0.38,
        "yes_ask": 0.42,
        "no_bid": 0.57,
        "no_ask": 0.61,
        "observed_at": "2026-09-27T11:59:00Z",
        "source": "fixture order book",
        "expires_at": "2026-10-01T00:00:00Z",
    }
    values.update(overrides)
    return MarketQuote(**values)


def forecast(probability: ProbabilityRange | None = None, **overrides) -> ForecastEstimate:
    values = {
        "probability": probability or ProbabilityRange(0.60, 0.65, 0.70),
        "source": "manual baseline forecast",
        "issued_at": "2026-09-27T11:58:00Z",
    }
    values.update(overrides)
    return ForecastEstimate(**values)


class PolymarketAnalysisTests(unittest.TestCase):
    def test_yes_candidate_uses_conservative_net_edge(self):
        result = analyze_market(
            market(), forecast(), as_of=AS_OF,
            estimated_fee_per_share=0.01,
            estimated_slippage_per_share=0.01,
            minimum_edge=0.10,
        )
        self.assertEqual(result.candidate_side, "YES")
        self.assertAlmostEqual(result.edges["YES"].net_edge_low, 0.16)
        self.assertAlmostEqual(result.edges["YES"].net_edge_likely, 0.21)
        self.assertEqual(result.data_status, "fresh")
        self.assertEqual(result.quote_age_seconds, 60)

    def test_no_candidate_uses_complement_probability_and_own_ask(self):
        quote = market(yes_bid=0.78, yes_ask=0.82, no_bid=0.17, no_ask=0.21)
        result = analyze_market(
            quote,
            forecast(ProbabilityRange(0.30, 0.35, 0.40)),
            as_of=AS_OF,
            minimum_edge=0.20,
        )
        self.assertEqual(result.candidate_side, "NO")
        self.assertAlmostEqual(result.edges["NO"].net_edge_low, 0.39)

    def test_costs_can_remove_apparent_edge(self):
        result = analyze_market(
            market(), forecast(), as_of=AS_OF,
            estimated_fee_per_share=0.20,
            estimated_slippage_per_share=0.20,
            minimum_edge=0.05,
        )
        self.assertIsNone(result.candidate_side)
        self.assertAlmostEqual(result.estimated_cost_per_share, 0.40)

    def test_stale_or_expired_inputs_block_candidate_selection(self):
        stale_quote = market(observed_at="2026-09-27T11:00:00Z")
        stale_result = analyze_market(stale_quote, forecast(), as_of=AS_OF)
        self.assertIn("stale_quote", stale_result.data_status)
        self.assertIsNone(stale_result.candidate_side)

        expired_result = analyze_market(
            market(expires_at="2026-09-27T11:59:30Z"), forecast(), as_of=AS_OF
        )
        self.assertIn("expired", expired_result.data_status)
        self.assertIsNone(expired_result.candidate_side)

        old_forecast = forecast(issued_at="2026-09-25T00:00:00Z")
        forecast_result = analyze_market(market(), old_forecast, as_of=AS_OF)
        self.assertIn("stale_forecast", forecast_result.data_status)
        self.assertIsNone(forecast_result.candidate_side)

    def test_report_is_serializable_and_marks_unavailable_analysis(self):
        result = analyze_market(market(), forecast(), as_of=AS_OF)
        report = result.to_dict()
        json.dumps(report)
        self.assertEqual(report["model_confidence"], "not_calibrated")
        self.assertEqual(report["trade_execution"], "not performed")
        self.assertTrue(any("No sentiment or news model was run." in item for item in report["findings"]))
        self.assertTrue(any("Cross-market arbitrage was not evaluated" in item for item in report["findings"]))
        self.assertAlmostEqual(report["market_yes_midpoint"], 0.40)
        self.assertAlmostEqual(report["yes_spread"], 0.04)

    def test_invalid_quotes_and_forecast_timestamps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "yes_bid"):
            market(yes_bid=0.5, yes_ask=0.4)
        with self.assertRaisesRegex(ValueError, "source"):
            market(source=" ")
        with self.assertRaisesRegex(ValueError, "timezone"):
            market(observed_at="2026-09-27T11:59:00")
        with self.assertRaisesRegex(ValueError, "future"):
            analyze_market(
                market(), forecast(issued_at="2026-09-27T12:01:00Z"), as_of=AS_OF
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            analyze_market(market(), forecast(), as_of=AS_OF, minimum_edge=1.1)


if __name__ == "__main__":
    unittest.main()
