"""Market data provider backed by NSE India's public JSON endpoints.

Limitation: NSE's public website API (https://www.nseindia.com/api/...) only
reliably exposes end-of-day (EOD) historical data and live quotes. It does
not expose a stable, documented intraday OHLC history endpoint, so
`get_intraday_candles` always raises `ProviderError("intraday_unsupported")`.

NSE blocks requests that don't look like they came from a browser, so every
call warms up a session cookie against the homepage before hitting the API,
and sends browser-like headers (User-Agent, Accept, Referer, etc).
"""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from market_data.base import Candle, Provider, ProviderError, cache_candles, with_retry

_BASE_URL = "https://www.nseindia.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
_ONE_DAY_SECONDS = 24 * 60 * 60
_IST = ZoneInfo("Asia/Kolkata")


def _parse_ist(value: str, fmt: str) -> int:
    """Parse an NSE date/time string as IST wall-clock time and return epoch seconds.

    NSE's timestamps are always IST. Using `time.mktime` would interpret the
    parsed struct in the host machine's local timezone, silently shifting
    every value on a non-IST host (e.g. a UTC container). We parse naively
    then explicitly localize to Asia/Kolkata.
    """
    naive = datetime.strptime(value, fmt)
    aware = naive.replace(tzinfo=_IST)
    return int(aware.timestamp())


def _new_session() -> httpx.Client:
    client = httpx.Client(headers=_HEADERS, timeout=10.0)
    # Cookie warmup: NSE rejects bare API requests without a browser-origin cookie.
    client.get(_BASE_URL)
    return client


class NSEProvider(Provider):
    name = "nse"

    @with_retry(max_attempts=3, backoff_base=1.5)
    @cache_candles(ttl=3600)
    def get_daily_candles(self, symbol: str, lookback_days: int) -> list[Candle]:
        try:
            with _new_session() as client:
                resp = client.get(
                    f"{_BASE_URL}/api/historical/cm/equity",
                    params={"symbol": symbol, "series": '["EQ"]'},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(str(exc)) from exc

        rows = data.get("data") if isinstance(data, dict) else None
        if not rows:
            raise ProviderError(f"no daily data for {symbol}")

        candles: list[Candle] = []
        for row in rows[-lookback_days:] if lookback_days else rows:
            try:
                candles.append(
                    Candle(
                        ts=_parse_ist(row["CH_TIMESTAMP"], "%Y-%m-%d"),
                        open=float(row["CH_OPENING_PRICE"]),
                        high=float(row["CH_TRADE_HIGH_PRICE"]),
                        low=float(row["CH_TRADE_LOW_PRICE"]),
                        close=float(row["CH_CLOSING_PRICE"]),
                        volume=int(row["CH_TOT_TRADED_QTY"]),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                raise ProviderError(str(exc)) from exc
        return candles

    def get_intraday_candles(self, symbol: str, interval: str, lookback_days: int) -> list[Candle]:
        raise ProviderError("intraday_unsupported")

    @with_retry(max_attempts=3, backoff_base=1.5)
    @cache_candles(ttl=60)
    def get_quote(self, symbol: str) -> dict:
        try:
            with _new_session() as client:
                resp = client.get(f"{_BASE_URL}/api/quote-equity", params={"symbol": symbol})
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(str(exc)) from exc

        try:
            price_info = data["priceInfo"]
            price = float(price_info["lastPrice"])
            last_update = data.get("metadata", {}).get("lastUpdateTime")
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(str(exc)) from exc

        ts = None
        if last_update:
            try:
                ts = _parse_ist(last_update, "%d-%b-%Y %H:%M:%S")
            except ValueError:
                ts = None

        if ts is None:
            # No real timestamp - never fabricate one; mark the quote stale
            # using "now" only as a placeholder clock, not as fact about the data.
            ts = int(time.time())
            is_stale = True
        else:
            is_stale = (time.time() - ts) > _ONE_DAY_SECONDS

        return {"price": price, "ts": ts, "is_stale": is_stale}
