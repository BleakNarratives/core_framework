from core_framework.adapters.market_twin import MarketTwinTranslator
# Assuming the necessary import/classes exist. If not, I'll adjust based on test failure.
# Note: Assuming ScoutIntel, BuildingSpec, apply_schema are available in market_twin context or scope.

def test_axe_scout_bridge():
    translator = MarketTwinTranslator()
    
    mock_findings = [
        {
            "ticker": "TSLA",
            "scout_type": "distress",
            "severity": "CRITICAL",
            "signals": ["Debt default risk", "Margin compression"],
            "confidence": 0.88,
            "sources": ["10-K Filing"],
            "recommendations": ["Hedge exposure"]
        },
        {
            "ticker": "AAPL",
            "scout_type": "competitive",
            "severity": "WARNING",
            "signals": ["Ad spend shift"],
            "confidence": 0.65,
            "sources": ["AdTrace"],
            "recommendations": ["Monitor market share"]
        }
    ]

    for finding in mock_findings:
        translator.add_axe_scout_finding(finding)

    # Validate based on the assumption that market_twin provides a way to verify the state
    assert len(translator.buildings) == 2
    print("SUCCESS: AxeScout -> MarketTwin bridge validated successfully under mock findings!")

if __name__ == "__main__":
    try:
        test_axe_scout_bridge()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
