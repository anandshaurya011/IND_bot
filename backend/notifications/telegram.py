"""Telegram notifications for newly-matched scan symbols.

Sends one message per genuinely new match (`current_matches - previous_matches`)
via the Telegram Bot API, using the per-user chat id and bot token stored
(encrypted) in `user_settings`. Never raises: a missing chat id/token is a
no-op, and a failed Telegram API call is logged and swallowed -- a
notification failure must never crash a scan or be reported as sent when it
was not.
"""

from __future__ import annotations

import logging

import httpx

import crypto
from database import schema
from strategies.model import Strategy

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _get_user_telegram_config(user_id: str) -> tuple[str, str] | None:
    """Return (chat_id, bot_token) for `user_id`, or None if not configured."""
    conn = schema.conn()
    try:
        row = conn.execute(
            "SELECT telegram_chat_id, telegram_bot_token_enc FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["telegram_chat_id"] or not row["telegram_bot_token_enc"]:
        return None
    try:
        token = crypto.decrypt(row["telegram_bot_token_enc"])
    except Exception:
        logger.exception("failed to decrypt telegram bot token for user=%s", user_id)
        return None
    return row["telegram_chat_id"], token


def _send_telegram_message(chat_id: str, token: str, text: str) -> None:
    url = TELEGRAM_API_URL.format(token=token)
    try:
        resp = httpx.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        resp.raise_for_status()
    except Exception:
        logger.exception("failed to send telegram notification to chat_id=%s", chat_id)


def notify_new_matches(
    user_id: str,
    strategy: Strategy,
    current_matches: set[str],
    previous_matches: set[str],
) -> None:
    """Notify `user_id` via Telegram about symbols newly matched by `strategy`.

    Only sends for `current_matches - previous_matches`. No-ops (and never
    raises) if the user has no Telegram chat id/token configured, or if the
    Telegram API call fails.
    """
    new_symbols = current_matches - previous_matches
    if not new_symbols:
        return

    config_ = _get_user_telegram_config(user_id)
    if config_ is None:
        return
    chat_id, token = config_

    for symbol in sorted(new_symbols):
        text = f"New match for strategy '{strategy.name}': {symbol}"
        _send_telegram_message(chat_id, token, text)
