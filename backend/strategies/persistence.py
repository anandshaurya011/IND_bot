"""Strategy validation and session-persistence counting."""

from __future__ import annotations

from indicators.calc import IndicatorError, validate_indicator_timeframe
from strategies.model import Strategy

# Hard-coded provider capability map: which providers support intraday
# timeframes. Consulted alongside `validate_indicator_timeframe` when
# validating a strategy's provider/timeframe combination.
PROVIDER_CAPABILITIES = {
    "yfinance": {"intraday": True},
    "nse": {"intraday": False},
}


def _is_intraday(timeframe: str) -> bool:
    """A timeframe is intraday unless it is the daily bar."""
    return timeframe != "daily"


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
