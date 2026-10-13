from market_data.base import Candle, Provider, ProviderError, cache_candles, with_retry


class _FakeProvider(Provider):
    def get_daily_candles(self, symbol, lookback_days):
        return [Candle(ts=1700000000, open=100, high=101, low=99, close=100.5, volume=1000)]

    def get_intraday_candles(self, symbol, interval, lookback_days):
        raise ProviderError("intraday_unsupported")

    def get_quote(self, symbol):
        return {"price": 100.5, "ts": 1700000000, "is_stale": False}


def test_fake_provider_round_trip():
    p = _FakeProvider()
    candles = p.get_daily_candles("RELIANCE.NS", 30)
    assert candles[0].close == 100.5
    try:
        p.get_intraday_candles("RELIANCE.NS", "5m", 1)
        assert False, "should have raised"
    except ProviderError as e:
        assert str(e) == "intraday_unsupported"


def test_with_retry_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("market_data.base.time.sleep", lambda *_args, **_kwargs: None)

    calls = {"count": 0}

    @with_retry(max_attempts=3, backoff_base=1.5)
    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ProviderError("transient")
        return "success"

    assert flaky() == "success"
    assert calls["count"] == 3


def test_cache_candles_hits_and_misses():
    calls = {"count": 0}

    @cache_candles(ttl=60)
    def fetch(symbol):
        calls["count"] += 1
        return f"data-for-{symbol}"

    assert fetch("RELIANCE.NS") == "data-for-RELIANCE.NS"
    assert fetch("RELIANCE.NS") == "data-for-RELIANCE.NS"
    assert calls["count"] == 1

    assert fetch("TCS.NS") == "data-for-TCS.NS"
    assert calls["count"] == 2
