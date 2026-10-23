"""Normalized multi-indicator comparisons over archived macro observations."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from app.services import observation_store
from app.services.historical_analytics import _display_points
from app.services.macro_service import INDICATORS

ALLOWED_WINDOWS_YEARS = {1, 3, 5, 10}
MAX_COMPARISON_INDICATORS = 5


class MacroComparisonError(ValueError):
    """Raised when a requested macro comparison cannot be calculated."""


def _subtract_years(day: date, years: int) -> date:
    """Subtract calendar years, handling leap day without changing the month."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def analyze_macro_comparison(
    indicator_keys: list[str],
    archived_source_points: dict[str, list[dict[str, Any]]],
    years: int = 5,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Rebase each series to 100 at its first archived point in a calendar window.

    Series retain their native display meaning. Each series has its own actual
    first/last observation dates because upstream frequencies and release dates differ.
    """
    if years not in ALLOWED_WINDOWS_YEARS:
        raise MacroComparisonError("Comparison window must be 1, 3, 5, or 10 years")
    if not 2 <= len(indicator_keys) <= MAX_COMPARISON_INDICATORS:
        raise MacroComparisonError("Select between 2 and 5 indicators")
    if len(set(indicator_keys)) != len(indicator_keys):
        raise MacroComparisonError("Each indicator can only be selected once")
    unknown = [key for key in indicator_keys if key not in INDICATORS]
    if unknown:
        raise MacroComparisonError("Unsupported macro indicator: " + ", ".join(unknown))

    end_date = as_of or date.today()
    start_date = _subtract_years(end_date, years)
    series: list[dict[str, Any]] = []

    for key in indicator_keys:
        config = INDICATORS[key]
        source_points = archived_source_points.get(key, [])
        display_points = _display_points(key, source_points)
        clean_points: list[dict[str, str | float]] = []
        for point in display_points:
            value = float(point["value"])
            if not math.isfinite(value):
                raise MacroComparisonError(f"Archive contains a non-finite value for {key}")
            observation_date = date.fromisoformat(str(point["observation_date"]))
            if start_date <= observation_date <= end_date:
                clean_points.append({
                    "observation_date": observation_date.isoformat(),
                    "value": value,
                })
        clean_points.sort(key=lambda point: str(point["observation_date"]))

        base_value = float(clean_points[0]["value"]) if clean_points else None
        latest_value = float(clean_points[-1]["value"]) if clean_points else None
        status = "available"
        reason = None
        indexed_points: list[dict[str, Any]] = []

        if len(clean_points) < 2:
            status = "insufficient-history"
            reason = "Fewer than two archived observations fall inside this calendar window."
            indexed_points = [
                {
                    "observation_date": str(point["observation_date"]),
                    "raw_value": float(point["value"]),
                    "indexed_value": 100.0,
                }
                for point in clean_points
            ]
        elif base_value is not None and base_value <= 0:
            status = "non-positive-base-value"
            reason = "Relative indexing requires a positive first observation; this series is shown without a normalized trend."
        else:
            assert base_value is not None
            indexed_points = [
                {
                    "observation_date": str(point["observation_date"]),
                    "raw_value": float(point["value"]),
                    "indexed_value": round((float(point["value"]) / base_value) * 100, 4),
                }
                for point in clean_points
            ]

        change_percent = None
        if status == "available" and base_value is not None and latest_value is not None:
            change_percent = round(((latest_value / base_value) - 1) * 100, 4)

        series.append({
            "key": key,
            "indicator": config["indicator"],
            "series_id": config["series_id"],
            "unit": config["unit"],
            "frequency": config["frequency"],
            "source": config["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
            "status": status,
            "reason": reason,
            "period_start": str(clean_points[0]["observation_date"]) if clean_points else None,
            "period_end": str(clean_points[-1]["observation_date"]) if clean_points else None,
            "observation_count": len(clean_points),
            "base_value": round(base_value, 4) if base_value is not None else None,
            "latest_value": round(latest_value, 4) if latest_value is not None else None,
            "relative_change_percent": change_percent,
            "points": indexed_points,
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "requested_indicators": indicator_keys,
        "available_count": sum(item["status"] == "available" for item in series),
        "series": series,
        "methodology": (
            "Each indicator is independently rebased to 100 at its first archived display observation "
            "inside the selected calendar window. The latest index shows relative movement from that "
            "series-specific base, not whether the movement is economically good or bad."
        ),
        "limitations": [
            "Observation dates differ across series because source frequencies and release schedules differ; dates are not interpolated.",
            "Series with fewer than two in-window observations or a non-positive starting value are not normalized.",
            "For U.S. CPI inflation, the displayed series is derived year-over-year inflation calculated from archived raw CPI index levels.",
            "This is a descriptive relative-trend comparison, not a forecast, correlation estimate, causal model, or calibrated macro regime score.",
            "Results depend on the observations already retained in the database; an empty archive is not replaced with fabricated values.",
        ],
    }


def get_archived_macro_comparison(
    indicator_keys: list[str],
    years: int = 5,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Load archived source values for the requested indicators and compare them."""
    if years not in ALLOWED_WINDOWS_YEARS:
        raise MacroComparisonError("Comparison window must be 1, 3, 5, or 10 years")
    if not 2 <= len(indicator_keys) <= MAX_COMPARISON_INDICATORS:
        raise MacroComparisonError("Select between 2 and 5 indicators")
    if len(set(indicator_keys)) != len(indicator_keys):
        raise MacroComparisonError("Each indicator can only be selected once")
    unknown = [key for key in indicator_keys if key not in INDICATORS]
    if unknown:
        raise MacroComparisonError("Unsupported macro indicator: " + ", ".join(unknown))

    archived: dict[str, list[dict[str, Any]]] = {}
    for key in indicator_keys:
        archived[key] = observation_store.list_archived_observations(
            INDICATORS[key]["series_id"], limit=10000
        )
    return analyze_macro_comparison(indicator_keys, archived, years=years, as_of=as_of)
