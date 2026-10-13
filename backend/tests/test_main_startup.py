"""Tests for main._load_scheduled_strategies: one corrupt strategy row must
never block the others or crash startup.
"""

from __future__ import annotations

import time

from database import schema
from main import _load_scheduled_strategies


def _insert_strategy_row(conn, strategy_id: str, config_json: str) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT INTO strategies (id, user_id, name, config_json, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (strategy_id, "u", strategy_id, config_json, 1, now, now),
    )


_GOOD_CONFIG = (
    '{"id": "good-1", "user_id": "u", "name": "good", "universe": ["nifty50"], '
    '"instrument_type": "stock", "timeframe": "daily", "conditions": [], "logic": "AND", '
    '"min_consecutive_sessions": 1, "provider": "yfinance", "enabled": true, '
    '"scan_time": "09:00", "scan_days": "daily"}'
)

_BAD_CONFIG = "{not valid json"


class _FakeSchedulerService:
    def __init__(self):
        self.scheduled_ids: list[str] = []

    def add_strategy_job(self, strategy):
        self.scheduled_ids.append(strategy.id)


def test_load_scheduled_strategies_skips_bad_row_schedules_good_row(tmp_db_path):
    schema.init_db()
    conn = schema.conn()
    try:
        _insert_strategy_row(conn, "good-1", _GOOD_CONFIG)
        _insert_strategy_row(conn, "bad-1", _BAD_CONFIG)
    finally:
        conn.close()

    fake_scheduler = _FakeSchedulerService()
    _load_scheduled_strategies(fake_scheduler)  # must not raise

    assert fake_scheduler.scheduled_ids == ["good-1"]
