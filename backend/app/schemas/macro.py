"""Typed API response schemas for macroeconomic indicators."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroIndicatorResponse(BaseModel):
    """A measured macro indicator with data provenance."""

    model_config = ConfigDict(extra="forbid")

    indicator: str
    series_id: str
    value_percent: float = Field(allow_inf_nan=False)
    observation_date: str
    unit: str
    source: str
    source_url: str
    retrieved_at: datetime
    calculation: str | None = None


class MacroOverviewItem(BaseModel):
    """Availability and value for one configured indicator."""

    model_config = ConfigDict(extra="forbid")

    key: str
    category: str
    status: Literal["available", "unavailable"]
    data: MacroIndicatorResponse | None = None
    error: str | None = None


class MacroOverviewResponse(BaseModel):
    """Snapshot of supported indicators at the time of this API response."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    available_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    indicators: list[MacroOverviewItem]
