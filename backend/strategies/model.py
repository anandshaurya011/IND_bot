"""Pydantic models for user-defined scanner strategies."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Condition(BaseModel):
    """A single indicator condition within a strategy."""

    indicator: str
    params: dict
    comparison: Literal["above", "below", "crosses_above", "crosses_below"]
    # Either another indicator spec (as a string) or the literal "price".
    compare_to: str


class Strategy(BaseModel):
    """A user-defined scanning strategy."""

    id: str
    user_id: str
    name: str
    universe: list[str]
    instrument_type: Literal["stock", "index", "both"]
    timeframe: str
    conditions: list[Condition]
    logic: Literal["AND", "OR"]
    min_consecutive_sessions: int
    provider: str
    enabled: bool
