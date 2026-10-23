"""Network-free tests for FRED parsing and indicator calculations."""

import pytest

from app.services import macro_service
from app.services.macro_service import MacroDataError, _parse_fed_funds_csv, _parse_fred_csv


def test_parser_selects_latest_valid_fed_funds_observation() -> None:
    csv_text = """observation_date,FEDFUNDS
2026-07-01,3.75
2026-08-01,.
2026-06-01,4.00
2026-09-01,3.62
"""

    assert _parse_fed_funds_csv(csv_text) == {
        "observation_date": "2026-09-01",
        "value_percent": 3.62,
    }


def test_parser_sorts_rows_and_ignores_missing_values() -> None:
    csv_text = """observation_date,UNRATE
2026-09-01,4.2
2026-07-01,4.1
2026-08-01,.
"""
    assert _parse_fred_csv(csv_text, "UNRATE") == [
        ("2026-07-01", 4.1),
        ("2026-09-01", 4.2),
    ]


def test_parser_rejects_unexpected_columns() -> None:
    with pytest.raises(MacroDataError, match="expected columns"):
        _parse_fred_csv("date,value\n2026-09-01,3.62\n", "UNRATE")


def test_parser_rejects_empty_or_invalid_series() -> None:
    with pytest.raises(MacroDataError, match="no valid observations"):
        _parse_fred_csv(
            "observation_date,UNRATE\n2026-09-01,.\n2026-10-01,NaN\n",
            "UNRATE",
        )


def test_inflation_is_calculated_from_cpi_year_over_year(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = [
        ("2025-09-01", 300.0),
        ("2026-08-01", 329.0),
        ("2026-09-01", 309.0),
    ]
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: (observations, "2026-10-23T00:00:00+00:00"),
    )

    result = macro_service.fetch_macro_indicator("us-inflation")

    assert result["observation_date"] == "2026-09-01"
    assert result["value"] == 3.0
    assert result["unit"] == "percent year over year"
    assert result["series_id"] == "CPIAUCSL"


def test_unknown_indicator_key_is_rejected() -> None:
    with pytest.raises(MacroDataError, match="Unsupported"):
        macro_service.fetch_macro_indicator("not-a-real-indicator")


def test_old_observation_is_marked_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: (
            [("2010-01-01", 1.0)],
            "2026-10-23T00:00:00+00:00",
        ),
    )

    result = macro_service.fetch_macro_indicator("fed-funds")

    assert result["freshness_status"] == "stale"
    assert result["observation_age_days"] > 120


def test_future_observation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: (
            [("2099-01-01", 4.0)],
            "2026-10-23T00:00:00+00:00",
        ),
    )

    with pytest.raises(MacroDataError, match="future observation"):
        macro_service.fetch_macro_indicator("fed-funds")



def test_history_returns_latest_observations_with_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = [
        ("2026-01-01", 3.1),
        ("2026-02-01", 3.2),
        ("2026-03-01", 3.3),
        ("2026-04-01", 3.4),
    ]
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: (observations, "2026-10-23T00:00:00+00:00"),
    )

    result = macro_service.fetch_macro_history("fed-funds", limit=2)

    assert result["returned_count"] == 2
    assert result["points"] == [
        {"observation_date": "2026-03-01", "value": 3.3},
        {"observation_date": "2026-04-01", "value": 3.4},
    ]


def test_history_calculates_inflation_series(monkeypatch: pytest.MonkeyPatch) -> None:
    observations = [
        ("2025-01-01", 200.0),
        ("2025-02-01", 202.0),
        ("2026-01-01", 210.0),
        ("2026-02-01", 212.1),
    ]
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: (observations, "2026-10-23T00:00:00+00:00"),
    )

    result = macro_service.fetch_macro_history("us-inflation", limit=12)

    assert result["points"] == [
        {"observation_date": "2026-01-01", "value": 5.0},
        {"observation_date": "2026-02-01", "value": 5.0},
    ]


def test_history_rejects_out_of_range_limit() -> None:
    with pytest.raises(MacroDataError, match="between 1 and 60"):
        macro_service.fetch_macro_history("fed-funds", limit=100)



@pytest.mark.parametrize(
    ("key", "series_id", "observation_date", "expected_unit", "value"),
    [
        ("india-gdp-growth", "INDGDPRQPSMEI", "2026-07-01", "percent year over year", 8.1),
        ("india-policy-uncertainty", "INDEPUINDXM", "2026-09-01", "index", 184.61),
        ("usd-inr", "DEXINUS", "2026-10-16", "INR per USD", 94.96),
        ("india-reer", "CCRETT01INM661N", "2026-08-01", "index (2015=100)", 91.47),
    ],
)
def test_india_and_fx_series_keep_their_native_units(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    series_id: str,
    observation_date: str,
    expected_unit: str,
    value: float,
) -> None:
    monkeypatch.setattr(
        macro_service,
        "_fetch_fred_series",
        lambda _series_id: ([(observation_date, value)], "2026-10-23T00:00:00+00:00"),
    )

    result = macro_service.fetch_macro_indicator(key)

    assert result["series_id"] == series_id
    assert result["observation_date"] == observation_date
    assert result["unit"] == expected_unit
    assert result["value"] == value
    assert "value_percent" not in result
