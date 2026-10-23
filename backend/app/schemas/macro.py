"""Typed API response schemas for macroeconomic indicators and analytics."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroIndicatorResponse(BaseModel):
    """A measured macro indicator with data provenance and freshness."""

    model_config = ConfigDict(extra="forbid")

    indicator: str
    series_id: str
    value_percent: float = Field(allow_inf_nan=False)
    observation_date: str
    observation_age_days: int = Field(ge=0)
    freshness_status: Literal["fresh", "stale"]
    unit: str
    source: str
    source_url: str
    retrieved_at: datetime
    calculation: str | None = None


class MacroIndicatorMetadata(BaseModel):
    """Definitions and transparent source metadata for one configured indicator."""

    model_config = ConfigDict(extra="forbid")

    key: str
    indicator: str
    description: str
    series_id: str
    frequency: str
    unit: str
    source: str
    source_url: str
    calculation: str
    freshness_threshold_days: int = Field(ge=0)


class MacroCatalogResponse(BaseModel):
    """Catalog of indicators implemented in Arthvest."""

    generated_at: datetime
    total_count: int = Field(ge=0)
    indicators: list[MacroIndicatorMetadata]


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
