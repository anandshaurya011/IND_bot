from __future__ import annotations

import functools
import time
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


def with_retry(max_attempts: int = 3, backoff_base: float = 1.5):
    """Retry a network-calling method with exponential backoff.

    Re-raises the last exception if all attempts fail. Never swallows the
    error into a fabricated result - callers must still handle failure by
    surfacing missing/stale data, not a guessed value.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised below
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        time.sleep(backoff_base**attempt)
            raise last_exc

        return wrapper

    return decorator


def cache_candles(ttl: float):
    """In-process TTL cache keyed on (args, sorted kwargs).

    Intended for Provider methods (self, symbol, ...). Entries older than
    `ttl` seconds are treated as misses and refetched - we never serve
    arbitrarily stale data silently past its TTL.
    """

    def decorator(func):
        store: dict[tuple, tuple[float, object]] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            cached = store.get(key)
            if cached is not None and (now - cached[0]) < ttl:
                return cached[1]
            result = func(*args, **kwargs)
            store[key] = (now, result)
            return result

        wrapper.cache_clear = store.clear
        return wrapper

    return decorator
