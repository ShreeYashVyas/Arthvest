"""Typed API response schemas for macroeconomic indicators and analytics."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroIndicatorResponse(BaseModel):
    """A measured macro indicator with data provenance and freshness."""

    model_config = ConfigDict(extra="forbid")

    indicator: str
    series_id: str
    value: float = Field(allow_inf_nan=False)
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


class MacroQualityItem(BaseModel):
    """Quality summary for one configured indicator."""

    key: str
    status: Literal["available", "unavailable"]
    freshness_status: Literal["fresh", "stale"] | None = None
    observation_age_days: int | None = Field(default=None, ge=0)
    issue: str | None = None


class MacroQualityResponse(BaseModel):
    """Compact, transparent view of the current data quality state."""

    generated_at: datetime
    total_count: int = Field(ge=0)
    available_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    fresh_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)
    quality_status: Literal["good", "partial", "unavailable"]
    note: str
    indicators: list[MacroQualityItem]


class MacroHistoryPoint(BaseModel):
    """One dated point in a published or calculated macro series."""

    observation_date: str
    value: float = Field(allow_inf_nan=False)


class MacroHistoryResponse(BaseModel):
    """Historical points for one indicator, with the series definition attached."""

    generated_at: datetime
    retrieved_at: datetime
    key: str
    indicator: str
    series_id: str
    unit: str
    source: str
    source_url: str
    calculation: str
    requested_limit: int = Field(ge=1, le=60)
    returned_count: int = Field(ge=0)
    points: list[MacroHistoryPoint]


class MacroScoreComponent(BaseModel):
    """One input and its contribution to the provisional conditions score."""

    key: str
    indicator: str
    status: Literal["available", "stale", "unavailable"]
    value_percent: float | None = Field(default=None, allow_inf_nan=False)
    observation_date: str | None = None
    freshness_status: Literal["fresh", "stale"] | None = None
    component_score: float | None = Field(default=None, ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    weighted_points: float | None = Field(default=None, ge=0, le=100)


class USMacroScoreResponse(BaseModel):
    """Provisional score for U.S. macro conditions, not the full Arthvest regime."""

    generated_at: datetime
    available: bool
    score: float | None = Field(default=None, ge=0, le=100)
    label: Literal["supportive", "mixed", "pressured", "insufficient-data"]
    provisional: bool = True
    weights: dict[str, float]
    threshold_rules: dict[str, list[str]]
    components: list[MacroScoreComponent]
    methodology: str
    limitations: list[str]
    blockers: list[str]
