"""Tests for the best-effort macro overview API."""

from fastapi.testclient import TestClient

from app.api.routes import macro as macro_routes
from app.main import app
from app.services.macro_service import INDICATORS, MacroDataError

client = TestClient(app)


def _sample_payload(key: str) -> dict[str, str | float]:
    config = INDICATORS[key]
    value = 3.5 if key != "us-unemployment" else 4.1
    return {
        "indicator": config["indicator"],
        "series_id": config["series_id"],
        "value": value,
        "observation_date": "2026-09-01",
        "observation_age_days": 52,
        "freshness_status": "fresh",
        "unit": config["unit"],
        "source": config["source"],
        "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
        "retrieved_at": "2026-10-23T09:00:00+00:00",
        "calculation": config["calculation"],
    }


def test_macro_overview_returns_available_indicators(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, str | float]:
        return _sample_payload(key)

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_count"] == len(INDICATORS)
    assert payload["total_count"] == len(INDICATORS)
    assert all(item["status"] == "available" for item in payload["indicators"])
    assert {item["key"] for item in payload["indicators"]} == set(INDICATORS)


def test_macro_overview_preserves_partial_results(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, str | float]:
        if key == "us-inflation":
            raise MacroDataError("upstream unavailable")
        return _sample_payload(key)

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_count"] == len(INDICATORS) - 1
    result_by_key = {item["key"]: item for item in payload["indicators"]}
    assert result_by_key["us-inflation"]["status"] == "unavailable"
    assert result_by_key["us-inflation"]["data"] is None
    assert result_by_key["fed-funds"]["status"] == "available"


def test_macro_overview_does_not_hide_all_source_failures(monkeypatch) -> None:
    def fake_fetch(_key: str) -> dict[str, str | float]:
        raise MacroDataError("source unavailable")

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_count"] == 0
    assert all(item["status"] == "unavailable" for item in payload["indicators"])


def test_fed_funds_route_remains_available(monkeypatch) -> None:
    monkeypatch.setattr(
        macro_routes,
        "fetch_fed_funds_rate",
        lambda: _sample_payload("fed-funds"),
    )

    response = client.get("/api/macro/fed-funds")

    assert response.status_code == 200
    assert response.json()["series_id"] == "FEDFUNDS"
