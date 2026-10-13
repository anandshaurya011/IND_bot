import crypto
from database import schema
from notifications import telegram
from strategies.model import Strategy


def _make_strategy() -> Strategy:
    return Strategy(
        id="strat1",
        user_id="user1",
        name="Test Strategy",
        universe=["nifty50"],
        instrument_type="stock",
        timeframe="1d",
        conditions=[],
        logic="AND",
        min_consecutive_sessions=1,
        provider="yfinance",
        enabled=True,
    )


def _configure_telegram(user_id: str, chat_id: str = "12345", token: str = "fake-token") -> None:
    conn = schema.conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_settings "
            "(user_id, telegram_chat_id, telegram_bot_token_enc, active_provider, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, crypto.encrypt(token), "yfinance", 0),
        )
    finally:
        conn.close()


def test_sends_only_for_genuinely_new_symbols(monkeypatch):
    schema.init_db()
    _configure_telegram("user1")
    strategy = _make_strategy()

    sent = []

    def fake_send(chat_id, token, text):
        sent.append((chat_id, token, text))

    monkeypatch.setattr(telegram, "_send_telegram_message", fake_send)

    telegram.notify_new_matches(
        "user1", strategy, current_matches={"RELIANCE", "TCS", "INFY"}, previous_matches={"TCS"}
    )

    sent_symbols = {s[2].split(": ")[-1] for s in sent}
    assert sent_symbols == {"RELIANCE", "INFY"}
    assert len(sent) == 2


def test_no_op_when_matches_unchanged(monkeypatch):
    schema.init_db()
    _configure_telegram("user1")
    strategy = _make_strategy()

    sent = []
    monkeypatch.setattr(telegram, "_send_telegram_message", lambda *a: sent.append(a))

    telegram.notify_new_matches(
        "user1", strategy, current_matches={"RELIANCE", "TCS"}, previous_matches={"RELIANCE", "TCS"}
    )

    assert sent == []


def test_no_op_when_user_has_no_telegram_config(monkeypatch):
    schema.init_db()
    strategy = _make_strategy()

    sent = []
    monkeypatch.setattr(telegram, "_send_telegram_message", lambda *a: sent.append(a))

    telegram.notify_new_matches("user1", strategy, current_matches={"RELIANCE"}, previous_matches=set())

    assert sent == []


def test_does_not_raise_when_telegram_api_call_fails(monkeypatch):
    schema.init_db()
    _configure_telegram("user1")
    strategy = _make_strategy()

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(telegram.httpx, "post", boom)

    # Should not raise.
    telegram.notify_new_matches("user1", strategy, current_matches={"RELIANCE"}, previous_matches=set())
