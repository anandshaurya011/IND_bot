"""Static NSE instrument master: index constituents + index tickers.

Data is loaded once at import time from the JSON files in this package.
These are point-in-time snapshots (see each file's "_meta" key) and should
be refreshed periodically from NSE's official published index constituent
CSVs - they are NOT fetched live.
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_DIR = Path(__file__).resolve().parent

_FILES = {
    "nifty50": "nifty50.json",
    "banknifty": "banknifty.json",
    "niftyit": "niftyit.json",
    "indices": "indices.json",
}


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    yf_ticker: str
    nse_symbol: str
    kind: Literal["stock", "index"]


def _load(filename: str) -> list[Instrument]:
    with open(_DIR / filename, encoding="utf-8") as f:
        data = json.load(f)
    return [Instrument(**entry) for entry in data["constituents"]]


_UNIVERSES: dict[str, list[Instrument]] = {
    name: _load(filename) for name, filename in _FILES.items()
}

# all_stocks = union of nifty50 + banknifty + niftyit, deduped by symbol
_all_stocks: dict[str, Instrument] = {}
for _universe_name in ("nifty50", "banknifty", "niftyit"):
    for _inst in _UNIVERSES[_universe_name]:
        _all_stocks.setdefault(_inst.symbol, _inst)
_UNIVERSES["all_stocks"] = list(_all_stocks.values())

# Flat lookup table keyed by symbol, across every universe (stocks + indices).
_ALL: dict[str, Instrument] = {}
for _insts in _UNIVERSES.values():
    for _inst in _insts:
        _ALL.setdefault(_inst.symbol, _inst)


VALID_UNIVERSE_NAMES = sorted(_UNIVERSES.keys())


def list_universe(name: str) -> list[Instrument]:
    """Return the instruments in the named universe.

    `name` is one of "nifty50", "banknifty", "niftyit", "indices", "all_stocks".
    Raises KeyError for an unrecognized universe name.
    """
    return list(_UNIVERSES[name])


def resolve(symbol: str) -> Instrument | None:
    """Look up an instrument by symbol. Returns None on a miss, never raises."""
    return _ALL.get(symbol)
