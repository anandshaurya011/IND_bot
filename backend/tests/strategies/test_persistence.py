from strategies.model import Condition, Strategy
from strategies.persistence import consecutive_sessions_satisfied, validate_strategy


def test_consecutive_sessions_counts_trailing_true_run():
    assert consecutive_sessions_satisfied([False, True, True, True, True, True]) == 5


def test_consecutive_sessions_stops_at_break():
    assert consecutive_sessions_satisfied([True, False, True, True]) == 2


def test_consecutive_sessions_empty_is_zero():
    assert consecutive_sessions_satisfied([]) == 0


def test_validate_strategy_rejects_session_vwap_on_daily_timeframe():
    s = Strategy(
        id="x", user_id="u", name="n", universe=["nifty50"],
        instrument_type="stock", timeframe="daily",
        conditions=[Condition(indicator="vwap_session", params={}, comparison="above", compare_to="price")],
        logic="AND", min_consecutive_sessions=5, provider="yfinance", enabled=True,
    )
    errors = validate_strategy(s)
    assert any("vwap_session" in e for e in errors)


def test_validate_strategy_rejects_intraday_on_nse_provider():
    s = Strategy(
        id="x", user_id="u", name="n", universe=["nifty50"],
        instrument_type="stock", timeframe="15m",
        conditions=[Condition(indicator="ema", params={"length": 20}, comparison="above", compare_to="price")],
        logic="AND", min_consecutive_sessions=1, provider="nse", enabled=True,
    )
    errors = validate_strategy(s)
    assert any("intraday" in e.lower() for e in errors)


def test_validate_strategy_valid_returns_empty():
    s = Strategy(
        id="x", user_id="u", name="n", universe=["nifty50"],
        instrument_type="stock", timeframe="daily",
        conditions=[Condition(indicator="ema", params={"length": 20}, comparison="above", compare_to="price")],
        logic="AND", min_consecutive_sessions=1, provider="yfinance", enabled=True,
    )
    assert validate_strategy(s) == []
