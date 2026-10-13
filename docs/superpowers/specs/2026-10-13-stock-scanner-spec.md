# Build an AI-Powered Stock & Index Scanner Bot

(Full spec as provided by the user on 2026-10-13. Decisions made during brainstorming are appended at the end.)

## 1. Project Overview

Build a trading scanner application inspired by the existing cryptocurrency trading bot built for Delta Exchange (`/home/anand-shaurya/Documents/personal/delta`). This new application focuses on the Indian stock market: individual stocks, Nifty 50, Bank Nifty, Nifty IT, and other major indices.

Goal: a lightweight, modern application with a minimal but advanced UI that automatically scans the market based on user-defined technical indicator conditions and identifies stocks/indices matching those conditions. This is a market-scanning and signal-discovery tool, NOT an automatic trade execution system.

## 2. User Interface

Dark theme, compact, modern financial-terminal aesthetic.

### A. Dashboard
- Market status: Pre-market, Open, Closed.
- Latest scan execution time and next scheduled scan.
- Total instruments scanned; number matching filters.
- Latest scan results and their technical conditions.
- Scan status: Running, Completed, Failed.

### B. Watchlist
- Add/remove stocks and indices.
- Instrument name, symbol, latest price, daily change, relevant indicator values.
- Open detailed charts / technical indicator data.
- Search, sort, filter.
- Clearly distinguish stocks from indices.

### C. Stock & Index Finder
Scanner over a configurable universe: Nifty 50, Nifty Next 50, Bank Nifty, Nifty IT, other NSE-listed stocks, major indices (Nifty 50, Bank Nifty, Nifty IT, Nifty Financial Services). Users select one or more universes or individual instruments.

## 3. Advanced Strategy Builder

Settings page to define screening conditions without code:
- Market: India. Exchange: NSE (BSE optional future extension).
- Instrument type: Stock, Index, or Both.
- Instrument universe: Nifty 50, Bank Nifty constituents, all supported NSE stocks, custom watchlist, etc.
- Indicator: VWAP, EMA, SMA, RSI, MACD, SuperTrend, ADX, Bollinger Bands, etc.
- Indicator parameters (e.g. EMA length = 200).
- Comparison: price above/below indicator, indicator A vs B, crossover, etc.
- Timeframe: 5m, 15m, 1h, daily, weekly, etc.
- Historical persistence: condition true for N consecutive trading sessions.
- Combine multiple rules with AND/OR.

Example strategies given (EMA200 close-below for 5 sessions; VWAP above for 5 sessions on Bank Nifty constituents).

Indicator rules: correct timeframe per indicator; daily conditions use completed daily candles unless user opts otherwise; intraday VWAP resets per exchange session; daily VWAP != rolling 5-day VWAP — must be explained in UI; validate indicator/timeframe combination is meaningful.

## 4. Automated Scheduling
- Default 9:00 AM IST, user-configurable time and frequency (daily/weekdays/manual).
- Timezone explicitly Asia/Kolkata.
- No duplicate scans per scheduled slot; safe across restarts/missed schedules.
- Show next scheduled execution; "Run Scan Now" button.
- Scan logs: timestamps, errors, duration.
- 9:00 AM scan (before 9:15 open) must use latest completed pre-market/previous-session data, never mislabeled as live.

## 5. Free Market Data APIs
- Evaluate yfinance, NSE India public endpoints, other free providers.
- Provider abstraction layer so providers are swappable; user can pick/switch provider in Settings.
- Rate limiting, retries with backoff, caching, clear error handling.
- Instrument master / symbol mapping for stocks and indices.
- Track data timestamps; flag stale/missing data. Never fabricate values.
- Must remain useful with EOD data alone if intraday provider unavailable.

## 6. Technical Architecture
- Backend: Python, FastAPI (reuse patterns from `/home/anand-shaurya/Documents/personal/delta/backend`: Clerk JWT auth via `auth.py`, encrypted-at-rest SQLite via `store.py`/`crypto.py`, `config.py`, same run style `uvicorn main:app`).
- Frontend: Next.js (App Router) + Tailwind, Clerk sign-in, dark terminal aesthetic matching `delta/frontend` (`components/Ui.tsx`, table components, `Nav.tsx`).
- Database: SQLite MVP (`backend/data.db` style), Postgres optional later.
- Market data: pluggable provider interface (yfinance + NSE India endpoints both wired in from day 1; user-switchable in Settings).
- Indicators: pandas + `pandas-ta` (or equivalent), independently verified.
- Scheduling: APScheduler, `Asia/Kolkata` tz.
- Charts: Lightweight Charts (TradingView OSS).

Module layout:
- `market_data/`, `instruments/`, `indicators/`, `scanner/`, `strategies/`, `scheduler/`, `watchlist/`, `api/`, `database/`, `frontend/`.

## 7. Scan Results
Per result: instrument name/symbol, type, latest price + timestamp, timeframe, indicator name/value, comparison value, satisfied true/false, consecutive-session count, most recent confirmed candle date, strategy name.

## 8. Notifications and Scan History
- Full scan history (matched + excluded where practical), exact strategy config per run, diff vs previous scan.
- Optional Telegram/email notifications for new matches only (dedupe).

## 9. Reliability and Testing
Automated tests for: indicator calculations, 5-session persistence, missing candles/holidays, symbol changes/delistings, duplicate scheduled runs, API failures/rate limits, timezone/DST-independent scheduling, bad historical data, multi-condition AND/OR. Missing sessions must never count as confirmations; use actual trading sessions, not calendar days.

## 10. MVP Completion Criteria
1. Functional dashboard and watchlist.
2. Indian stocks and major indices.
3. Configurable technical screening engine.
4. Five-consecutive-session condition verification.
5. User-configurable daily scheduler.
6. Persistent scan history.
7. Usable UI for creating/managing strategies.
8. At least one working free-data integration, limitations documented.

No automatic trade execution, no paid data subscriptions, no unnecessary AI features unless explicitly requested later.

---

## Decisions made during brainstorming (2026-10-13)

- **Auth:** Multi-user, Clerk login — mirror the Delta bot's pattern exactly (Clerk JWT verified in FastAPI via `auth.bind_user`-style dependency; per-user encrypted credentials/settings in SQLite; no shared operator key).
- **Data providers:** Build the provider abstraction from day 1 with BOTH `yfinance` and NSE India public endpoints wired in; user picks/switches active provider per instrument-universe in Settings. Document each provider's limitations (rate limits, intraday depth, reliability) in the UI.
- **Timeframe scope:** Not fixed to daily-only — exposed as a user choice in the Strategy Builder (daily/weekly default and recommended; intraday 5m/15m/1h available but UI must flag intraday-VWAP/session-reset caveats and provider reliability risk per the chosen provider).
