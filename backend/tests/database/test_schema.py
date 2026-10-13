import sqlite3

from database import schema

EXPECTED_TABLES = {"strategies", "scan_runs", "scan_results", "watchlist", "scheduler_locks"}


def test_init_db_creates_all_tables():
    schema.init_db()
    c = schema.conn()
    try:
        names = {r["name"] for r in c.execute("select name from sqlite_master where type='table'")}
    finally:
        c.close()
    assert EXPECTED_TABLES <= names


def test_init_db_is_idempotent():
    schema.init_db()
    schema.init_db()


def test_conn_uses_row_factory_and_creates_file_0600(tmp_db_path):
    assert not tmp_db_path.exists()
    c = schema.conn()
    try:
        assert c.row_factory is sqlite3.Row
        assert tmp_db_path.exists()
        assert tmp_db_path.stat().st_mode & 0o777 == 0o600
    finally:
        c.close()
