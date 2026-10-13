"""API tests using the `client` fixture (Clerk auth bypassed via dependency override)."""

from __future__ import annotations


def _valid_strategy_body(**overrides) -> dict:
    body = dict(
        name="Test Strategy",
        universe=["nifty50"],
        instrument_type="stock",
        timeframe="daily",
        conditions=[
            {"indicator": "ema", "params": {"length": 50}, "comparison": "above", "compare_to": "price"}
        ],
        logic="AND",
        min_consecutive_sessions=1,
        provider="yfinance",
        enabled=False,
        scan_time="09:00",
        scan_days="daily",
    )
    body.update(overrides)
    return body


def test_create_invalid_strategy_returns_400(client):
    body = _valid_strategy_body(provider="nse", timeframe="1h")  # nse has no intraday support
    resp = client.post("/strategies", json=body)
    assert resp.status_code == 400
    assert "intraday" in str(resp.json()).lower() or "errors" in resp.json().get("detail", {})


def test_create_strategy_malformed_scan_time_returns_400_and_not_persisted(client):
    body = _valid_strategy_body(scan_time="25:99")
    resp = client.post("/strategies", json=body)
    assert resp.status_code == 400

    resp = client.get("/strategies")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_strategy_run_now_and_history(client, monkeypatch):
    import scanner.engine as engine_module
    from scanner.engine import ScanResultRow

    def fake_run_scan(strategy):
        return [
            ScanResultRow(
                run_id=None,
                symbol="RELIANCE",
                kind="stock",
                satisfied=True,
                consecutive_sessions=3,
                latest_price=2500.0,
                latest_ts=1760000000,
                indicator_values_json="{}",
                last_candle_date="2026-10-10",
                strategy_name=strategy.name,
            )
        ]

    monkeypatch.setattr(engine_module, "run_scan", fake_run_scan)
    import scheduler.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "run_scan", fake_run_scan)

    body = _valid_strategy_body()
    resp = client.post("/strategies", json=body)
    assert resp.status_code == 200
    strategy = resp.json()
    strategy_id = strategy["id"]

    resp = client.post(f"/strategies/{strategy_id}/run-now")
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    assert run_id is not None

    resp = client.get("/scans", params={"strategy_id": strategy_id})
    assert resp.status_code == 200
    runs = resp.json()
    assert any(r["id"] == run_id for r in runs)

    resp = client.get(f"/scans/{run_id}/results")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["symbol"] == "RELIANCE"


def test_run_now_twice_same_day_returns_two_fresh_runs(client, monkeypatch):
    # Regression: run-now previously shared the scheduled job's once-per-day
    # dedupe slot, so a second click on the same day returned the SAME
    # (stale) run_id instead of actually scanning again.
    import scanner.engine as engine_module
    import scheduler.jobs as jobs_module

    monkeypatch.setattr(engine_module, "run_scan", lambda strategy: [])
    monkeypatch.setattr(jobs_module, "run_scan", lambda strategy: [])

    body = _valid_strategy_body()
    resp = client.post("/strategies", json=body)
    strategy_id = resp.json()["id"]

    run_id_1 = client.post(f"/strategies/{strategy_id}/run-now").json()["run_id"]
    run_id_2 = client.post(f"/strategies/{strategy_id}/run-now").json()["run_id"]

    assert run_id_1 is not None
    assert run_id_2 is not None
    assert run_id_1 != run_id_2

    runs = client.get("/scans", params={"strategy_id": strategy_id}).json()
    assert {r["id"] for r in runs} == {run_id_1, run_id_2}


def test_dashboard_reports_market_status(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market_status"] in ("pre_market", "open", "closed")


def test_universe_lists_known_universes(client):
    resp = client.get("/universe")
    assert resp.status_code == 200
    data = resp.json()
    for name in ("nifty50", "banknifty", "niftyit", "indices", "all_stocks"):
        assert name in data
        assert isinstance(data[name], list)


def test_watchlist_add_list_delete(client):
    resp = client.post("/watchlist", json={"symbol": "RELIANCE"})
    assert resp.status_code == 200

    resp = client.get("/watchlist")
    assert resp.status_code == 200
    symbols = [row["symbol"] for row in resp.json()]
    assert "RELIANCE" in symbols

    resp = client.delete("/watchlist/RELIANCE")
    assert resp.status_code == 200

    resp = client.get("/watchlist")
    symbols = [row["symbol"] for row in resp.json()]
    assert "RELIANCE" not in symbols


def test_settings_telegram_bot_token_configured_flag_independent_of_chat_id(client):
    # Chat id only, no token -> flag must be False.
    resp = client.put("/settings", json={"telegram_chat_id": "12345"})
    assert resp.status_code == 200
    assert resp.json()["telegram_bot_token_configured"] is False

    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_chat_id"] == "12345"
    assert body["telegram_bot_token_configured"] is False

    # Now also set a token -> flag must become True, chat id preserved.
    resp = client.put("/settings", json={"telegram_bot_token": "secret-token"})
    assert resp.status_code == 200
    assert resp.json()["telegram_bot_token_configured"] is True

    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["telegram_chat_id"] == "12345"
    assert body["telegram_bot_token_configured"] is True


def test_unauthenticated_request_rejected():
    """Without the auth override, real Clerk verification kicks in and 500/401s."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as c:
        resp = c.get("/watchlist")
    assert resp.status_code in (401, 500)


def test_get_instrument_candles_returns_404_for_unknown_symbol(client):
    resp = client.get("/instruments/NOT_A_REAL_SYMBOL/candles")
    assert resp.status_code == 404


class _FakeCandleProvider:
    name = "yfinance"

    def get_daily_candles(self, symbol, lookback_days):
        from market_data.base import Candle

        return [
            Candle(ts=1_700_000_000 + i * 86400, open=100, high=101, low=99, close=100 + i, volume=1000)
            for i in range(lookback_days)
        ]


def test_get_instrument_candles_returns_candles_and_no_overlay_without_history(client, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "get_provider", lambda name: _FakeCandleProvider())

    resp = client.get("/instruments/RELIANCE/candles?lookback_days=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "RELIANCE"
    assert len(body["candles"]) == 10
    # no prior satisfied scan result for this user/symbol -> no overlay, not fabricated
    assert body["overlays"] == []


def test_get_instrument_candles_computes_requested_indicator_overlays(client, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "get_provider", lambda name: _FakeCandleProvider())

    resp = client.get("/instruments/RELIANCE/candles?lookback_days=30&indicators=ema:5,sma:5")
    assert resp.status_code == 200
    body = resp.json()
    overlays = {o["indicator"]: o for o in body["overlays"]}
    assert set(overlays) == {"ema", "sma"}
    assert overlays["ema"]["params"] == {"length": 5}
    assert overlays["ema"]["strategy_name"] is None
    assert len(overlays["ema"]["values"]) == 30


def test_get_instrument_candles_rejects_unknown_indicator(client, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "get_provider", lambda name: _FakeCandleProvider())

    resp = client.get("/instruments/RELIANCE/candles?lookback_days=10&indicators=not_a_real_indicator")
    assert resp.status_code == 400


def test_get_instrument_candles_vwap_rolling_overlay_computes_successfully(client, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "get_provider", lambda name: _FakeCandleProvider())

    resp = client.get("/instruments/RELIANCE/candles?lookback_days=30&indicators=vwap_rolling:5")
    assert resp.status_code == 200
    overlays = resp.json()["overlays"]
    assert len(overlays) == 1
    assert overlays[0]["indicator"] == "vwap_rolling"
    assert overlays[0]["params"] == {"days": 5}
    # at least the trailing values should be real numbers, not all null
    # (a days= kwarg mismatch would make every value null/absent instead).
    assert any(v["value"] is not None for v in overlays[0]["values"])


def test_get_instrument_candles_drops_incomplete_trailing_nan_candle(client, monkeypatch):
    import main as main_module
    from market_data.base import Candle

    class _FakeProviderWithTrailingNanCandle:
        name = "yfinance"

        def get_daily_candles(self, symbol, lookback_days):
            candles = [
                Candle(ts=1_700_000_000 + i * 86400, open=100, high=101, low=99, close=100 + i, volume=1000)
                for i in range(9)
            ]
            # yfinance returns a row like this for the in-progress session
            # before today's OHLC is known - only volume is populated.
            candles.append(
                Candle(
                    ts=1_700_000_000 + 9 * 86400,
                    open=float("nan"),
                    high=float("nan"),
                    low=float("nan"),
                    close=float("nan"),
                    volume=500,
                )
            )
            return candles

    monkeypatch.setattr(main_module, "get_provider", lambda name: _FakeProviderWithTrailingNanCandle())

    resp = client.get("/instruments/RELIANCE/candles?lookback_days=10")
    assert resp.status_code == 200  # not a 500 from json.dumps choking on NaN
    body = resp.json()
    assert len(body["candles"]) == 9  # the NaN trailing candle was dropped, not fabricated
    assert all(c["close"] == c["close"] for c in body["candles"])  # no NaN made it through
