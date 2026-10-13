import pandas as pd
import pytest

from instruments.universe import Instrument
from market_data.base import Candle, Provider, ProviderError
from scanner.engine import _compare, run_scan
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

    def __init__(self):
        self.lookback_calls: list[int] = []

    def get_daily_candles(self, symbol, lookback_days):
        self.lookback_calls.append(lookback_days)
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


@pytest.fixture
def fake_provider():
    return _FakeProvider()


@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch, fake_provider):
    monkeypatch.setattr("scanner.engine.get_provider", lambda name: fake_provider)
    monkeypatch.setattr(
        "scanner.engine.list_universe", lambda name: list(_INSTRUMENTS.values())
    )
    # No real network calls in tests - skip the inter-instrument rate-limit pacing.
    monkeypatch.setattr("scanner.engine.INTER_INSTRUMENT_DELAY_SECONDS", 0)


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


def test_run_scan_ema200_requests_enough_lookback_for_warmup(fake_provider):
    # EMA length=200 + min_consecutive_sessions buffer must drive a lookback
    # window well beyond the old flat +30 buffer - assert against the fake
    # provider's recorded lookback_days call args.
    strategy = _make_strategy(min_consecutive_sessions=5)
    run_scan(strategy)

    assert fake_provider.lookback_calls
    # old behaviour would have requested min_consecutive_sessions + 30 = 35
    # calendar days; the new behaviour must account for the EMA(200) warm-up.
    assert all(count > 200 for count in fake_provider.lookback_calls)


def test_run_scan_non_provider_error_becomes_row_not_dropped():
    """A non-ProviderError exception (e.g. malformed compare_to/params raising
    ValueError) for one instrument must not drop the other instruments'
    results, mirroring test_run_scan_provider_error_becomes_row_not_dropped
    but with a different exception type.
    """
    strategy = Strategy(
        id="strat-2",
        user_id="user-1",
        name="malformed-condition",
        universe=["fake_universe"],
        instrument_type="stock",
        timeframe="daily",
        conditions=[
            Condition(
                indicator="ema",
                params={"length": 200},
                comparison="above",
                compare_to="ema:not_a_number",
            )
        ],
        logic="AND",
        min_consecutive_sessions=5,
        provider="fake",
        enabled=True,
    )

    rows = run_scan(strategy)

    symbols = {r.symbol for r in rows}
    assert symbols == {"OK", "PARTIAL", "FAIL"}
    for row in rows:
        assert row.latest_price is None
        assert row.satisfied is False


def test_compare_not_equal():
    lhs = pd.Series([1.0, 2.0, 3.0, float("nan")])
    rhs = pd.Series([1.0, 2.5, 3.0, 4.0])
    result = _compare(lhs, "not_equal", rhs)
    # row 0: equal -> False. row 1: differ -> True. row 2: equal -> False.
    # row 3: lhs is NaN -> never fabricate a verdict -> False.
    assert list(result) == [False, True, False, False]


def test_run_scan_paces_requests_between_instruments(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("scanner.engine.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("scanner.engine.INTER_INSTRUMENT_DELAY_SECONDS", 0.35)

    strategy = _make_strategy(min_consecutive_sessions=1)
    run_scan(strategy)

    # 3 instruments -> 2 inter-instrument pauses (no delay before the first).
    assert sleep_calls == [0.35, 0.35]


def test_resolve_universe_watchlist_symbols_come_first(monkeypatch, tmp_db_path):
    from database import schema

    schema.init_db()
    conn = schema.conn()
    conn.execute(
        "INSERT INTO watchlist (user_id, symbol, added_at) VALUES (?, ?, ?)",
        ("user-1", "PARTIAL", 1),
    )
    conn.close()
    monkeypatch.setattr("scanner.engine.resolve", lambda symbol: _INSTRUMENTS.get(f"{symbol}.NS"))

    strategy = _make_strategy(min_consecutive_sessions=1)
    strategy = strategy.model_copy(update={"universe": ["fake_universe", "watchlist"]})

    from scanner.engine import _resolve_universe

    instruments = _resolve_universe(strategy)
    symbols = [i.symbol for i in instruments]
    # PARTIAL is in both "watchlist" and "fake_universe" - watchlist membership
    # should put it first regardless of "watchlist"'s position in strategy.universe.
    assert symbols[0] == "PARTIAL"
    assert set(symbols) == {"OK", "PARTIAL", "FAIL"}


def test_parse_spec_uses_length_for_most_indicators():
    from scanner.engine import _parse_spec

    assert _parse_spec("ema:200") == ("ema", {"length": 200})


def test_parse_spec_uses_days_for_vwap_rolling():
    from scanner.engine import _parse_spec

    assert _parse_spec("vwap_rolling:5") == ("vwap_rolling", {"days": 5})
