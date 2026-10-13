"""Asia/Kolkata-aware scheduler for strategy scans.

All scheduling/dedupe logic uses `ZoneInfo("Asia/Kolkata")` explicitly - never
naive or system-local time. `slot_key` gives one lock per strategy per IST
calendar day, so a restart re-firing the same day's cron job (or a manual
"run now" shortly before/after the scheduled time) only ever scans once.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import schema
from notifications.telegram import notify_new_matches
from scanner.engine import run_scan
from strategies.model import Strategy

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def slot_key(strategy_id: str, scheduled_time: datetime) -> str:
    """One slot per strategy per IST calendar day."""
    return f"{strategy_id}:{scheduled_time.astimezone(IST).date()}"


def try_acquire_slot(key: str) -> bool:
    """Attempt to claim `key` in `scheduler_locks`.

    Returns True iff this call inserted the row (i.e. "won" the slot); False
    if the slot was already taken by a previous call (same process or a prior
    run before a restart).
    """
    conn = schema.conn()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO scheduler_locks (slot_key, locked_at) VALUES (?, ?)",
            (key, int(time.time())),
        )
        return cur.rowcount == 1
    finally:
        conn.close()


def run_scheduled_scan(strategy: Strategy) -> str | None:
    """Run `strategy`'s scan, deduped per IST calendar day via `try_acquire_slot`.

    This dedupe exists for the CRON-triggered path only: it stops a server
    restart from re-firing the same day's scheduled job a second time. If
    the slot for "now" is already taken, logs and returns None without
    scanning or writing any rows. Returns the new run's id on success.

    Manual "Run Now" does NOT go through this - see `_execute_scan` /
    `SchedulerService.run_now`, which always scans fresh regardless of
    whether today's scheduled slot was already used.
    """
    now = datetime.now(IST)
    key = slot_key(strategy.id, now)
    if not try_acquire_slot(key):
        logger.info("skipping scan for strategy=%s: slot %s already taken", strategy.id, key)
        return None
    return _execute_scan(strategy)


def _execute_scan(strategy: Strategy) -> str:
    """Run `strategy`'s scan and persist the results, unconditionally (no
    dedupe/slot check - callers that need the once-per-day guard use
    `run_scheduled_scan` instead). Returns the new run's id.
    """
    run_id = str(uuid.uuid4())
    started_at = int(time.time())
    conn = schema.conn()
    try:
        prior_row = conn.execute(
            "SELECT id FROM scan_runs WHERE strategy_id = ? AND status = 'ok' "
            "ORDER BY started_at DESC LIMIT 1",
            (strategy.id,),
        ).fetchone()
        previous_matches: set[str] = set()
        if prior_row is not None:
            previous_matches = {
                r["symbol"]
                for r in conn.execute(
                    "SELECT symbol FROM scan_results WHERE run_id = ? AND satisfied = 1",
                    (prior_row["id"],),
                ).fetchall()
            }

        try:
            rows = run_scan(strategy)
        except Exception as exc:  # defensive: run_scan should not raise, but
            # a scheduled run must never crash the scheduler thread.
            logger.exception("scan failed for strategy=%s", strategy.id)
            conn.execute(
                "INSERT INTO scan_runs (id, user_id, strategy_id, started_at, finished_at, "
                "status, instruments_scanned, matches_count, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, strategy.user_id, strategy.id, started_at, int(time.time()), "error", 0, 0, str(exc)),
            )
            return run_id

        matches_count = sum(1 for row in rows if row.satisfied)
        conn.execute(
            "INSERT INTO scan_runs (id, user_id, strategy_id, started_at, finished_at, "
            "status, instruments_scanned, matches_count, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                strategy.user_id,
                strategy.id,
                started_at,
                int(time.time()),
                "ok",
                len(rows),
                matches_count,
                None,
            ),
        )
        for row in rows:
            conn.execute(
                "INSERT INTO scan_results (run_id, symbol, kind, satisfied, consecutive_sessions, "
                "latest_price, latest_ts, indicator_values_json, last_candle_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    row.symbol,
                    row.kind,
                    int(row.satisfied),
                    row.consecutive_sessions,
                    row.latest_price,
                    row.latest_ts,
                    row.indicator_values_json,
                    row.last_candle_date,
                ),
            )

        current_matches = {row.symbol for row in rows if row.satisfied}
        try:
            notify_new_matches(strategy.user_id, strategy, current_matches, previous_matches)
        except Exception:
            # Notifications must never crash a scan; notify_new_matches already
            # logs internally, but guard defensively against any other failure.
            logger.exception("notify_new_matches failed for strategy=%s", strategy.id)
    finally:
        conn.close()

    return run_id


def _build_trigger(strategy: Strategy) -> CronTrigger:
    hour_str, minute_str = strategy.scan_time.split(":")
    hour, minute = int(hour_str), int(minute_str)
    day_of_week = "*" if strategy.scan_days == "daily" else ",".join(str(d) for d in strategy.scan_days)
    return CronTrigger(hour=hour, minute=minute, day_of_week=day_of_week, timezone=IST)


class SchedulerService:
    """Wraps an `apscheduler` `BackgroundScheduler` configured for Asia/Kolkata."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone=IST)
        self._scheduler.start(paused=False)

    def add_strategy_job(self, strategy: Strategy) -> None:
        trigger = _build_trigger(strategy)
        self._scheduler.add_job(
            run_scheduled_scan,
            trigger=trigger,
            args=[strategy],
            id=strategy.id,
            replace_existing=True,
        )

    def remove_strategy_job(self, strategy_id: str) -> None:
        job = self._scheduler.get_job(strategy_id)
        if job is not None:
            self._scheduler.remove_job(strategy_id)

    def run_now(self, strategy: Strategy) -> str:
        """Run `strategy` immediately, bypassing both the cron trigger AND
        the once-per-IST-day slot dedupe - a user clicking "Run Now" wants
        a genuinely fresh scan every time, even if today's scheduled slot
        was already used (that dedupe exists only to stop a server restart
        from re-firing the same cron job twice, not to limit manual runs).
        Returns the new run's id.
        """
        return _execute_scan(strategy)

    def next_run_time(self, strategy_id: str) -> datetime | None:
        job = self._scheduler.get_job(strategy_id)
        if job is None:
            return None
        return job.next_run_time

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
