from strategies.model import Condition, Strategy


def test_strategy_and_condition_round_trip():
    s = Strategy(
        id="x",
        user_id="u",
        name="n",
        universe=["nifty50"],
        instrument_type="stock",
        timeframe="daily",
        conditions=[
            Condition(indicator="ema", params={"length": 20}, comparison="above", compare_to="price")
        ],
        logic="AND",
        min_consecutive_sessions=1,
        provider="yfinance",
        enabled=True,
    )
    assert s.conditions[0].indicator == "ema"
    assert s.instrument_type == "stock"
