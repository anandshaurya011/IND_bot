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


def test_unauthenticated_request_rejected():
    """Without the auth override, real Clerk verification kicks in and 500/401s."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as c:
        resp = c.get("/watchlist")
    assert resp.status_code in (401, 500)
