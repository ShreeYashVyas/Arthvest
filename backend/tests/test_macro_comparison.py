"""Tests for normalized historical comparison across macro indicators."""

from datetime import date

import pytest

from app.services.macro_comparison import (
    MacroComparisonError,
    analyze_macro_comparison,
)


def _stored(day: str, value: float) -> dict[str, object]:
    return {"observation_date": day, "source_value": value}


def test_comparison_rebases_each_series_to_100_and_reports_relative_movement() -> None:
    archived = {
        "fed-funds": [
            _stored("2022-01-01", 5.0),
            _stored("2024-01-01", 4.0),
            _stored("2026-01-01", 2.5),
        ],
        "us-unemployment": [
            _stored("2022-01-01", 4.0),
            _stored("2024-01-01", 5.0),
            _stored("2026-01-01", 6.0),
        ],
    }

    result = analyze_macro_comparison(
        ["fed-funds", "us-unemployment"], archived, years=5, as_of=date(2026, 10, 23)
    )

    assert result["window_start"] == "2021-10-23"
    assert result["available_count"] == 2
    rate, unemployment = result["series"]
    assert rate["points"][0]["indexed_value"] == 100
    assert rate["points"][-1]["indexed_value"] == 50
    assert rate["relative_change_percent"] == -50
    assert unemployment["points"][0]["indexed_value"] == 100
    assert unemployment["points"][-1]["indexed_value"] == 150
    assert unemployment["relative_change_percent"] == 50


def test_comparison_filters_points_to_the_selected_calendar_window() -> None:
    archived = {
        "fed-funds": [
            _stored("2020-01-01", 2.0),
            _stored("2024-01-01", 4.0),
            _stored("2026-01-01", 3.0),
        ],
        "us-unemployment": [
            _stored("2024-01-01", 5.0),
            _stored("2026-01-01", 6.0),
        ],
    }

    result = analyze_macro_comparison(
        ["fed-funds", "us-unemployment"], archived, years=1, as_of=date(2026, 10, 23)
    )

    assert result["window_start"] == "2025-10-23"
    assert result["series"][0]["observation_count"] == 1
    assert result["series"][0]["status"] == "insufficient-history"
    assert result["series"][0]["relative_change_percent"] is None


def test_comparison_flags_a_non_positive_base_instead_of_creating_a_misleading_index() -> None:
    archived = {
        "india-gdp-growth": [
            _stored("2023-01-01", -2.0),
            _stored("2025-01-01", 3.0),
        ],
        "us-unemployment": [
            _stored("2023-01-01", 4.0),
            _stored("2025-01-01", 5.0),
        ],
    }

    result = analyze_macro_comparison(
        ["india-gdp-growth", "us-unemployment"],
        archived,
        years=5,
        as_of=date(2026, 10, 23),
    )

    assert result["series"][0]["status"] == "non-positive-base-value"
    assert result["series"][0]["relative_change_percent"] is None
    assert result["series"][0]["points"] == []
    assert result["series"][1]["status"] == "available"


@pytest.mark.parametrize(
    ("keys", "years", "message"),
    [
        (["fed-funds"], 5, "between 2 and 5"),
        (["fed-funds", "fed-funds"], 5, "once"),
        (["fed-funds", "us-inflation"], 2, "1, 3, 5, or 10"),
        (["fed-funds", "unknown"], 5, "Unsupported"),
        (["fed-funds"] * 6, 5, "between 2 and 5"),
    ],
)
def test_comparison_validates_keys_and_window(keys, years, message) -> None:
    with pytest.raises(MacroComparisonError, match=message):
        analyze_macro_comparison(keys, {}, years=years, as_of=date(2026, 10, 23))


def test_comparison_rejects_non_finite_archived_values() -> None:
    archived = {
        "fed-funds": [
            _stored("2023-01-01", 4.0),
            _stored("2025-01-01", float("inf")),
        ],
        "us-unemployment": [
            _stored("2023-01-01", 4.0),
            _stored("2025-01-01", 5.0),
        ],
    }
    with pytest.raises(MacroComparisonError, match="non-finite"):
        analyze_macro_comparison(
            ["fed-funds", "us-unemployment"], archived, years=5, as_of=date(2026, 10, 23)
        )
