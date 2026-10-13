from market_data.base import Candle, Provider, ProviderError


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
