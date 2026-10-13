from __future__ import annotations

import pandas as pd
import pytest

from indicators.calc import (
    IndicatorError,
    adx,
    bollinger,
    ema,
    macd,
    sma,
    rsi,
    supertrend,
    to_dataframe,
    validate_indicator_timeframe,
    vwap_rolling,
    vwap_session,
)
from market_data.base import Candle


def _daily_candles(n: int, start_ts: int = 1_700_000_000, step_seconds: int = 86400) -> list[Candle]:
    candles = []
    price = 100.0
    for i in range(n):
        price += 0.5
        candles.append(
            Candle(
                ts=start_ts + i * step_seconds,
                open=price - 0.3,
                high=price + 1.0,
                low=price - 1.0,
                close=price,
                volume=1000 + i,
            )
        )
    return candles


def test_to_dataframe_columns_and_tz():
    candles = _daily_candles(5)
    df = to_dataframe(candles)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "Asia/Kolkata"


def test_ema200_matches_independent_calculation():
    candles = _daily_candles(220)
    df = to_dataframe(candles)
    result = ema(df, 200)

    expected = df["close"].ewm(span=200, adjust=False).mean()
    assert result.iloc[-1] == pytest.approx(expected.iloc[-1])


def test_sma_basic():
    candles = _daily_candles(10)
    df = to_dataframe(candles)
    result = sma(df, 5)
    expected_last = df["close"].iloc[-5:].mean()
    assert result.iloc[-1] == pytest.approx(expected_last)
    # insufficient lookback -> NaN, not fabricated
    assert pd.isna(result.iloc[0])


def test_rsi_dtype_and_range():
    candles = _daily_candles(50)
    df = to_dataframe(candles)
    result = rsi(df, 14)
    assert isinstance(result, pd.Series)
    valid = result.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_macd_columns():
    candles = _daily_candles(60)
    df = to_dataframe(candles)
    result = macd(df)
    assert list(result.columns) == ["macd", "signal", "hist"]
    assert isinstance(result, pd.DataFrame)


def test_bollinger_columns_and_ordering():
    candles = _daily_candles(30)
    df = to_dataframe(candles)
    result = bollinger(df, length=20, std=2)
    assert list(result.columns) == ["lower", "mid", "upper"]
    valid = result.dropna()
    assert (valid["lower"] <= valid["mid"]).all()
    assert (valid["mid"] <= valid["upper"]).all()


def test_adx_dtype():
    candles = _daily_candles(60)
    df = to_dataframe(candles)
    result = adx(df, 14)
    assert isinstance(result, pd.Series)
    # warm-up window (first length-1 rows) must be NaN, not ta's fabricated 0.0
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[12])
    valid = result.dropna()
    assert (valid >= 0).all()


def test_supertrend_columns_and_direction_values():
    candles = _daily_candles(60)
    df = to_dataframe(candles)
    result = supertrend(df, length=10, multiplier=3)
    assert list(result.columns) == ["supertrend", "direction"]
    # warm-up window (first length-1 rows) must be NaN, not a fabricated
    # value derived from ta's zero-filled ATR.
    assert pd.isna(result["supertrend"].iloc[0])
    assert pd.isna(result["direction"].iloc[0])
    assert pd.isna(result["supertrend"].iloc[8])
    assert pd.isna(result["direction"].iloc[8])
    valid_direction = result["direction"].dropna()
    assert set(valid_direction.unique()).issubset({1.0, -1.0})


def test_vwap_session_resets_at_new_session():
    # Session 1: 3 intraday bars at 5-min interval on day 1.
    # Session 2: 3 intraday bars on day 2, starting fresh.
    base_day1 = 1_700_000_000  # arbitrary epoch seconds, day boundary irrelevant to logic besides .date()
    session1 = [
        Candle(ts=base_day1, open=100, high=102, low=99, close=101, volume=1000),
        Candle(ts=base_day1 + 300, open=101, high=103, low=100, close=102, volume=1500),
        Candle(ts=base_day1 + 600, open=102, high=104, low=101, close=103, volume=2000),
    ]
    base_day2 = base_day1 + 86400
    session2 = [
        Candle(ts=base_day2, open=200, high=210, low=195, close=205, volume=3000),
        Candle(ts=base_day2 + 300, open=205, high=215, low=200, close=210, volume=3500),
    ]
    candles = session1 + session2
    df = to_dataframe(candles)
    result = vwap_session(df)

    # First bar of session 2 must equal that bar's own typical price,
    # not a blend with session 1's accumulated VWAP.
    session2_bar1_typical = (210 + 195 + 205) / 3
    assert result.iloc[3] == pytest.approx(session2_bar1_typical)


def test_vwap_rolling_is_distinct_from_vwap_session():
    candles = _daily_candles(10)
    df = to_dataframe(candles)
    result = vwap_rolling(df, days=5)
    assert isinstance(result, pd.Series)
    assert pd.isna(result.iloc[0])  # insufficient lookback for first bars
    assert not pd.isna(result.iloc[-1])


def test_validate_indicator_timeframe_rejects_vwap_session_daily():
    with pytest.raises(IndicatorError):
        validate_indicator_timeframe("vwap_session", "daily")


def test_validate_indicator_timeframe_allows_ema_daily():
    validate_indicator_timeframe("ema", "daily")  # should not raise
