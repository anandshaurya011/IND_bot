"""
FastAPI backend for the Indian-market scanner.

Every endpoint requires  Authorization: Bearer <Clerk session token>.
Set CLERK_PUBLISHABLE_KEY in backend/.env.

Read/configure only: strategies, watchlist, scan triggers/history. This API
never places trades.

Run:  .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

import auth
import crypto
from database import schema
from scheduler.jobs import SchedulerService
from strategies.model import Strategy
from strategies.persistence import validate_strategy
from instruments.universe import Instrument, list_universe

app = FastAPI(
    title="Indian Market Scanner Backend",
    description="Strategy-based scanner over NSE instruments. Authenticate with a Clerk session token.",
    version="0.1.0",
    dependencies=[Depends(auth.bind_user)],
)

IST = ZoneInfo("Asia/Kolkata")

UNIVERSE_NAMES = ["nifty50", "banknifty", "niftyit", "indices", "all_stocks"]

scheduler_service: SchedulerService | None = None


@app.on_event("startup")
def _startup() -> None:
    global scheduler_service
    schema.init_db()
    scheduler_service = SchedulerService()
    conn = schema.conn()
    try:
        rows = conn.execute("SELECT config_json FROM strategies WHERE enabled = 1").fetchall()
    finally:
        conn.close()
    for row in rows:
        strategy = Strategy.model_validate_json(row["config_json"])
        scheduler_service.add_strategy_job(strategy)


@app.on_event("shutdown")
def _shutdown() -> None:
    if scheduler_service is not None:
        scheduler_service.shutdown()


def _row_to_strategy(row) -> Strategy:
    return Strategy.model_validate_json(row["config_json"])


def _get_strategy_or_404(strategy_id: str, user_id: str) -> Strategy:
    conn = schema.conn()
    try:
        row = conn.execute(
            "SELECT config_json FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, user_id)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "Unknown strategy")
    return _row_to_strategy(row)


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------

class StrategyIn(BaseModel):
    name: str
    universe: list[str]
    instrument_type: str
    timeframe: str
    conditions: list[dict]
    logic: str
    min_consecutive_sessions: int
    provider: str
    enabled: bool
    scan_time: str = "09:00"
    scan_days: list[int] | str = "daily"


class WatchlistIn(BaseModel):
    symbol: str


class SettingsIn(BaseModel):
    telegram_chat_id: str | None = None
    telegram_bot_token: str | None = None
    active_provider: str | None = None


# --------------------------------------------------------------------------
# Universe
# --------------------------------------------------------------------------

@app.get("/universe")
def get_universe() -> dict[str, list[Instrument]]:
    return {name: list_universe(name) for name in UNIVERSE_NAMES}


# --------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------

@app.get("/watchlist")
def get_watchlist():
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        rows = conn.execute(
            "SELECT symbol, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at", (uid,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.post("/watchlist")
def post_watchlist(body: WatchlistIn):
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, symbol, added_at) VALUES (?, ?, ?)",
            (uid, body.symbol, int(time.time())),
        )
    finally:
        conn.close()
    return {"symbol": body.symbol}


@app.delete("/watchlist/{symbol}")
def delete_watchlist(symbol: str):
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        conn.execute("DELETE FROM watchlist WHERE user_id = ? AND symbol = ?", (uid, symbol))
    finally:
        conn.close()
    return {"deleted": symbol}


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

@app.get("/strategies")
def get_strategies():
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        rows = conn.execute("SELECT config_json FROM strategies WHERE user_id = ?", (uid,)).fetchall()
    finally:
        conn.close()
    return [_row_to_strategy(r) for r in rows]


@app.post("/strategies")
def post_strategies(body: StrategyIn):
    uid = auth.user_id_var.get()
    strategy = Strategy(id=uuid.uuid4().hex, user_id=uid, **body.model_dump())
    errors = validate_strategy(strategy)
    if errors:
        raise HTTPException(400, {"errors": errors})

    now = int(time.time())
    conn = schema.conn()
    try:
        conn.execute(
            "INSERT INTO strategies (id, user_id, name, config_json, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (strategy.id, uid, strategy.name, strategy.model_dump_json(), int(strategy.enabled), now, now),
        )
    finally:
        conn.close()

    if strategy.enabled and scheduler_service is not None:
        scheduler_service.add_strategy_job(strategy)

    return strategy


@app.put("/strategies/{strategy_id}")
def put_strategies(strategy_id: str, body: StrategyIn):
    uid = auth.user_id_var.get()
    _get_strategy_or_404(strategy_id, uid)  # 404 if missing / not owned

    strategy = Strategy(id=strategy_id, user_id=uid, **body.model_dump())
    errors = validate_strategy(strategy)
    if errors:
        raise HTTPException(400, {"errors": errors})

    conn = schema.conn()
    try:
        conn.execute(
            "UPDATE strategies SET name = ?, config_json = ?, enabled = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (strategy.name, strategy.model_dump_json(), int(strategy.enabled), int(time.time()), strategy_id, uid),
        )
    finally:
        conn.close()

    if scheduler_service is not None:
        if strategy.enabled:
            scheduler_service.add_strategy_job(strategy)
        else:
            scheduler_service.remove_strategy_job(strategy_id)

    return strategy


@app.delete("/strategies/{strategy_id}")
def delete_strategies(strategy_id: str):
    uid = auth.user_id_var.get()
    _get_strategy_or_404(strategy_id, uid)

    conn = schema.conn()
    try:
        conn.execute("DELETE FROM strategies WHERE id = ? AND user_id = ?", (strategy_id, uid))
    finally:
        conn.close()

    if scheduler_service is not None:
        scheduler_service.remove_strategy_job(strategy_id)

    return {"deleted": strategy_id}


@app.post("/strategies/{strategy_id}/run-now")
def run_now(strategy_id: str):
    uid = auth.user_id_var.get()
    strategy = _get_strategy_or_404(strategy_id, uid)
    if scheduler_service is None:
        raise HTTPException(500, "Scheduler not initialized")
    scheduler_service.run_now(strategy)

    conn = schema.conn()
    try:
        row = conn.execute(
            "SELECT id FROM scan_runs WHERE strategy_id = ? ORDER BY started_at DESC LIMIT 1",
            (strategy_id,),
        ).fetchone()
    finally:
        conn.close()
    return {"run_id": row["id"] if row else None}


# --------------------------------------------------------------------------
# Scans
# --------------------------------------------------------------------------

@app.get("/scans")
def get_scans(strategy_id: str | None = None, limit: int = Query(50, ge=1, le=500)):
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        if strategy_id:
            rows = conn.execute(
                "SELECT * FROM scan_runs WHERE user_id = ? AND strategy_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (uid, strategy_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scan_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ?",
                (uid, limit),
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@app.get("/scans/{run_id}/results")
def get_scan_results(run_id: str):
    conn = schema.conn()
    try:
        rows = conn.execute("SELECT * FROM scan_results WHERE run_id = ?", (run_id,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

@app.get("/settings")
def get_settings():
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        row = conn.execute(
            "SELECT telegram_chat_id, active_provider, updated_at FROM user_settings WHERE user_id = ?",
            (uid,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {
            "telegram_chat_id": None,
            "telegram_bot_token_configured": False,
            "active_provider": None,
            "updated_at": None,
        }
    return {
        "telegram_chat_id": row["telegram_chat_id"],
        "telegram_bot_token_configured": bool(row["telegram_chat_id"]),
        "active_provider": row["active_provider"],
        "updated_at": row["updated_at"],
    }


@app.put("/settings")
def put_settings(body: SettingsIn):
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        existing = conn.execute(
            "SELECT telegram_chat_id, telegram_bot_token_enc, active_provider FROM user_settings WHERE user_id = ?",
            (uid,),
        ).fetchone()

        telegram_chat_id = (
            body.telegram_chat_id if body.telegram_chat_id is not None
            else (existing["telegram_chat_id"] if existing else None)
        )
        if body.telegram_bot_token is not None:
            telegram_bot_token_enc = crypto.encrypt(body.telegram_bot_token)
        else:
            telegram_bot_token_enc = existing["telegram_bot_token_enc"] if existing else None
        active_provider = (
            body.active_provider if body.active_provider is not None
            else (existing["active_provider"] if existing else None)
        )

        conn.execute(
            "INSERT INTO user_settings (user_id, telegram_chat_id, telegram_bot_token_enc, "
            "active_provider, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET telegram_chat_id = excluded.telegram_chat_id, "
            "telegram_bot_token_enc = excluded.telegram_bot_token_enc, "
            "active_provider = excluded.active_provider, updated_at = excluded.updated_at",
            (uid, telegram_chat_id, telegram_bot_token_enc, active_provider, int(time.time())),
        )
    finally:
        conn.close()

    return {
        "telegram_chat_id": telegram_chat_id,
        "telegram_bot_token_configured": bool(telegram_bot_token_enc),
        "active_provider": active_provider,
    }


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

def _market_status(now: datetime) -> str:
    open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if now < open_t:
        return "pre_market"
    if now <= close_t:
        return "open"
    return "closed"


@app.get("/dashboard")
def get_dashboard():
    uid = auth.user_id_var.get()
    now = datetime.now(IST)
    market_status = _market_status(now)

    conn = schema.conn()
    try:
        strategy_rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id = ? AND enabled = 1", (uid,)
        ).fetchall()

        strategies = []
        for srow in strategy_rows:
            strategy = Strategy.model_validate_json(srow["config_json"])
            last_run = conn.execute(
                "SELECT * FROM scan_runs WHERE strategy_id = ? ORDER BY started_at DESC LIMIT 1",
                (strategy.id,),
            ).fetchone()
            next_run = scheduler_service.next_run_time(strategy.id) if scheduler_service else None
            strategies.append(
                {
                    "strategy_id": strategy.id,
                    "name": strategy.name,
                    "last_run": dict(last_run) if last_run else None,
                    "next_run_time": next_run.isoformat() if next_run else None,
                }
            )
    finally:
        conn.close()

    return {
        "market_status": market_status,
        "strategies": strategies,
    }
