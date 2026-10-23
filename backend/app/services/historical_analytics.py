"""Descriptive analytics over persisted, source-attributed macro observations.

Statistics here describe the archived observation window. They are not forecasts,
validated regimes, or investment recommendations.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from statistics import fmean, pstdev
from typing import Any

from app.services import observation_store
from app.services.macro_service import INDICATORS


class HistoricalAnalyticsError(ValueError):
    """Raised when an indicator or observation window cannot be analyzed."""


def _display_points(
    indicator_key: str,
    source_points: list[dict[str, Any]],
) -> list[dict[str, str | float]]:
    """Convert stored source-native values into the unit displayed by Arthvest."""
    config = INDICATORS[indicator_key]
    if config["series_id"] != "CPIAUCSL":
        return [
            {
                "observation_date": str(point["observation_date"]),
                "value": float(point["source_value"]),
            }
            for point in source_points
        ]

    # CPIAUCSL is stored as an index, but the dashboard displays year-over-year
    # inflation. Preserve that semantic distinction in archived analytics too.
    values_by_date = {
        str(point["observation_date"]): float(point["source_value"])
        for point in source_points
    }
    derived: list[dict[str, str | float]] = []
    for point in source_points:
        observation_date = date.fromisoformat(str(point["observation_date"]))
        try:
            prior_year = observation_date.replace(year=observation_date.year - 1)
        except ValueError:
            continue
        prior_value = values_by_date.get(prior_year.isoformat())
        current_value = float(point["source_value"])
        if prior_value is None or prior_value == 0:
            continue
        derived.append(
            {
                "observation_date": observation_date.isoformat(),
                "value": round((current_value / prior_value - 1) * 100, 2),
            }
        )
    return derived


def analyze_historical_values(
    indicator_key: str,
    source_points: list[dict[str, Any]],
    limit: int = 12,
) -> dict[str, Any]:
    """Calculate a transparent trend summary from chronological archived values."""
    if indicator_key not in INDICATORS:
        raise HistoricalAnalyticsError(f"Unsupported macro indicator: {indicator_key}")
    if not 2 <= limit <= 60:
        raise HistoricalAnalyticsError("Analytics limit must be between 2 and 60")

    normalized = _display_points(indicator_key, source_points)
    clean_points: list[dict[str, str | float]] = []
    for point in normalized:
        value = float(point["value"])
        if not math.isfinite(value):
            raise HistoricalAnalyticsError("Archive contains a non-finite observation")
        clean_points.append(
            {
                "observation_date": str(point["observation_date"]),
                "value": value,
            }
        )

    points = clean_points[-limit:]
    values = [float(point["value"]) for point in points]
    enough_history = len(values) >= 2
    if enough_history:
        oldest_value = values[0]
        latest_value = values[-1]
        absolute_change = latest_value - oldest_value
        relative_change = (
            (absolute_change / oldest_value) * 100
            if oldest_value != 0
            else None
        )
        direction = (
            "flat" if math.isclose(absolute_change, 0.0, abs_tol=1e-9)
            else "higher" if absolute_change > 0
            else "lower"
        )
        standard_deviation = pstdev(values)
    else:
        oldest_value = values[0] if values else None
        latest_value = values[-1] if values else None
        absolute_change = None
        relative_change = None
        direction = "insufficient-history"
        standard_deviation = None

    config = INDICATORS[indicator_key]
    unit = config["unit"]
    change_unit = "percentage points" if "percent" in unit.lower() else unit
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "key": indicator_key,
        "indicator": config["indicator"],
        "series_id": config["series_id"],
        "unit": unit,
        "change_unit": change_unit,
        "frequency": config["frequency"],
        "source": config["source"],
        "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
        "calculation": (
            "Year-over-year percentage change calculated from archived CPI index values."
            if config["series_id"] == "CPIAUCSL"
            else "Descriptive statistics computed from archived source observations."
        ),
        "requested_limit": limit,
        "returned_count": len(points),
        "period_start": points[0]["observation_date"] if points else None,
        "period_end": points[-1]["observation_date"] if points else None,
        "summary": {
            "oldest_value": round(oldest_value, 4) if oldest_value is not None else None,
            "latest_value": round(latest_value, 4) if latest_value is not None else None,
            "absolute_change": round(absolute_change, 4) if absolute_change is not None else None,
            "relative_change_percent": round(relative_change, 4) if relative_change is not None else None,
            "direction": direction,
            "mean": round(fmean(values), 4) if values else None,
            "minimum": round(min(values), 4) if values else None,
            "maximum": round(max(values), 4) if values else None,
            "population_standard_deviation": (
                round(standard_deviation, 4) if standard_deviation is not None else None
            ),
        },
        "points": points,
        "limitations": [
            "Descriptive history only; not a forecast or a validated macro regime score.",
            "Relative change is a mathematical comparison with the first returned value; absolute change uses the unit shown above.",
            "Results depend on which observations have already been archived. Configure DATABASE_URL and allow successful source fetches to populate the archive.",
            "Upstream revisions can change the current archived history; detected revisions are listed separately by the revisions endpoint.",
        ],
    }


def get_archived_indicator_analytics(indicator_key: str, limit: int = 12) -> dict[str, Any]:
    """Read archived observations and analyze the latest requested display points."""
    if indicator_key not in INDICATORS:
        raise HistoricalAnalyticsError(f"Unsupported macro indicator: {indicator_key}")
    if not 2 <= limit <= 60:
        raise HistoricalAnalyticsError("Analytics limit must be between 2 and 60")

    config = INDICATORS[indicator_key]
    source_window = min(500, limit + 12) if config["series_id"] == "CPIAUCSL" else limit
    observations = observation_store.list_archived_observations(
        config["series_id"], limit=source_window
    )
    return analyze_historical_values(indicator_key, observations, limit=limit)
