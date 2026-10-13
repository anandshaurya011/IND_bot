# Stock & Index Scanner — Backend MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI backend that scans NSE stocks/indices against user-defined technical-indicator strategies, persists results, and runs on a daily schedule — the data/logic layer the frontend (separate plan) will call.

**Architecture:** Mirror `/home/anand-shaurya/Documents/personal/delta/backend`: a FastAPI app (`main.py`) with Clerk JWT auth (`auth.py`), encrypted per-user settings in SQLite (`store.py` + `crypto.py`). New domain modules: `market_data/` (provider abstraction: yfinance + NSE India, switchable), `instruments/` (symbol master for Nifty50/BankNifty/NiftyIT/etc.), `indicators/` (EMA/SMA/VWAP/RSI/MACD/SuperTrend/ADX/Bollinger via pandas + pandas-ta), `scanner/` (strategy evaluation incl. N-session persistence), `strategies/` (CRUD for saved rules), `scheduler/` (APScheduler, Asia/Kolkata, dedupe + run-now), `database/` (schema + migrations layered on `store.py`'s sqlite3 pattern).

**Tech Stack:** Python 3.11+, FastAPI, pydantic, APScheduler, pandas, pandas-ta, yfinance, httpx (NSE endpoints), sqlite3, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-stock-scanner-spec.md`

## Global Constraints

- Timezone for scheduling and session-day logic is always `Asia/Kolkata` — never system local time, never UTC-naive.
- Never fabricate a price or indicator value; if a provider returns nothing usable, the result row must say so (`stale`/`missing`), not a guessed number.
- Persistence counts ("N consecutive sessions") count actual trading sessions only — a missing/holiday session never counts as satisfying or breaking the streak silently; it must be explicitly reconciled against the exchange calendar.
- Every endpoint requires a Clerk-verified user (`Depends(auth.bind_user)` at the app level, exactly as `delta/backend/main.py` does) — no shared/operator credentials.
- No automatic order placement anywhere in this codebase — scanner output is read-only data.
- Provider choice (yfinance vs NSE endpoints) is a per-user Settings value, stored encrypted/plain like other user settings in `store.py`, and the scanner must work (degrade gracefully, not crash) if one provider is down.

## Review Focus

- NSE holiday / no-trading day: a scan scheduled for a market holiday must not treat the absence of a new candle as a broken streak or a crash — pins to Task 4 (persistence) and Task 7 (scheduler) tests.
- Symbol delisted or renamed mid-universe scan: the scanner must skip and flag that instrument rather than aborting the whole scan — pins to Task 2 (instruments) and Task 5 (scanner loop) tests.
- Both data providers unreachable at scan time: the scan must complete with all instruments marked stale/missing, not throw an unhandled exception that drops the whole run — pins to Task 1 (provider abstraction) and Task 6 (scanner run) tests.
- Intraday VWAP requested on a provider that only has daily candles: strategy validation must reject this combination with a clear error before scheduling, not silently fall back to daily — pins to Task 3 (indicators) and Task 4 (strategy validation) tests.
- Scheduler fires twice for the same slot (process restart right at 9:00 AM): the second trigger must be a no-op, not a duplicate scan row — pins to Task 7 (scheduler dedupe) tests.

---

## Task 0: Project scaffolding

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/.env.example`
- Create: `backend/pytest.ini`
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `config.Settings` object (fields: `CLERK_PUBLISHABLE_KEY: str`, `DB_PATH: Path`, `DEFAULT_TZ: str = "Asia/Kolkata"`, `DEFAULT_SCAN_TIME: str = "09:00"`), importable as `from config import settings`.

- [ ] **Step 1:** Write `backend/requirements.txt`:
```
fastapi
uvicorn
python-dotenv
pyjwt[crypto]
cryptography
httpx
pytest
pandas
pandas-ta
yfinance
apscheduler
```
- [ ] **Step 2:** Write `backend/config.py` loading `.env` via `python-dotenv`, exposing a module-level `settings` instance (plain class, not pydantic — matches the Delta backend's lightweight style). Fields above, with `DB_PATH` defaulting to `Path(__file__).resolve().parent / "data.db"`.
- [ ] **Step 3:** Write `backend/.env.example` with `CLERK_PUBLISHABLE_KEY=`.
- [ ] **Step 4:** Write `backend/tests/conftest.py` with a `tmp_db_path` fixture that points `config.settings.DB_PATH` at a `tmp_path` sqlite file for every test (so tests never touch the real `data.db`).
- [ ] **Step 5:** `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt`
- [ ] **Step 6:** Commit.
```bash
git init  # if not already a repo
git add backend/requirements.txt backend/config.py backend/.env.example backend/tests/conftest.py
git commit -m "chore: scaffold scanner backend"
```

---

## Task 1: Market data provider abstraction

**Files:**
- Create: `backend/market_data/__init__.py`
- Create: `backend/market_data/base.py`
- Create: `backend/market_data/yfinance_provider.py`
- Create: `backend/market_data/nse_provider.py`
- Create: `backend/tests/market_data/test_base.py`

**Interfaces:**
- Produces: `Candle` dataclass (`ts: int` epoch seconds, `open: float`, `high: float`, `low: float`, `close: float`, `volume: int`), `ProviderError(Exception)`, abstract `Provider` with `def get_daily_candles(self, symbol: str, lookback_days: int) -> list[Candle]` and `def get_intraday_candles(self, symbol: str, interval: str, lookback_days: int) -> list[Candle]` (raises `ProviderError("intraday_unsupported")` if the provider can't do intraday), `def get_quote(self, symbol: str) -> dict` (keys `price`, `ts`, `is_stale: bool`). `PROVIDERS: dict[str, Provider]` registry keyed `"yfinance"` / `"nse"`.

- [ ] **Step 1: Write the failing test** (`backend/tests/market_data/test_base.py`):
```python
from market_data.base import Candle, Provider, ProviderError


class _FakeProvider(Provider):
    def get_daily_candles(self, symbol, lookback_days):
        return [Candle(ts=1700000000, open=100, high=101, low=99, close=100.5, volume=1000)]

    def get_intraday_candles(self, symbol, interval, lookback_days):
        raise ProviderError("intraday_unsupported")

    def get_quote(self, symbol):
        return {"price": 100.5, "ts": 1700000000, "is_stale": False}


def test_fake_provider_round_trip():
    p = _FakeProvider()
    candles = p.get_daily_candles("RELIANCE.NS", 30)
    assert candles[0].close == 100.5
    try:
        p.get_intraday_candles("RELIANCE.NS", "5m", 1)
        assert False, "should have raised"
    except ProviderError as e:
        assert str(e) == "intraday_unsupported"
```
- [ ] **Step 2: Run test to verify it fails** — `pytest tests/market_data/test_base.py -v` → FAIL (`market_data.base` doesn't exist).
- [ ] **Step 3: Implement `backend/market_data/base.py`:**
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: int


class ProviderError(Exception):
    pass


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def get_daily_candles(self, symbol: str, lookback_days: int) -> list[Candle]: ...

    @abstractmethod
    def get_intraday_candles(self, symbol: str, interval: str, lookback_days: int) -> list[Candle]: ...

    @abstractmethod
    def get_quote(self, symbol: str) -> dict: ...
```
- [ ] **Step 4: Run test to verify it passes** — PASS.
- [ ] **Step 5: Write `backend/market_data/yfinance_provider.py`** implementing `Provider` with `yfinance.Ticker(symbol).history(period=...)`; `.NS` suffix for NSE stocks, `^NSEI`/`^NSEBANK`/`^CNXIT` for indices; `get_intraday_candles` uses `interval="5m"/"15m"/"1h"` via `yfinance` (raise `ProviderError("intraday_unsupported")` only if yfinance itself errors/returns empty — don't pre-emptively disable it, yfinance does support limited intraday); wrap all network calls in try/except re-raising as `ProviderError(str(e))`; mark `get_quote`'s `is_stale=True` when the latest candle's `ts` is more than 1 trading day old.
- [ ] **Step 6: Write `backend/market_data/nse_provider.py`** implementing `Provider` against NSE India's public JSON endpoints (`https://www.nseindia.com/api/...`) using `httpx` with required browser-like headers and a cookie-warmup request (NSE blocks bare requests); raise `ProviderError("intraday_unsupported")` from `get_intraday_candles` since the public endpoints only expose EOD history reliably; add a module docstring documenting this limitation.
- [ ] **Step 7: Write `backend/market_data/__init__.py`** exporting `PROVIDERS = {"yfinance": YFinanceProvider(), "nse": NSEProvider()}` and `def get_provider(name: str) -> Provider`.
- [ ] **Step 8: Add retry/backoff + cache.** In `base.py` add `@with_retry(max_attempts=3, backoff_base=1.5)` decorator (plain `time.sleep` loop, no new dependency) and apply it to both providers' network-calling methods; add a simple in-process TTL cache (`functools` + dict keyed on `(symbol, kind, params)`, 60s TTL for quotes, 1h TTL for daily candles) in `base.py` as `cache_candles(ttl)` decorator, applied in both providers.
- [ ] **Step 9: Run full test suite** — `pytest tests/market_data -v` → PASS.
- [ ] **Step 10: Commit.**
```bash
git add backend/market_data backend/tests/market_data
git commit -m "feat: add market data provider abstraction (yfinance + NSE)"
```

---

## Task 2: Instrument master

**Files:**
- Create: `backend/instruments/__init__.py`
- Create: `backend/instruments/universe.py`
- Create: `backend/instruments/nifty50.json` (symbol, name, isin for all 50 constituents, `.NS` yfinance ticker)
- Create: `backend/instruments/banknifty.json`
- Create: `backend/instruments/niftyit.json`
- Create: `backend/instruments/indices.json` (Nifty 50, Bank Nifty, Nifty IT, Nifty Financial Services — symbol + yfinance ticker `^NSEI`/`^NSEBANK`/`^CNXIT`/`^CNXFIN`)
- Create: `backend/tests/instruments/test_universe.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `Instrument` dataclass (`symbol: str`, `name: str`, `yf_ticker: str`, `nse_symbol: str`, `kind: Literal["stock", "index"]`), `def list_universe(name: str) -> list[Instrument]` (`name` in `"nifty50"`, `"banknifty"`, `"niftyit"`, `"indices"`, `"all_stocks"`), `def resolve(symbol: str) -> Instrument | None`.

- [ ] **Step 1: Write the failing test:**
```python
from instruments.universe import list_universe, resolve


def test_nifty50_has_fifty_stock_instruments():
    insts = list_universe("nifty50")
    assert len(insts) == 50
    assert all(i.kind == "stock" for i in insts)


def test_resolve_known_symbol():
    inst = resolve("RELIANCE")
    assert inst is not None
    assert inst.yf_ticker == "RELIANCE.NS"


def test_resolve_unknown_symbol_returns_none():
    assert resolve("NOT_A_REAL_SYMBOL") is None
```
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Populate the four JSON files with real, current (as of 2026-10) NSE constituent lists — fetch the authoritative list once manually (NSE publishes official index constituent CSVs) and hard-code it; each entry: `{"symbol": "RELIANCE", "name": "Reliance Industries Ltd", "yf_ticker": "RELIANCE.NS", "nse_symbol": "RELIANCE", "kind": "stock"}`. `indices.json` entries use `"kind": "index"`.
- [ ] **Step 4:** Implement `backend/instruments/universe.py`: loads all JSON files at import time into an in-memory `_ALL: dict[str, Instrument]` keyed by symbol plus per-universe lists; `list_universe("all_stocks")` unions nifty50+banknifty+niftyit deduped by symbol; `resolve()` does a dict lookup, returns `None` on miss (never raises).
- [ ] **Step 5: Run to verify pass.**
- [ ] **Step 6: Commit.**
```bash
git add backend/instruments backend/tests/instruments
git commit -m "feat: add NSE instrument master (Nifty50/BankNifty/NiftyIT/indices)"
```

---

## Task 3: Indicator calculations

**Files:**
- Create: `backend/indicators/__init__.py`
- Create: `backend/indicators/calc.py`
- Create: `backend/tests/indicators/test_calc.py`

**Interfaces:**
- Consumes: `market_data.base.Candle`.
- Produces: `def to_dataframe(candles: list[Candle]) -> pd.DataFrame` (columns `open high low close volume`, index = `pd.DatetimeIndex` from `ts`, tz `Asia/Kolkata`); `def ema(df, length: int) -> pd.Series`; `def sma(df, length: int) -> pd.Series`; `def rsi(df, length: int = 14) -> pd.Series`; `def macd(df, fast=12, slow=26, signal=9) -> pd.DataFrame` (cols `macd signal hist`); `def bollinger(df, length=20, std=2) -> pd.DataFrame` (cols `lower mid upper`); `def supertrend(df, length=10, multiplier=3) -> pd.DataFrame` (cols `supertrend direction`); `def adx(df, length=14) -> pd.Series`; `def vwap_session(df) -> pd.Series` (resets at each session boundary — true intraday VWAP, requires intraday data); `def vwap_rolling(df, days: int) -> pd.Series` (rolling N-day VWAP over daily candles — explicitly NOT the same thing, named differently on purpose per spec §3).
- Produces: `class IndicatorError(Exception)` and `def validate_indicator_timeframe(indicator: str, timeframe: str) -> None` raising `IndicatorError` for meaningless combos (e.g. `vwap_session` requested with `timeframe="daily"` — session VWAP needs intraday candles).

- [ ] **Step 1: Write the failing tests** covering: EMA200 against a known 220-row synthetic series (assert last value matches `pandas.Series.ewm(span=200, adjust=False).mean()` computed inline in the test, i.e. independently verified per spec §6); `vwap_session` resets to the first bar's typical price at the start of each new trading day (construct two synthetic sessions, assert VWAP at session 2 bar 1 equals that bar's typical price, not a blend with session 1); `validate_indicator_timeframe("vwap_session", "daily")` raises `IndicatorError`; `validate_indicator_timeframe("ema", "daily")` does not raise.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `calc.py` using `pandas` directly for EMA/SMA/VWAP (simple, verifiable formulas) and `pandas_ta` for RSI/MACD/Bollinger/SuperTrend/ADX (don't hand-roll the harder ones — but assert each `pandas_ta` result's dtype/columns in the test so a library upgrade that renames a column fails loudly). `vwap_session` groups by `df.index.date` and computes cumulative `(typical_price * volume).cumsum() / volume.cumsum()` per group. `vwap_rolling` computes a rolling `days`-session VWAP over daily OHLCV (no session reset — it's a different metric, documented as such).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/indicators backend/tests/indicators
git commit -m "feat: add indicator calculations (EMA/SMA/RSI/MACD/BB/SuperTrend/ADX/VWAP)"
```

---

## Task 4: Strategy model + validation + persistence engine

**Files:**
- Create: `backend/strategies/__init__.py`
- Create: `backend/strategies/model.py`
- Create: `backend/strategies/persistence.py`
- Create: `backend/tests/strategies/test_model.py`
- Create: `backend/tests/strategies/test_persistence.py`

**Interfaces:**
- Consumes: `indicators.calc.validate_indicator_timeframe`, `market_data.base.Provider` (via its `.name` and known capabilities).
- Produces: pydantic `Condition` (`indicator: str`, `params: dict`, `comparison: Literal["above","below","crosses_above","crosses_below"]`, `compare_to: str` — either another indicator spec or `"price"`), `Strategy` (`id: str`, `user_id: str`, `name: str`, `universe: list[str]`, `instrument_type: Literal["stock","index","both"]`, `timeframe: str`, `conditions: list[Condition]`, `logic: Literal["AND","OR"]`, `min_consecutive_sessions: int`, `provider: str`, `enabled: bool`); `def validate_strategy(s: Strategy) -> list[str]` (returns list of human-readable errors, empty = valid; calls `validate_indicator_timeframe` per condition and checks `provider` supports the chosen `timeframe` via a capability map); `def consecutive_sessions_satisfied(satisfied_by_session: list[bool]) -> int` (counts the trailing run of `True` values, stopping at the first `False` or at a gap — takes an already-session-aligned, holiday-free list, i.e. caller must have already dropped non-trading days, not treat them as `False`).

- [ ] **Step 1: Write the failing tests:**
```python
def test_consecutive_sessions_counts_trailing_true_run():
    assert consecutive_sessions_satisfied([False, True, True, True, True, True]) == 5

def test_consecutive_sessions_stops_at_break():
    assert consecutive_sessions_satisfied([True, False, True, True]) == 2

def test_consecutive_sessions_empty_is_zero():
    assert consecutive_sessions_satisfied([]) == 0

def test_validate_strategy_rejects_session_vwap_on_daily_timeframe():
    s = Strategy(id="x", user_id="u", name="n", universe=["nifty50"],
                 instrument_type="stock", timeframe="daily",
                 conditions=[Condition(indicator="vwap_session", params={}, comparison="above", compare_to="price")],
                 logic="AND", min_consecutive_sessions=5, provider="yfinance", enabled=True)
    errors = validate_strategy(s)
    assert any("vwap_session" in e for e in errors)

def test_validate_strategy_rejects_intraday_on_nse_provider():
    s = Strategy(id="x", user_id="u", name="n", universe=["nifty50"],
                 instrument_type="stock", timeframe="15m",
                 conditions=[Condition(indicator="ema", params={"length": 20}, comparison="above", compare_to="price")],
                 logic="AND", min_consecutive_sessions=1, provider="nse", enabled=True)
    errors = validate_strategy(s)
    assert any("intraday" in e.lower() for e in errors)
```
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `model.py` (pydantic models above) and `persistence.py` (`consecutive_sessions_satisfied`, `validate_strategy` with a hard-coded `PROVIDER_CAPABILITIES = {"yfinance": {"intraday": True}, "nse": {"intraday": False}}` map consulted alongside `validate_indicator_timeframe`).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/strategies backend/tests/strategies
git commit -m "feat: add strategy model, validation, and session-persistence counting"
```

---

## Task 5: Database schema

**Files:**
- Create: `backend/database/__init__.py`
- Create: `backend/database/schema.py`
- Create: `backend/tests/database/test_schema.py`

**Interfaces:**
- Consumes: `config.settings.DB_PATH`.
- Produces: `def conn() -> sqlite3.Connection` (same pattern as `delta/backend/store.py:_conn`, `row_factory = sqlite3.Row`, creates-if-missing with `0o600` perms); tables created idempotently: `strategies(id TEXT PRIMARY KEY, user_id TEXT, name TEXT, config_json TEXT, enabled INTEGER, created_at INTEGER, updated_at INTEGER)`; `scan_runs(id TEXT PRIMARY KEY, user_id TEXT, strategy_id TEXT, started_at INTEGER, finished_at INTEGER, status TEXT, instruments_scanned INTEGER, matches_count INTEGER, error TEXT)`; `scan_results(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, symbol TEXT, kind TEXT, satisfied INTEGER, consecutive_sessions INTEGER, latest_price REAL, latest_ts INTEGER, indicator_values_json TEXT, last_candle_date TEXT)`; `watchlist(user_id TEXT, symbol TEXT, added_at INTEGER, PRIMARY KEY (user_id, symbol))`; `scheduler_locks(slot_key TEXT PRIMARY KEY, locked_at INTEGER)` (dedupe table for Task 7).

- [ ] **Step 1: Write the failing test** asserting each table exists after `init_db()` and that calling `init_db()` twice doesn't error (idempotent `CREATE TABLE IF NOT EXISTS`).
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `schema.py` directly modeled on `delta/backend/store.py`'s `_conn()` pattern, with a single `init_db()` that runs all `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` statements.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/database backend/tests/database
git commit -m "feat: add scanner database schema"
```

---

## Task 6: Scanner engine (strategy evaluation over a universe)

**Files:**
- Create: `backend/scanner/__init__.py`
- Create: `backend/scanner/engine.py`
- Create: `backend/tests/scanner/test_engine.py`

**Interfaces:**
- Consumes: `strategies.model.Strategy`, `instruments.universe.list_universe`, `market_data.get_provider`, `indicators.calc.*`, `strategies.persistence.consecutive_sessions_satisfied`.
- Produces: `@dataclass ScanResultRow` (fields match `database.schema.scan_results` columns plus `strategy_name: str`); `def run_scan(strategy: Strategy) -> list[ScanResultRow]` — resolves the strategy's universe to instruments, fetches candles per instrument via the strategy's chosen provider, evaluates every condition per session going back `min_consecutive_sessions + buffer` sessions, computes the trailing satisfied-run length via `consecutive_sessions_satisfied`, and returns one row per instrument (including non-matches, each tagged `satisfied=False`, and including skipped/stale instruments with `latest_price=None` rather than omitting them).

- [ ] **Step 1: Write the failing test** using a fake `Provider` (reuse the `_FakeProvider` pattern from Task 1, extended to return a controllable candle series) and a single-condition `Strategy` ("close below EMA200"), asserting: (a) an instrument whose fake series is below EMA200 for exactly 5 of the last 5 sessions comes back `satisfied=True, consecutive_sessions=5`; (b) an instrument with only 3 satisfying sessions comes back `satisfied=False` when `min_consecutive_sessions=5`; (c) an instrument whose fake provider raises `ProviderError` comes back as a row with `latest_price=None` and is not silently dropped from the result list, and the scan as a whole still returns rows for the other instruments (per Review Focus: provider outage must not abort the run).
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `engine.py`: wrap each instrument's fetch+evaluate in `try/except ProviderError` inside the per-instrument loop (never let one instrument's failure propagate out of `run_scan`); build the daily/session-aligned boolean series by evaluating the condition on each row of the indicator-augmented dataframe, then feed the trailing window into `consecutive_sessions_satisfied`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/scanner backend/tests/scanner
git commit -m "feat: add scanner engine evaluating strategies over an instrument universe"
```

---

## Task 7: Scheduler (APScheduler, Asia/Kolkata, dedupe, run-now)

**Files:**
- Create: `backend/scheduler/__init__.py`
- Create: `backend/scheduler/jobs.py`
- Create: `backend/tests/scheduler/test_jobs.py`

**Interfaces:**
- Consumes: `scanner.engine.run_scan`, `database.schema.conn`, `strategies.model.Strategy`.
- Produces: `def slot_key(strategy_id: str, scheduled_time: datetime) -> str` (e.g. `f"{strategy_id}:{scheduled_time.astimezone(ZoneInfo('Asia/Kolkata')).date()}"` — one slot per strategy per calendar day, immune to a restart re-firing the same day's 9:00 job); `def try_acquire_slot(slot_key: str) -> bool` (INSERT OR IGNORE into `scheduler_locks`, returns True iff this call inserted the row — i.e. this call "won" the slot); `def run_scheduled_scan(strategy: Strategy) -> None` (calls `try_acquire_slot`; if it returns `False`, logs and returns without scanning; else runs `run_scan`, writes a `scan_runs` + `scan_results` row); `class SchedulerService` wrapping `apscheduler.schedulers.background.BackgroundScheduler` with `add_strategy_job(strategy)` (cron trigger at the strategy's configured time, `timezone="Asia/Kolkata"`), `remove_strategy_job(strategy_id)`, `run_now(strategy)` (bypasses the cron trigger but still goes through `try_acquire_slot` using the *current* time's slot key, so a manual run-now right before the scheduled 9:00 run still dedupes against it), `next_run_time(strategy_id) -> datetime | None`.

- [ ] **Step 1: Write the failing test:**
```python
def test_try_acquire_slot_only_succeeds_once(tmp_db_path):
    schema.init_db()
    assert try_acquire_slot("strat1:2026-10-13") is True
    assert try_acquire_slot("strat1:2026-10-13") is False

def test_run_scheduled_scan_skips_if_slot_already_taken(tmp_db_path, monkeypatch):
    schema.init_db()
    calls = []
    monkeypatch.setattr("scanner.engine.run_scan", lambda s: calls.append(s) or [])
    strategy = _sample_strategy()
    run_scheduled_scan(strategy)
    run_scheduled_scan(strategy)  # simulates restart re-firing same day's job
    assert len(calls) == 1
```
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `jobs.py` per the interfaces above; `SchedulerService` uses `from apscheduler.triggers.cron import CronTrigger` with `timezone=ZoneInfo("Asia/Kolkata")` built from the strategy's stored `scan_time` (HH:MM) and `scan_days` (weekday list or `"daily"`).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/scheduler backend/tests/scheduler
git commit -m "feat: add Asia/Kolkata scheduler with slot-based dedupe and run-now"
```

---

## Task 8: FastAPI app (auth, strategies CRUD, watchlist, scan + history endpoints)

**Files:**
- Create: `backend/auth.py` (copy pattern from `delta/backend/auth.py` — Clerk JWKS verification, `bind_user` dependency)
- Create: `backend/main.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces REST endpoints (all behind `Depends(auth.bind_user)` at app level, matching `delta/backend/main.py`):
  - `GET /universe` → `{universe_name: [Instrument...]}` for all known universes.
  - `GET /watchlist`, `POST /watchlist {symbol}`, `DELETE /watchlist/{symbol}`.
  - `GET /strategies`, `POST /strategies` (body = `Strategy` minus `id`/`user_id`; 400 with `validate_strategy` errors if invalid), `PUT /strategies/{id}`, `DELETE /strategies/{id}`.
  - `POST /strategies/{id}/run-now` → triggers `SchedulerService.run_now`, returns the new `scan_runs.id`.
  - `GET /scans?strategy_id=&limit=` → list of `scan_runs` rows (history).
  - `GET /scans/{run_id}/results` → list of `scan_results` rows for that run.
  - `GET /dashboard` → aggregate: market status (derived from current `Asia/Kolkata` time vs NSE session hours 09:15–15:30, pre-market before that), most recent `scan_runs` row per enabled strategy, next scheduled run time per strategy.

- [ ] **Step 1: Write the failing API tests** using `fastapi.testclient.TestClient` with a monkeypatched `auth.bind_user` dependency override (same trick `delta/backend/tests` uses to bypass real Clerk verification in tests — check `delta/backend/tests/conftest.py` for the exact override pattern and reuse it) covering: creating an invalid strategy returns 400 with the validation error text; creating a valid strategy then calling `run-now` produces a `scan_runs` row retrievable via `GET /scans`; `GET /dashboard` reports `market_status` as one of `"pre_market"/"open"/"closed"`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement `auth.py` (copy+adapt from the Delta backend, same Clerk envvar) and `main.py` wiring all routes to the modules above, instantiating one process-wide `SchedulerService` on app startup (`@app.on_event("startup")`) that loads every enabled strategy from the DB and calls `add_strategy_job`.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/auth.py backend/main.py backend/tests/test_api.py
git commit -m "feat: wire FastAPI app with Clerk auth, strategy CRUD, scan history, dashboard"
```

---

## Task 9: Notifications (Telegram, dedupe on unchanged matches)

**Files:**
- Create: `backend/notifications/__init__.py`
- Create: `backend/notifications/telegram.py`
- Create: `backend/tests/notifications/test_telegram.py`
- Modify: `backend/scheduler/jobs.py` (`run_scheduled_scan` calls `notifications.telegram.notify_new_matches` after writing results, if the user has a Telegram chat id configured)

**Interfaces:**
- Consumes: `database.schema.conn` (to diff current vs previous run's matched symbols for the same strategy).
- Produces: `def notify_new_matches(user_id: str, strategy: Strategy, current_matches: set[str], previous_matches: set[str]) -> None` — sends a Telegram message only for symbols in `current_matches - previous_matches`; no-ops (and doesn't raise) if the user has no Telegram chat id configured or the Telegram API call fails (logs instead).

- [ ] **Step 1: Write the failing test** asserting `notify_new_matches` only calls the (monkeypatched) Telegram send function for genuinely new symbols, and does nothing when `current_matches == previous_matches`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3:** Implement using `httpx.post` to `https://api.telegram.org/bot{token}/sendMessage`; token + per-user chat id read from a new `user_settings` table (add `CREATE TABLE IF NOT EXISTS user_settings(user_id TEXT PRIMARY KEY, telegram_chat_id TEXT, telegram_bot_token_enc TEXT, active_provider TEXT, updated_at INTEGER)` to `database/schema.py` in this task, plus `GET/PUT /settings` endpoints in `main.py` to read/write it, encrypting the bot token at rest the same way `delta/backend/crypto.py` encrypts Delta API secrets).
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit.**
```bash
git add backend/notifications backend/database/schema.py backend/main.py backend/tests/notifications
git commit -m "feat: add Telegram notifications for new scan matches, dedupe unchanged matches"
```

---

## Self-review notes

- Spec coverage: §2 (dashboard/watchlist/finder data) → Task 8 endpoints + Task 2 universe; §3 (strategy builder + validation) → Task 4; §4 (scheduling) → Task 7; §5 (free data APIs, provider switch) → Task 1 + `user_settings.active_provider` in Task 9; §6 (architecture/module layout) → all tasks map 1:1 to the spec's listed modules; §7 (scan result shape) → `ScanResultRow`/`scan_results` schema in Tasks 5–6; §8 (history + notifications) → Tasks 5, 8, 9; §9 (reliability/testing) → covered per-task plus Review Focus; §10 (MVP criteria) → satisfied by Tasks 1–8 (criterion 8, "at least one working free-data integration", satisfied by yfinance in Task 1; NSE provider included per the brainstorming decision, with its EOD-only limitation documented in its module docstring).
- No frontend task here — the frontend (dashboard/watchlist/finder/settings UI) is a separate plan that consumes this backend's REST contract (Task 8); write it once this plan's Task 8 is implemented and the actual response shapes are confirmed.
- BSE support, Postgres upgrade, and crossover-specific indicator edge cases (e.g. multi-bar crossover confirmation) are intentionally deferred past MVP per spec §6/§10.
