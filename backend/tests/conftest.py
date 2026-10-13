import sqlite3  # noqa: F401  (available to tests that need it)

import pytest

import config


@pytest.fixture(autouse=True)
def tmp_db_path(tmp_path, monkeypatch):
    """Point settings.DB_PATH at a per-test temp sqlite file so tests never touch data.db."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(config.settings, "DB_PATH", path)
    return path
