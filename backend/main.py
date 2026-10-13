"""
FastAPI backend for the Indian-market scanner.

Every endpoint requires  Authorization: Bearer <Clerk session token>.
Set CLERK_PUBLISHABLE_KEY in backend/.env.

Read/configure only: strategies, watchlist, scan triggers/history. This API
never places trades.

Run:  .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

import auth
import crypto
from database import schema
from indicators import calc
from market_data import get_provider
from market_data.base import ProviderError
from scanner.engine import _INDICATOR_FUNCS, _symbol_for_provider
from scheduler.jobs import SchedulerService
from strategies.model import Strategy
from strategies.persistence import validate_strategy
from instruments.universe import Instrument, list_universe, resolve as resolve_instrument

app = FastAPI(
    title="Indian Market Scanner Backend",
    description="Strategy-based scanner over NSE instruments. Authenticate with a Clerk session token.",
    version="0.1.0",
    dependencies=[Depends(auth.bind_user)],
)

IST = ZoneInfo("Asia/Kolkata")

UNIVERSE_NAMES = ["nifty50", "banknifty", "niftyit", "indices", "all_stocks"]

logger = logging.getLogger(__name__)

scheduler_service: SchedulerService | None = None


def _load_scheduled_strategies(scheduler_service: SchedulerService) -> None:
    """Load every enabled strategy row and schedule it.

    One corrupt/unschedulable row must never block the others or crash
    startup - each strategy's `add_strategy_job` call is isolated in its own
    try/except, logged, and skipped on failure.
    """
    conn = schema.conn()
    try:
        rows = conn.execute("SELECT id, config_json FROM strategies WHERE enabled = 1").fetchall()
    finally:
        conn.close()
    for row in rows:
        try:
            strategy = Strategy.model_validate_json(row["config_json"])
            scheduler_service.add_strategy_job(strategy)
        except Exception:
            logger.exception("failed to schedule strategy id=%s at startup", row["id"])


@app.on_event("startup")
def _startup() -> None:
    global scheduler_service
    schema.init_db()
    scheduler_service = SchedulerService()
    _load_scheduled_strategies(scheduler_service)


@app.on_event("shutdown")
def _shutdown() -> None:
    if scheduler_service is not None:
        scheduler_service.shutdown()


def _set_enabled(strategy_id: str, user_id: str, enabled: bool) -> None:
    conn = schema.conn()
    try:
        conn.execute(
            "UPDATE strategies SET enabled = ? WHERE id = ? AND user_id = ?",
            (int(enabled), strategy_id, user_id),
        )
    finally:
        conn.close()


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


@app.get("/instruments/{symbol}/candles")
def get_instrument_candles(
    symbol: str,
    provider: str = Query("yfinance"),
    lookback_days: int = Query(180, ge=5, le=2000),
    indicators: str = Query(
        "",
        description=(
            "Comma-separated indicator specs to overlay, e.g. 'ema:20,vwma:50,rsi:14'. "
            "A bare name (no ':length') uses that indicator's default params. "
            "If omitted, falls back to the indicator from the most recent strategy "
            "that matched this symbol for the authenticated user, if any."
        ),
    ),
):
    """Historical daily candles for one instrument, plus indicator overlays
    for charting. Never fabricates data: a provider failure is surfaced as
    a 502, not a guessed candle series; an unknown/invalid indicator spec
    is surfaced as a 400, not silently dropped.
    """
    uid = auth.user_id_var.get()
    instrument = resolve_instrument(symbol)
    if instrument is None:
        raise HTTPException(404, f"unknown instrument {symbol!r}")

    provider_obj = get_provider(provider)
    provider_symbol = _symbol_for_provider(instrument, provider)
    try:
        candles = provider_obj.get_daily_candles(provider_symbol, lookback_days=lookback_days)
    except ProviderError as exc:
        raise HTTPException(502, f"could not fetch candle data: {exc}") from exc

    candle_rows = [
        {"ts": c.ts, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
        for c in candles
    ]

    df = calc.to_dataframe(candles)

    specs = [s.strip() for s in indicators.split(",") if s.strip()]
    if specs:
        overlays = []
        for spec in specs:
            name, params = _parse_indicator_spec(spec)
            if name not in _INDICATOR_FUNCS:
                raise HTTPException(
                    400, f"unknown indicator {name!r}; must be one of {sorted(_INDICATOR_FUNCS)}"
                )
            overlay = _compute_overlay(df, name, params, strategy_name=None)
            if overlay is not None:
                overlays.append(overlay)
    else:
        overlays = []
        auto = _last_matching_overlay(uid, symbol, df)
        if auto is not None:
            overlays.append(auto)

    return {
        "symbol": symbol,
        "instrument": instrument,
        "provider": provider,
        "candles": candle_rows,
        "overlays": overlays,
    }


def _parse_indicator_spec(spec: str) -> tuple[str, dict]:
    """Parse "name" or "name:N" (same convention and same `days`-for-
    vwap_rolling exception as strategies' compare_to specs - see
    scanner.engine._parse_spec / _SPEC_PARAM_NAME).
    """
    from scanner.engine import _SPEC_PARAM_NAME

    if ":" in spec:
        name, _, raw_param = spec.partition(":")
        name = name.strip()
        try:
            value = int(raw_param)
        except ValueError:
            raise HTTPException(400, f"indicator spec {spec!r}: parameter must be an integer") from None
        param_name = _SPEC_PARAM_NAME.get(name, "length")
        return name, {param_name: value}
    return spec.strip(), {}


def _compute_overlay(df, indicator: str, params: dict, strategy_name: str | None) -> dict | None:
    """Compute one indicator's series over `df` as a chart-overlay payload.
    Returns None if the indicator can't be computed - never fabricates a line.
    """
    func = _INDICATOR_FUNCS.get(indicator)
    if func is None:
        return None
    try:
        series = func(df, **params)
    except Exception:  # noqa: BLE001 - overlay is best-effort, never breaks the chart
        return None
    if hasattr(series, "iloc") and series.ndim > 1:
        # Multi-column indicator output (e.g. macd/bollinger/supertrend) -
        # use its first column as the overlay line.
        series = series.iloc[:, 0]

    values = [
        {"ts": int(ts.timestamp()), "value": None if value != value else float(value)}  # NaN check
        for ts, value in series.items()
    ]

    return {
        "indicator": indicator,
        "params": params,
        "strategy_name": strategy_name,
        "values": values,
    }


def _last_matching_overlay(user_id: str, symbol: str, df) -> dict | None:
    """Find the most recent `satisfied=1` scan result for this user/symbol,
    load the strategy that produced it, and compute that strategy's first
    condition's indicator series over `df` for a chart overlay. Returns None
    if there's no matching history - never fabricates an overlay.
    """
    conn = schema.conn()
    try:
        row = conn.execute(
            "SELECT sr.run_id, srun.strategy_id, srun.started_at "
            "FROM scan_results sr JOIN scan_runs srun ON sr.run_id = srun.id "
            "WHERE srun.user_id = ? AND sr.symbol = ? AND sr.satisfied = 1 "
            "ORDER BY srun.started_at DESC LIMIT 1",
            (user_id, symbol),
        ).fetchone()
        if row is None:
            return None
        strategy_row = conn.execute(
            "SELECT config_json FROM strategies WHERE id = ? AND user_id = ?",
            (row["strategy_id"], user_id),
        ).fetchone()
    finally:
        conn.close()

    if strategy_row is None:
        return None

    strategy = Strategy.model_validate_json(strategy_row["config_json"])
    if not strategy.conditions:
        return None
    condition = strategy.conditions[0]

    return _compute_overlay(df, condition.indicator, condition.params, strategy.name)


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
        try:
            scheduler_service.add_strategy_job(strategy)
        except Exception:
            logger.exception("failed to schedule strategy id=%s on create", strategy.id)
            _set_enabled(strategy.id, uid, False)
            raise HTTPException(500, "Strategy saved but could not be scheduled")

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
            try:
                scheduler_service.add_strategy_job(strategy)
            except Exception:
                logger.exception("failed to schedule strategy id=%s on update", strategy.id)
                _set_enabled(strategy.id, uid, False)
                raise HTTPException(500, "Strategy saved but could not be scheduled")
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
    uid = auth.user_id_var.get()
    conn = schema.conn()
    try:
        run_row = conn.execute(
            "SELECT id FROM scan_runs WHERE id = ? AND user_id = ?", (run_id, uid)
        ).fetchone()
        if run_row is None:
            raise HTTPException(404, "Unknown scan run")
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
            "SELECT telegram_chat_id, telegram_bot_token_enc, active_provider, updated_at "
            "FROM user_settings WHERE user_id = ?",
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
        "telegram_bot_token_configured": bool(row["telegram_bot_token_enc"]),
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
