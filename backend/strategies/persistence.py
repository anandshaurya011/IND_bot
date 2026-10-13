"""Strategy validation and session-persistence counting."""

from __future__ import annotations

import re

from indicators.calc import IndicatorError, validate_indicator_timeframe
from instruments.universe import VALID_UNIVERSE_NAMES
from strategies.model import Strategy

# "watchlist" is a special universe name (not in the static instrument-master
# universes) meaning "scan this user's own saved watchlist symbols first" -
# resolved per-user at scan time in scanner.engine, not a static JSON list.
_SPECIAL_UNIVERSE_NAMES = {"watchlist"}

# Hard-coded provider capability map: which providers support intraday
# timeframes. Consulted alongside `validate_indicator_timeframe` when
# validating a strategy's provider/timeframe combination.
PROVIDER_CAPABILITIES = {
    "yfinance": {"intraday": True},
    "nse": {"intraday": False},
}

_SCAN_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _is_intraday(timeframe: str) -> bool:
    """A timeframe is intraday unless it is the daily bar."""
    return timeframe != "daily"


def _validate_scan_time(scan_time: str) -> str | None:
    """Return an error message if `scan_time` isn't a valid "HH:MM" (00-23/00-59)."""
    if not isinstance(scan_time, str) or not _SCAN_TIME_RE.match(scan_time):
        return f"scan_time {scan_time!r} must be in HH:MM format (00-23:00-59)"
    return None


def _validate_scan_days(scan_days) -> str | None:
    """Return an error message if `scan_days` isn't "daily" or a non-empty
    list of weekday ints 0-6 (0=Monday .. 6=Sunday).
    """
    if scan_days == "daily":
        return None
    if not isinstance(scan_days, list) or len(scan_days) == 0:
        return f"scan_days {scan_days!r} must be 'daily' or a non-empty list of ints 0-6"
    if not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in scan_days):
        return f"scan_days {scan_days!r} must be 'daily' or a non-empty list of ints 0-6"
    return None


def validate_strategy(s: Strategy) -> list[str]:
    """Validate a Strategy, returning a list of human-readable errors.

    An empty list means the strategy is valid. Checks each condition's
    indicator/timeframe combination via `validate_indicator_timeframe`, and
    checks that the chosen provider supports the strategy's timeframe
    (e.g. intraday timeframes on a provider without intraday data).
    """
    errors: list[str] = []

    for condition in s.conditions:
        try:
            validate_indicator_timeframe(condition.indicator, s.timeframe)
        except IndicatorError as exc:
            errors.append(str(exc))

    capabilities = PROVIDER_CAPABILITIES.get(s.provider)
    if capabilities is None:
        errors.append(f"unknown provider {s.provider!r}")
    elif _is_intraday(s.timeframe) and not capabilities.get("intraday", False):
        errors.append(
            f"provider {s.provider!r} does not support intraday timeframe "
            f"{s.timeframe!r}"
        )

    if len(s.universe) == 0:
        errors.append("universe must not be empty; select at least one universe to scan")

    for universe_name in s.universe:
        if universe_name not in VALID_UNIVERSE_NAMES and universe_name not in _SPECIAL_UNIVERSE_NAMES:
            errors.append(
                f"unknown universe {universe_name!r}; must be one of "
                f"{VALID_UNIVERSE_NAMES + sorted(_SPECIAL_UNIVERSE_NAMES)}"
            )

    scan_time_error = _validate_scan_time(s.scan_time)
    if scan_time_error:
        errors.append(scan_time_error)

    scan_days_error = _validate_scan_days(s.scan_days)
    if scan_days_error:
        errors.append(scan_days_error)

    return errors


def consecutive_sessions_satisfied(satisfied_by_session: list[bool]) -> int:
    """Count the trailing run of True values in an already session-aligned,
    holiday-free list (caller must have already dropped non-trading days).
    """
    count = 0
    for satisfied in reversed(satisfied_by_session):
        if not satisfied:
            break
        count += 1
    return count
