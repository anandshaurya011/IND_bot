"""Regression test for a real bug: NSEProvider's `_new_session()` fired the
cookie-warmup request on the client BEFORE entering `with client: ...`.
httpx marks a client "opened" the moment any request is sent (not just on
`__enter__`), so the subsequent `with` block's `__enter__` always raised
"Cannot open a client instance more than once." - this method has never
actually worked. Fixed by moving the warmup request inside the `with` block.

Uses httpx's MockTransport so this never depends on live NSE network access
(NSE also actively blocks non-browser traffic, which would make a live-network
test flaky/always-failing regardless of this bug).
"""

from __future__ import annotations

import httpx
import pytest

import market_data.nse_provider as nse_provider_module
from market_data.base import ProviderError
from market_data.nse_provider import NSEProvider


def _mock_client_factory(handler):
    """Builds a `_new_session`-compatible factory backed by a MockTransport,
    so `with client:` goes through the real httpx state machine (the thing
    that was actually broken) rather than bypassing it with a stub object.
    """

    def factory():
        return httpx.Client(transport=httpx.MockTransport(handler))

    return factory


def test_get_daily_candles_does_not_raise_cannot_open_twice(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "CH_TIMESTAMP": "2026-10-10",
                        "CH_OPENING_PRICE": "100.0",
                        "CH_TRADE_HIGH_PRICE": "105.0",
                        "CH_TRADE_LOW_PRICE": "99.0",
                        "CH_CLOSING_PRICE": "103.0",
                        "CH_TOT_TRADED_QTY": "1000",
                    }
                ]
            },
        )

    monkeypatch.setattr(nse_provider_module, "_new_session", _mock_client_factory(handler))

    provider = NSEProvider()
    candles = provider.get_daily_candles("TCS", lookback_days=1)

    assert len(candles) == 1
    assert candles[0].close == 103.0
    # both the warmup GET and the real API GET happened on the SAME client
    # (the bug's symptom was the second one raising before even being sent).
    assert len(calls) == 2


def test_get_quote_does_not_raise_cannot_open_twice(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(
            200,
            json={
                "priceInfo": {"lastPrice": "2500.5"},
                "metadata": {"lastUpdateTime": "10-Oct-2026 15:30:00"},
            },
        )

    monkeypatch.setattr(nse_provider_module, "_new_session", _mock_client_factory(handler))

    provider = NSEProvider()
    quote = provider.get_quote("TCS")

    assert quote["price"] == 2500.5


def test_get_daily_candles_wraps_http_errors_as_provider_error(monkeypatch):
    monkeypatch.setattr("market_data.base.time.sleep", lambda s: None)  # skip retry backoff

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(503, text="Service Unavailable")

    monkeypatch.setattr(nse_provider_module, "_new_session", _mock_client_factory(handler))

    provider = NSEProvider()
    with pytest.raises(ProviderError):
        provider.get_daily_candles("TCS", lookback_days=1)
