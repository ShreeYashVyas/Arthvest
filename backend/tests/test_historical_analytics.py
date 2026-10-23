"""Tests for descriptive analytics over persisted macro observations."""

import pytest

from app.services.historical_analytics import (
    HistoricalAnalyticsError,
    analyze_historical_values,
)


def _stored(day: str, value: float) -> dict[str, object]:
    return {"observation_date": day, "source_value": value}


def test_rates_report_descriptive_change_and_distribution() -> None:
    source = [
        _stored("2026-06-01", 4.25),
        _stored("2026-07-01", 4.00),
        _stored("2026-08-01", 3.75),
    ]

    result = analyze_historical_values("fed-funds", source, limit=3)

    assert result["returned_count"] == 3
    assert result["period_start"] == "2026-06-01"
    assert result["period_end"] == "2026-08-01"
    assert result["summary"]["direction"] == "lower"
    assert result["summary"]["absolute_change"] == -0.5
    assert result["summary"]["relative_change_percent"] == pytest.approx(-11.7647)
    assert result["summary"]["mean"] == 4.0
    assert result["summary"]["minimum"] == 3.75
    assert result["summary"]["maximum"] == 4.25
    assert result["change_unit"] == "percentage points"


def test_cpi_analytics_derives_inflation_instead_of_reporting_index_levels() -> None:
    source = [
        _stored("2025-01-01", 100.0),
        _stored("2025-02-01", 101.0),
        _stored("2026-01-01", 104.0),
        _stored("2026-02-01", 106.05),
    ]

    result = analyze_historical_values("us-inflation", source, limit=2)

    assert result["unit"] == "percent year over year"
    assert result["points"] == [
        {"observation_date": "2026-01-01", "value": 4.0},
        {"observation_date": "2026-02-01", "value": 5.0},
    ]
    assert result["summary"]["absolute_change"] == 1.0
    assert result["change_unit"] == "percentage points"


def test_analytics_truncates_to_requested_latest_window() -> None:
    source = [
        _stored("2026-04-01", 1.0),
        _stored("2026-05-01", 2.0),
        _stored("2026-06-01", 3.0),
    ]

    result = analyze_historical_values("india-policy-uncertainty", source, limit=2)

    assert result["points"] == [
        {"observation_date": "2026-05-01", "value": 2.0},
        {"observation_date": "2026-06-01", "value": 3.0},
    ]
    assert result["summary"]["direction"] == "higher"


def test_single_observation_is_reported_as_insufficient_history() -> None:
    result = analyze_historical_values(
        "fed-funds", [_stored("2026-09-01", 3.75)], limit=12
    )

    assert result["summary"]["direction"] == "insufficient-history"
    assert result["summary"]["absolute_change"] is None
    assert result["summary"]["population_standard_deviation"] is None


@pytest.mark.parametrize("limit", [0, 1, 61, 100])
def test_analytics_rejects_out_of_range_limits(limit: int) -> None:
    with pytest.raises(HistoricalAnalyticsError, match="between 2 and 60"):
        analyze_historical_values("fed-funds", [], limit=limit)


def test_analytics_rejects_unknown_indicator() -> None:
    with pytest.raises(HistoricalAnalyticsError, match="Unsupported"):
        analyze_historical_values("unknown-indicator", [], limit=12)


def test_analytics_rejects_non_finite_archived_values() -> None:
    with pytest.raises(HistoricalAnalyticsError, match="non-finite"):
        analyze_historical_values(
            "fed-funds", [_stored("2026-09-01", float("nan"))], limit=12
        )
