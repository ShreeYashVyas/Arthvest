"""Network-free tests for the FRED CSV validator."""

import pytest

from app.services.macro_service import MacroDataError, _parse_fed_funds_csv


def test_parser_selects_latest_valid_observation() -> None:
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


def test_parser_ignores_missing_values() -> None:
    with pytest.raises(MacroDataError, match="no valid"):
        _parse_fed_funds_csv("""observation_date,FEDFUNDS
2026-09-01,.
""")


def test_parser_rejects_unexpected_columns() -> None:
    with pytest.raises(MacroDataError, match="expected columns"):
        _parse_fed_funds_csv("""date,value
2026-09-01,3.62
""")
