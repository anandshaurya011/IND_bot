from __future__ import annotations

from market_data.base import Candle, Provider, ProviderError
from market_data.nse_provider import NSEProvider
from market_data.yfinance_provider import YFinanceProvider

PROVIDERS: dict[str, Provider] = {
    "yfinance": YFinanceProvider(),
    "nse": NSEProvider(),
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]
    except KeyError as exc:
        raise ProviderError(f"unknown provider: {name}") from exc


__all__ = ["Candle", "Provider", "ProviderError", "PROVIDERS", "get_provider"]
