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
    assert result["value_percent"] == 3.0
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
