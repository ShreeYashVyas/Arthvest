"""Typed API responses for macroeconomic indicators."""

from datetime import datetime

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
