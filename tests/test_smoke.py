def test_import():
    import market_agent
    assert hasattr(market_agent, "MarketAgent")