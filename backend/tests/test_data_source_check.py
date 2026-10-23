"""Network-free tests for the manual live-source diagnostic."""

from typing import Any

from app.services.macro_service import INDICATORS, MacroDataError
from scripts import check_data_sources


def _healthy_result(key: str) -> dict[str, Any]:
    return {
        "observation_date": "2026-09-01",
        "freshness_status": "fresh",
        "value": 1.25,
        "unit": INDICATORS[key]["unit"],
    }


def test_source_check_reports_all_configured_series_as_validated(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        check_data_sources,
        "fetch_macro_indicator",
        lambda key: _healthy_result(key),
    )

    exit_code = check_data_sources.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Validated 8 of 8 configured sources; 0 unavailable." in output
    assert "FEDFUNDS" in output
    assert "CCRETT01INM661N" in output
    assert "FAIL" not in output


def test_source_check_continues_after_one_source_fails(
    monkeypatch, capsys
) -> None:
    def fake_fetch(key: str) -> dict[str, Any]:
        if key == "fed-funds":
            raise MacroDataError("simulated connection failure")
        return _healthy_result(key)

    monkeypatch.setattr(
        check_data_sources,
        "fetch_macro_indicator",
        fake_fetch,
    )

    exit_code = check_data_sources.main()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Validated 7 of 8 configured sources; 1 unavailable." in output
    assert "FEDFUNDS" in output
    assert "simulated connection failure" in output
