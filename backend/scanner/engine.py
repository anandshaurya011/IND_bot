"""Scanner engine: evaluate a Strategy's conditions over its instrument universe.

`run_scan` never raises for a single bad instrument (provider outage,
missing data, etc.) - the scheduler that will eventually call this depends
on one instrument's failure never aborting the whole scan. Failures are
surfaced as a result row with `latest_price=None` rather than by dropping
the instrument from the output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from indicators import calc
from instruments.universe import Instrument, list_universe
from market_data import get_provider
from market_data.base import ProviderError
from strategies.model import Condition, Strategy
from strategies.persistence import consecutive_sessions_satisfied

# Buffer of extra sessions fetched beyond min_consecutive_sessions, to give
# indicators (e.g. EMA200) a reasonable warm-up window.
_SESSION_BUFFER = 30

# Dispatch table: Condition.indicator string -> calc.py function.
_INDICATOR_FUNCS = {
    "ema": calc.ema,
    "sma": calc.sma,
    "rsi": calc.rsi,
    "macd": calc.macd,
    "bollinger": calc.bollinger,
    "supertrend": calc.supertrend,
    "adx": calc.adx,
    "vwap_session": calc.vwap_session,
    "vwap_rolling": calc.vwap_rolling,
    # Pseudo-indicator: the raw close price, usable on either side of a
    # condition (e.g. as `compare_to`'s target when the spec names it).
    "close": lambda df, **_kwargs: df["close"],
}


@dataclass
class ScanResultRow:
    """Mirrors `database.schema.scan_results` columns, plus `strategy_name`."""

    run_id: str | None
    symbol: str
    kind: str
    satisfied: bool
    consecutive_sessions: int
    latest_price: float | None
    latest_ts: int | None
    indicator_values_json: str | None
    last_candle_date: str | None
    strategy_name: str


def _resolve_universe(strategy: Strategy) -> list[Instrument]:
    """Union of every named universe in `strategy.universe`, deduped by symbol,
    filtered by `strategy.instrument_type` unless it is "both".
    """
    seen: dict[str, Instrument] = {}
    for universe_name in strategy.universe:
        for instrument in list_universe(universe_name):
            seen.setdefault(instrument.symbol, instrument)

    instruments = list(seen.values())
    if strategy.instrument_type != "both":
        instruments = [i for i in instruments if i.kind == strategy.instrument_type]
    return instruments


def _symbol_for_provider(instrument: Instrument, provider_name: str) -> str:
    if provider_name == "yfinance":
        return instrument.yf_ticker
    if provider_name == "nse":
        return instrument.nse_symbol
    return instrument.yf_ticker


def _parse_spec(spec: str) -> tuple[str, dict]:
    """Parse a `compare_to` indicator spec of the form "name" or "name:param".

    "price" is handled separately by the caller. A bare name uses empty
    params; "name:length" (e.g. "ema:50") passes `length=<int>` - the only
    parametrization `compare_to` needs for now.
    """
    if ":" in spec:
        name, _, raw_param = spec.partition(":")
        return name, {"length": int(raw_param)}
    return spec, {}


def _series_from_spec(df: pd.DataFrame, spec: str, params: dict) -> pd.Series:
    if spec == "price":
        return df["close"]
    name, parsed_params = _parse_spec(spec)
    func = _INDICATOR_FUNCS.get(name)
    if func is None:
        raise ProviderError(f"unknown indicator spec: {spec!r}")
    result = func(df, **(parsed_params or params))
    if isinstance(result, pd.DataFrame):
        # Multi-column indicators (macd, bollinger, supertrend) are not
        # addressable by a bare name on their own - callers that need a
        # specific column should use "name:column" via compare_to, but for
        # now we take the first column as a reasonable default.
        return result.iloc[:, 0]
    return result


def _indicator_series(df: pd.DataFrame, condition: Condition) -> pd.Series:
    func = _INDICATOR_FUNCS.get(condition.indicator)
    if func is None:
        raise ProviderError(f"unknown indicator: {condition.indicator!r}")
    result = func(df, **condition.params)
    if isinstance(result, pd.DataFrame):
        return result.iloc[:, 0]
    return result


def _compare(lhs: pd.Series, comparison: str, rhs: pd.Series) -> pd.Series:
    """Elementwise comparison. Any row where either side is NaN is False -
    never fabricate a satisfied/unsatisfied verdict from missing data.
    """
    valid = lhs.notna() & rhs.notna()

    if comparison == "above":
        result = lhs > rhs
    elif comparison == "below":
        result = lhs < rhs
    elif comparison == "crosses_above":
        prev_lhs = lhs.shift(1)
        prev_rhs = rhs.shift(1)
        valid = valid & prev_lhs.notna() & prev_rhs.notna()
        result = (prev_lhs <= prev_rhs) & (lhs > rhs)
    elif comparison == "crosses_below":
        prev_lhs = lhs.shift(1)
        prev_rhs = rhs.shift(1)
        valid = valid & prev_lhs.notna() & prev_rhs.notna()
        result = (prev_lhs >= prev_rhs) & (lhs < rhs)
    else:
        raise ProviderError(f"unknown comparison: {comparison!r}")

    return result.where(valid, other=False).astype(bool)


def _evaluate_condition(df: pd.DataFrame, condition: Condition) -> pd.Series:
    lhs = _indicator_series(df, condition)
    rhs = _series_from_spec(df, condition.compare_to, condition.params)
    return _compare(lhs, condition.comparison, rhs)


def _evaluate_strategy(df: pd.DataFrame, strategy: Strategy) -> pd.Series:
    """Combine every condition's per-session boolean series with `strategy.logic`
    BEFORE counting the trailing run - the combined series is what gets fed to
    `consecutive_sessions_satisfied`, not each condition separately.
    """
    combined: pd.Series | None = None
    for condition in strategy.conditions:
        condition_series = _evaluate_condition(df, condition)
        if combined is None:
            combined = condition_series
        elif strategy.logic == "AND":
            combined = combined & condition_series
        else:  # "OR"
            combined = combined | condition_series
    if combined is None:
        return pd.Series(dtype=bool)
    return combined


def _scan_one(strategy: Strategy, instrument: Instrument) -> ScanResultRow:
    provider = get_provider(strategy.provider)
    fetch_count = strategy.min_consecutive_sessions + _SESSION_BUFFER
    symbol = _symbol_for_provider(instrument, strategy.provider)

    candles = provider.get_daily_candles(symbol, lookback_days=fetch_count)
    if not candles:
        raise ProviderError(f"no candles for {symbol}")

    df = calc.to_dataframe(candles)
    combined = _evaluate_strategy(df, strategy)

    # Oldest-to-newest, matching consecutive_sessions_satisfied's trailing-run
    # convention.
    satisfied_by_session = [bool(v) for v in combined.tolist()]
    consecutive = consecutive_sessions_satisfied(satisfied_by_session)
    satisfied = consecutive >= strategy.min_consecutive_sessions

    latest_candle = candles[-1]
    last_candle_date = datetime.fromtimestamp(latest_candle.ts, tz=timezone.utc).date().isoformat()

    indicator_values = {
        condition.indicator: (
            None
            if pd.isna(_indicator_series(df, condition).iloc[-1])
            else float(_indicator_series(df, condition).iloc[-1])
        )
        for condition in strategy.conditions
    }

    return ScanResultRow(
        run_id=None,
        symbol=instrument.symbol,
        kind=instrument.kind,
        satisfied=satisfied,
        consecutive_sessions=consecutive,
        latest_price=float(latest_candle.close),
        latest_ts=latest_candle.ts,
        indicator_values_json=json.dumps(indicator_values),
        last_candle_date=last_candle_date,
        strategy_name=strategy.name,
    )


def run_scan(strategy: Strategy) -> list[ScanResultRow]:
    """Evaluate `strategy` over its resolved universe.

    Returns one row per instrument, including non-matches (`satisfied=False`)
    and instruments whose fetch/evaluation failed (`latest_price=None`) - the
    result list is never shorter than the resolved instrument set, and a
    single instrument's `ProviderError` never propagates out of this
    function.
    """
    instruments = _resolve_universe(strategy)
    rows: list[ScanResultRow] = []

    for instrument in instruments:
        try:
            rows.append(_scan_one(strategy, instrument))
        except ProviderError:
            rows.append(
                ScanResultRow(
                    run_id=None,
                    symbol=instrument.symbol,
                    kind=instrument.kind,
                    satisfied=False,
                    consecutive_sessions=0,
                    latest_price=None,
                    latest_ts=None,
                    indicator_values_json=None,
                    last_candle_date=None,
                    strategy_name=strategy.name,
                )
            )

    return rows
