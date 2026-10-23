"""Tests for indicator metadata and data-quality endpoints."""

from fastapi.testclient import TestClient

from app.api.routes import macro as macro_routes
from app.main import app
from app.services.macro_service import INDICATORS, MacroDataError

client = TestClient(app)


def _sample_payload(key: str, freshness: str = "fresh") -> dict[str, object]:
    config = INDICATORS[key]
    return {
        "indicator": config["indicator"],
        "series_id": config["series_id"],
        "value": 91.25,
        "observation_date": "2026-09-01",
        "frequency": config["frequency"],
        "observation_age_days": 2,
        "freshness_status": freshness,
        "unit": config["unit"],
        "source": config["source"],
        "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
        "retrieved_at": "2026-10-23T09:00:00+00:00",
        "calculation": config["calculation"],
    }


def test_catalog_describes_all_series_without_fetching_live_data() -> None:
    response = client.get("/api/macro/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    catalog = {item["key"]: item for item in payload["indicators"]}
    assert catalog["usd-inr"]["unit"] == "INR per USD"
    assert catalog["india-reer"]["series_id"] == "CCRETT01INM661N"
    assert catalog["india-policy-uncertainty"]["frequency"] == "Monthly"


def test_quality_summary_reports_coverage_and_staleness(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, object]:
        if key == "india-reer":
            raise MacroDataError("source unavailable")
        return _sample_payload(
            key,
            freshness="stale" if key == "us-inflation" else "fresh",
        )

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    assert payload["available_count"] == len(INDICATORS) - 1
    assert payload["unavailable_count"] == 1
    assert payload["stale_count"] == 1
    assert payload["fresh_count"] == len(INDICATORS) - 2
    assert payload["coverage_percent"] == round(
        (len(INDICATORS) - 1) / len(INDICATORS) * 100, 2
    )
    assert payload["quality_status"] == "partial"


def test_quality_summary_marks_no_data_unavailable(monkeypatch) -> None:
    def fail(_key: str) -> dict[str, object]:
        raise MacroDataError("upstream unavailable")

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fail)

    response = client.get("/api/macro/quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage_percent"] == 0
    assert payload["quality_status"] == "unavailable"
