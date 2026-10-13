"""SQLite schema for the scanner backend. Connection pattern follows delta/backend/store.py."""

import os
import sqlite3
from pathlib import Path

from config import settings

_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS strategies ("
    "id TEXT PRIMARY KEY, user_id TEXT, name TEXT, config_json TEXT, enabled INTEGER, "
    "created_at INTEGER, updated_at INTEGER)",
    "CREATE INDEX IF NOT EXISTS strategies_user ON strategies(user_id)",
    "CREATE TABLE IF NOT EXISTS scan_runs ("
    "id TEXT PRIMARY KEY, user_id TEXT, strategy_id TEXT, started_at INTEGER, finished_at INTEGER, "
    "status TEXT, instruments_scanned INTEGER, matches_count INTEGER, error TEXT)",
    "CREATE INDEX IF NOT EXISTS scan_runs_user ON scan_runs(user_id, started_at)",
    "CREATE TABLE IF NOT EXISTS scan_results ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, kind TEXT, satisfied INTEGER, "
    "consecutive_sessions INTEGER, latest_price REAL, latest_ts INTEGER, indicator_values_json TEXT, "
    "last_candle_date TEXT)",
    "CREATE INDEX IF NOT EXISTS scan_results_run ON scan_results(run_id)",
    "CREATE TABLE IF NOT EXISTS watchlist ("
    "user_id TEXT, symbol TEXT, added_at INTEGER, PRIMARY KEY (user_id, symbol))",
    "CREATE TABLE IF NOT EXISTS scheduler_locks (slot_key TEXT PRIMARY KEY, locked_at INTEGER)",
    "CREATE TABLE IF NOT EXISTS user_settings ("
    "user_id TEXT PRIMARY KEY, telegram_chat_id TEXT, telegram_bot_token_enc TEXT, "
    "active_provider TEXT, updated_at INTEGER)",
]


def conn() -> sqlite3.Connection:
    path = Path(settings.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
    c = sqlite3.connect(path, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    c = conn()
    try:
        for stmt in _SCHEMA:
            c.execute(stmt)
    finally:
        c.close()
