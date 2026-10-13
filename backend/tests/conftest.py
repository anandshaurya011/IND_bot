import sqlite3  # noqa: F401  (available to tests that need it)

import pytest

import config


@pytest.fixture(autouse=True)
def tmp_db_path(tmp_path, monkeypatch):
    """Point settings.DB_PATH at a per-test temp sqlite file so tests never touch data.db."""
    path = tmp_path / "test.db"
    monkeypatch.setattr(config.settings, "DB_PATH", path)
    return path


@pytest.fixture
def client(tmp_db_path, monkeypatch):
    """TestClient with Clerk auth bypassed via a dependency override.

    Same trick as delta/backend/tests: swap `auth.bind_user` for a fake that
    returns a fixed user id, so tests never need a real Clerk token.
    """
    from fastapi.testclient import TestClient

    from database import schema

    schema.init_db()

    import auth
    import main

    async def _fake_bind_user():
        uid = "test_user"
        auth.user_id_var.set(uid)
        return uid

    main.app.dependency_overrides[auth.bind_user] = _fake_bind_user
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.app.dependency_overrides.clear()
