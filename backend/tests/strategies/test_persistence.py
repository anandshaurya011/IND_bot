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


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(
        id="x", user_id="u", name="n", universe=["nifty50"],
        instrument_type="stock", timeframe="daily",
        conditions=[Condition(indicator="ema", params={"length": 20}, comparison="above", compare_to="price")],
        logic="AND", min_consecutive_sessions=1, provider="yfinance", enabled=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_validate_strategy_rejects_malformed_scan_time():
    s = Strategy(**_base_kwargs(scan_time="25:99"))
    errors = validate_strategy(s)
    assert any("scan_time" in e for e in errors)


def test_validate_strategy_rejects_malformed_scan_days_single_int():
    s = Strategy(**_base_kwargs(scan_days=[9]))
    errors = validate_strategy(s)
    assert any("scan_days" in e for e in errors)


def test_validate_strategy_rejects_empty_scan_days_list():
    s = Strategy(**_base_kwargs(scan_days=[]))
    errors = validate_strategy(s)
    assert any("scan_days" in e for e in errors)


def test_validate_strategy_accepts_valid_scan_time_and_daily():
    s = Strategy(**_base_kwargs(scan_time="09:00", scan_days="daily"))
    assert validate_strategy(s) == []


def test_validate_strategy_accepts_valid_scan_time_and_weekday_list():
    s = Strategy(**_base_kwargs(scan_time="09:00", scan_days=[0, 1, 2, 3, 4]))
    assert validate_strategy(s) == []


def test_validate_strategy_rejects_unknown_universe_name():
    s = Strategy(**_base_kwargs(universe=["not_a_real_universe"]))
    errors = validate_strategy(s)
    assert any("not_a_real_universe" in e for e in errors)


def test_validate_strategy_rejects_empty_universe():
    s = Strategy(**_base_kwargs(universe=[]))
    errors = validate_strategy(s)
    assert any("universe" in e and "empty" in e for e in errors)


def test_validate_strategy_accepts_watchlist_universe():
    s = Strategy(**_base_kwargs(universe=["watchlist"]))
    errors = validate_strategy(s)
    assert errors == []
