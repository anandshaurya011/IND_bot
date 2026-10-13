import pytest

from instruments.universe import Instrument
from market_data.base import Candle, Provider, ProviderError
from scanner.engine import run_scan
from strategies.model import Condition, Strategy

_OK_SYMBOL = "OK.NS"
_PARTIAL_SYMBOL = "PARTIAL.NS"
_FAIL_SYMBOL = "FAIL.NS"

_INSTRUMENTS = {
    _OK_SYMBOL: Instrument(
        symbol="OK", name="Ok Co", yf_ticker=_OK_SYMBOL, nse_symbol="OK", kind="stock"
    ),
    _PARTIAL_SYMBOL: Instrument(
        symbol="PARTIAL",
        name="Partial Co",
        yf_ticker=_PARTIAL_SYMBOL,
        nse_symbol="PARTIAL",
        kind="stock",
    ),
    _FAIL_SYMBOL: Instrument(
        symbol="FAIL", name="Fail Co", yf_ticker=_FAIL_SYMBOL, nse_symbol="FAIL", kind="stock"
    ),
}


def _make_candles(n: int, drop_last: int) -> list[Candle]:
    """n daily candles, close=100 except the trailing `drop_last` which close=50.

    A sharp drop makes `close` fall below a slow-moving EMA(200) for exactly
    `drop_last` trailing sessions (EMA lags the drop).
    """
    candles = []
    base_ts = 1_700_000_000
    for i in range(n):
        is_dropped = i >= n - drop_last
        close = 50.0 if is_dropped else 100.0
        candles.append(
            Candle(
                ts=base_ts + i * 86400,
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000,
            )
        )
    return candles


class _FakeProvider(Provider):
    """Fake provider returning controllable per-symbol candle series.

    Reuses the `_FakeProvider` pattern from Task 1 (tests/market_data/test_base.py),
    extended so each symbol can return its own series or raise ProviderError.
    """

    name = "fake"

    def get_daily_candles(self, symbol, lookback_days):
        if symbol == _OK_SYMBOL:
            return _make_candles(lookback_days, drop_last=5)
        if symbol == _PARTIAL_SYMBOL:
            return _make_candles(lookback_days, drop_last=3)
        if symbol == _FAIL_SYMBOL:
            raise ProviderError("simulated provider outage")
        raise ProviderError(f"unexpected symbol {symbol}")

    def get_intraday_candles(self, symbol, interval, lookback_days):
        raise ProviderError("intraday_unsupported")

    def get_quote(self, symbol):
        raise ProviderError("not implemented")


def _make_strategy(min_consecutive_sessions: int) -> Strategy:
    return Strategy(
        id="strat-1",
        user_id="user-1",
        name="close-below-ema200",
        universe=["fake_universe"],
        instrument_type="stock",
        timeframe="daily",
        conditions=[
            Condition(
                indicator="ema",
                params={"length": 200},
                comparison="above",
                compare_to="price",
            )
        ],
        logic="AND",
        min_consecutive_sessions=min_consecutive_sessions,
        provider="fake",
        enabled=True,
    )


@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch):
    monkeypatch.setattr("scanner.engine.get_provider", lambda name: _FakeProvider())
    monkeypatch.setattr(
        "scanner.engine.list_universe", lambda name: list(_INSTRUMENTS.values())
    )


def test_run_scan_satisfied_for_full_trailing_run():
    strategy = _make_strategy(min_consecutive_sessions=5)
    rows = run_scan(strategy)
    row = next(r for r in rows if r.symbol == "OK")
    assert row.satisfied is True
    assert row.consecutive_sessions == 5


def test_run_scan_not_satisfied_when_run_too_short():
    strategy = _make_strategy(min_consecutive_sessions=5)
    rows = run_scan(strategy)
    row = next(r for r in rows if r.symbol == "PARTIAL")
    assert row.satisfied is False
    assert row.consecutive_sessions == 3


def test_run_scan_provider_error_becomes_row_not_dropped():
    strategy = _make_strategy(min_consecutive_sessions=5)
    rows = run_scan(strategy)

    symbols = {r.symbol for r in rows}
    assert symbols == {"OK", "PARTIAL", "FAIL"}

    fail_row = next(r for r in rows if r.symbol == "FAIL")
    assert fail_row.latest_price is None
    assert fail_row.satisfied is False

    # The scan as a whole still returns rows for the other instruments.
    ok_row = next(r for r in rows if r.symbol == "OK")
    assert ok_row.latest_price is not None
