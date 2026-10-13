"""Indicator calculations over OHLCV candle data.

All functions consume/produce plain `pandas` objects built from
`market_data.base.Candle`. Insufficient lookback is surfaced as native
NaN values (from pandas/ta) rather than fabricated numbers.
"""

from __future__ import annotations

import pandas as pd
import ta

from market_data.base import Candle

IST = "Asia/Kolkata"


class IndicatorError(Exception):
    """Raised when an indicator is requested against a meaningless timeframe."""


# Indicators that require a session boundary (i.e. intraday candles) to be
# meaningful. Requesting these against daily (or other non-intraday)
# timeframes is a logic error, not a data-quality issue, so it is rejected
# up front rather than silently producing a degenerate result.
_INTRADAY_ONLY_INDICATORS = {"vwap_session"}


def validate_indicator_timeframe(indicator: str, timeframe: str) -> None:
    """Raise IndicatorError for indicator/timeframe combos that are meaningless.

    e.g. `vwap_session` (true intraday, session-resetting VWAP) requested
    against `timeframe="daily"` candles has no session boundary to reset at.
    """
    if indicator in _INTRADAY_ONLY_INDICATORS and timeframe == "daily":
        raise IndicatorError(
            f"'{indicator}' requires intraday candles; "
            f"timeframe={timeframe!r} has no intraday session boundary"
        )


def to_dataframe(candles: list[Candle]) -> pd.DataFrame:
    """Convert a list of Candle into a DataFrame indexed by tz-aware (IST) timestamp."""
    rows = {
        "open": [c.open for c in candles],
        "high": [c.high for c in candles],
        "low": [c.low for c in candles],
        "close": [c.close for c in candles],
        "volume": [c.volume for c in candles],
    }
    index = pd.to_datetime([c.ts for c in candles], unit="s", utc=True).tz_convert(IST)
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="ts"))
    return df


def ema(df: pd.DataFrame, length: int) -> pd.Series:
    return df["close"].ewm(span=length, adjust=False).mean()


def sma(df: pd.DataFrame, length: int) -> pd.Series:
    return df["close"].rolling(window=length).mean()


def rsi(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return ta.momentum.RSIIndicator(close=df["close"], window=length).rsi()


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    indicator = ta.trend.MACD(
        close=df["close"], window_fast=fast, window_slow=slow, window_sign=signal
    )
    return pd.DataFrame(
        {
            "macd": indicator.macd(),
            "signal": indicator.macd_signal(),
            "hist": indicator.macd_diff(),
        },
        index=df.index,
    )


def bollinger(df: pd.DataFrame, length: int = 20, std: int = 2) -> pd.DataFrame:
    indicator = ta.volatility.BollingerBands(close=df["close"], window=length, window_dev=std)
    return pd.DataFrame(
        {
            "lower": indicator.bollinger_lband(),
            "mid": indicator.bollinger_mavg(),
            "upper": indicator.bollinger_hband(),
        },
        index=df.index,
    )


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return ta.trend.ADXIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=length
    ).adx()


def supertrend(df: pd.DataFrame, length: int = 10, multiplier: int = 3) -> pd.DataFrame:
    """Standard SuperTrend. `ta` has no built-in implementation, so this
    hand-rolls the well-known algorithm: ATR-based basic bands, final bands
    that only move in the trend's favor, and a direction flip when price
    crosses the opposite final band.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    atr = ta.volatility.AverageTrueRange(
        high=high, low=low, close=close, window=length
    ).average_true_range()

    hl2 = (high + low) / 2
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = pd.Series(index=df.index, dtype="float64")
    final_lower = pd.Series(index=df.index, dtype="float64")
    supertrend_line = pd.Series(index=df.index, dtype="float64")
    direction = pd.Series(index=df.index, dtype="int64")

    for i in range(len(df)):
        if i == 0 or pd.isna(atr.iloc[i]):
            final_upper.iloc[i] = basic_upper.iloc[i]
            final_lower.iloc[i] = basic_lower.iloc[i]
            direction.iloc[i] = 1
            supertrend_line.iloc[i] = final_lower.iloc[i] if not pd.isna(final_lower.iloc[i]) else float("nan")
            continue

        prev_close = close.iloc[i - 1]
        prev_final_upper = final_upper.iloc[i - 1]
        prev_final_lower = final_lower.iloc[i - 1]

        if basic_upper.iloc[i] < prev_final_upper or prev_close > prev_final_upper:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = prev_final_upper

        if basic_lower.iloc[i] > prev_final_lower or prev_close < prev_final_lower:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = prev_final_lower

        prev_direction = direction.iloc[i - 1]
        curr_close = close.iloc[i]

        if prev_direction == 1:
            if curr_close < final_lower.iloc[i]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = 1
        else:
            if curr_close > final_upper.iloc[i]:
                direction.iloc[i] = 1
            else:
                direction.iloc[i] = -1

        supertrend_line.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    # Rows where ATR is NaN (insufficient lookback) have no real SuperTrend value.
    supertrend_line[atr.isna()] = float("nan")
    direction_result = direction.astype("float64")
    direction_result[atr.isna()] = float("nan")

    return pd.DataFrame({"supertrend": supertrend_line, "direction": direction_result}, index=df.index)


def vwap_session(df: pd.DataFrame) -> pd.Series:
    """True intraday VWAP: resets at the start of each trading session (date)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    dates = df.index.date
    cum_pv = pv.groupby(dates).cumsum()
    cum_vol = df["volume"].groupby(dates).cumsum()
    return cum_pv / cum_vol


def vwap_rolling(df: pd.DataFrame, days: int) -> pd.Series:
    """Rolling N-session VWAP over daily OHLCV candles. No session reset -
    this is a different metric from `vwap_session` and is named differently
    on purpose (spec §3): it's a rolling window average, not a true
    session-anchored VWAP.
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical_price * df["volume"]
    rolling_pv = pv.rolling(window=days).sum()
    rolling_vol = df["volume"].rolling(window=days).sum()
    return rolling_pv / rolling_vol
