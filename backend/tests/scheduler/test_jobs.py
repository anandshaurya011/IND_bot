from datetime import datetime
from zoneinfo import ZoneInfo

from database import schema
from scheduler.jobs import (
    SchedulerService,
    run_scheduled_scan,
    slot_key,
    try_acquire_slot,
)
from strategies.model import Condition, Strategy

IST = ZoneInfo("Asia/Kolkata")


def _sample_strategy(**overrides) -> Strategy:
    defaults = dict(
        id="strat1",
        user_id="user1",
        name="Test Strategy",
        universe=["nifty50"],
        instrument_type="stock",
        timeframe="1d",
        conditions=[
            Condition(indicator="ema", params={"length": 50}, comparison="above", compare_to="price")
        ],
        logic="AND",
        min_consecutive_sessions=1,
        provider="yfinance",
        enabled=True,
        scan_time="09:00",
        scan_days="daily",
    )
    defaults.update(overrides)
    return Strategy(**defaults)


def test_slot_key_is_per_strategy_per_ist_calendar_day():
    t = datetime(2026, 10, 13, 3, 30, tzinfo=ZoneInfo("UTC"))  # 09:00 IST
    assert slot_key("strat1", t) == "strat1:2026-10-13"


def test_try_acquire_slot_only_succeeds_once(tmp_db_path):
    schema.init_db()
    assert try_acquire_slot("strat1:2026-10-13") is True
    assert try_acquire_slot("strat1:2026-10-13") is False


def test_run_scheduled_scan_skips_if_slot_already_taken(tmp_db_path, monkeypatch):
    schema.init_db()
    calls = []
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: calls.append(s) or [])
    strategy = _sample_strategy()
    run_scheduled_scan(strategy)
    run_scheduled_scan(strategy)  # simulates restart re-firing same day's job
    assert len(calls) == 1


def test_run_scheduled_scan_writes_scan_run_and_results(tmp_db_path, monkeypatch):
    schema.init_db()
    from scanner.engine import ScanResultRow

    row = ScanResultRow(
        run_id=None,
        symbol="OK",
        kind="stock",
        satisfied=True,
        consecutive_sessions=3,
        latest_price=101.5,
        latest_ts=1_700_000_000,
        indicator_values_json="{}",
        last_candle_date="2026-10-13",
        strategy_name="Test Strategy",
    )
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: [row])
    strategy = _sample_strategy()
    run_scheduled_scan(strategy)

    conn = schema.conn()
    try:
        runs = conn.execute("SELECT * FROM scan_runs WHERE strategy_id = ?", (strategy.id,)).fetchall()
        assert len(runs) == 1
        assert runs[0]["status"] == "ok"
        assert runs[0]["matches_count"] == 1

        results = conn.execute(
            "SELECT * FROM scan_results WHERE run_id = ?", (runs[0]["id"],)
        ).fetchall()
        assert len(results) == 1
        assert results[0]["symbol"] == "OK"
    finally:
        conn.close()


def test_scheduler_service_add_and_next_run_time(tmp_db_path):
    schema.init_db()
    strategy = _sample_strategy()
    service = SchedulerService()
    try:
        service.add_strategy_job(strategy)
        next_run = service.next_run_time(strategy.id)
        assert next_run is not None
        assert next_run.tzinfo is not None
    finally:
        service.shutdown()


def test_scheduler_service_remove_job_is_safe_when_absent(tmp_db_path):
    schema.init_db()
    service = SchedulerService()
    try:
        service.remove_strategy_job("does-not-exist")
    finally:
        service.shutdown()


def test_run_now_does_not_dedupe_against_same_day_slot(tmp_db_path, monkeypatch):
    # Regression: run_now previously shared run_scheduled_scan's
    # once-per-IST-day slot, so a second manual "Run Now" click on the same
    # day silently did nothing and the API returned the FIRST run's stale
    # id - clicking "Run Now" must always scan fresh.
    schema.init_db()
    calls = []
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: calls.append(s) or [])
    strategy = _sample_strategy()
    service = SchedulerService()
    try:
        service.run_now(strategy)
        service.run_now(strategy)
        assert len(calls) == 2
    finally:
        service.shutdown()


def test_run_now_returns_a_fresh_run_id_each_call(tmp_db_path, monkeypatch):
    schema.init_db()
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: [])
    strategy = _sample_strategy()
    service = SchedulerService()
    try:
        run_id_1 = service.run_now(strategy)
        run_id_2 = service.run_now(strategy)
        assert run_id_1 is not None
        assert run_id_2 is not None
        assert run_id_1 != run_id_2

        conn = schema.conn()
        try:
            runs = conn.execute(
                "SELECT id FROM scan_runs WHERE strategy_id = ? ORDER BY started_at", (strategy.id,)
            ).fetchall()
        finally:
            conn.close()
        assert [r["id"] for r in runs] == [run_id_1, run_id_2]
    finally:
        service.shutdown()


def test_run_now_still_works_after_the_scheduled_slot_is_taken(tmp_db_path, monkeypatch):
    schema.init_db()
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: [])
    strategy = _sample_strategy()

    # Simulate today's scheduled (cron) run having already claimed the slot.
    now = datetime.now(IST)
    assert try_acquire_slot(slot_key(strategy.id, now)) is True

    service = SchedulerService()
    try:
        run_id = service.run_now(strategy)
        assert run_id is not None
    finally:
        service.shutdown()


def test_run_scheduled_scan_returns_none_when_slot_already_taken(tmp_db_path, monkeypatch):
    schema.init_db()
    monkeypatch.setattr("scheduler.jobs.run_scan", lambda s: [])
    strategy = _sample_strategy()
    assert run_scheduled_scan(strategy) is not None
    assert run_scheduled_scan(strategy) is None  # same-day re-fire is a no-op
