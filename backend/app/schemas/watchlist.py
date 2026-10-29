"""Validated local-development watchlist request and response schemas."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


_INSTRUMENT_KEY = re.compile(r"^(?:NSE_EQ|BSE_EQ)\|[A-Za-z0-9_-]{2,32}$")


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Watchlist name cannot be blank")
        return value


class WatchlistEntriesReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_keys: list[str] = Field(max_length=20)

    @field_validator("instrument_keys")
    @classmethod
    def validate_keys(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Instrument keys must be unique")
        if any(not _INSTRUMENT_KEY.fullmatch(value) for value in values):
            raise ValueError("Each key must identify a supported NSE or BSE equity")
        return values


class WatchlistInstrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_key: str
    exchange: str
    segment: str
    trading_symbol: str
    short_name: str | None
    name: str
    isin: str | None
    instrument_type: str
    lot_size: float | None
    tick_size: float | None
    source: str
    catalogue_updated_at: str | None


class WatchlistResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    instruments: list[WatchlistInstrument]


class WatchlistsResponse(BaseModel):
    watchlists: list[WatchlistResponse]
    persistence: str = "postgresql"
    scope: str = "local_single_user_development"
