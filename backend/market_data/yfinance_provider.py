from __future__ import annotations

import time

import yfinance as yf

from market_data.base import Candle, Provider, ProviderError, cache_candles, with_retry

_INTRADAY_INTERVALS = {"5m", "15m", "1h"}
_ONE_DAY_SECONDS = 24 * 60 * 60


def _history_to_candles(history) -> list[Candle]:
    candles: list[Candle] = []
    for ts, row in history.iterrows():
        candles.append(
            Candle(
                ts=int(ts.timestamp()),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
            )
        )
    return candles


class YFinanceProvider(Provider):
    """Market data provider backed by the `yfinance` package.

    Equities/indices are addressed with yfinance tickers: NSE equities use a
    `.NS` suffix (e.g. `RELIANCE.NS`), and well-known indices use caret
    symbols (`^NSEI`, `^NSEBANK`, `^CNXIT`). Callers are responsible for
    passing the correctly-suffixed symbol.
    """

    name = "yfinance"

    @with_retry(max_attempts=3, backoff_base=1.5)
    @cache_candles(ttl=3600)
    def get_daily_candles(self, symbol: str, lookback_days: int) -> list[Candle]:
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=f"{max(lookback_days, 1)}d", interval="1d")
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(str(exc)) from exc
        if history is None or history.empty:
            raise ProviderError(f"no daily data for {symbol}")
        return _history_to_candles(history)

    @with_retry(max_attempts=3, backoff_base=1.5)
    @cache_candles(ttl=3600)
    def get_intraday_candles(self, symbol: str, interval: str, lookback_days: int) -> list[Candle]:
        if interval not in _INTRADAY_INTERVALS:
            raise ProviderError("intraday_unsupported")
        try:
            ticker = yf.Ticker(symbol)
            history = ticker.history(period=f"{max(lookback_days, 1)}d", interval=interval)
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("intraday_unsupported") from exc
        if history is None or history.empty:
            raise ProviderError("intraday_unsupported")
        return _history_to_candles(history)

    @with_retry(max_attempts=3, backoff_base=1.5)
    @cache_candles(ttl=60)
    def get_quote(self, symbol: str) -> dict:
        try:
            candles = self.get_daily_candles(symbol, lookback_days=5)
        except ProviderError:
            raise
        latest = candles[-1]
        is_stale = (time.time() - latest.ts) > _ONE_DAY_SECONDS
        return {"price": latest.close, "ts": latest.ts, "is_stale": is_stale}
