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
        "observation_age_days": 2,
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



def test_macro_catalog_describes_every_configured_indicator() -> None:
    response = client.get("/api/macro/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    catalog = {item["key"]: item for item in payload["indicators"]}
    assert set(catalog) == set(INDICATORS)
    assert catalog["usd-inr"]["unit"] == "INR per USD"
    assert catalog["india-gdp-growth"]["frequency"] == "Quarterly"
    assert all(item["source_url"].startswith("https://") for item in catalog.values())


def test_macro_quality_reports_full_fresh_coverage(monkeypatch) -> None:
    monkeypatch.setattr(
        macro_routes,
        "fetch_macro_indicator",
        lambda key: _sample_payload(key),
    )

    response = client.get("/api/macro/quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    assert payload["available_count"] == len(INDICATORS)
    assert payload["coverage_percent"] == 100
    assert payload["fresh_count"] == len(INDICATORS)
    assert payload["stale_count"] == 0
    assert payload["quality_status"] == "good"


def test_macro_quality_separates_stale_from_unavailable(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, str | float]:
        if key == "us-inflation":
            raise MacroDataError("upstream unavailable")
        payload = _sample_payload(key)
        if key == "usd-inr":
            payload["freshness_status"] = "stale"
            payload["observation_age_days"] = 20
        return payload

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_status"] == "partial"
    assert payload["coverage_percent"] == round(
        (len(INDICATORS) - 1) / len(INDICATORS) * 100, 2
    )
    assert payload["stale_count"] == 1
    assert payload["unavailable_count"] == 1
    items = {item["key"]: item for item in payload["indicators"]}
    assert items["usd-inr"]["freshness_status"] == "stale"
    assert items["us-inflation"]["status"] == "unavailable"



def test_history_route_returns_typed_historical_points(monkeypatch) -> None:
    from app.services import macro_service

    history_payload = {
        "generated_at": "2026-10-23T09:00:00+00:00",
        "retrieved_at": "2026-10-23T08:55:00+00:00",
        "key": "fed-funds",
        "indicator": "Federal Funds Effective Rate",
        "series_id": "FEDFUNDS",
        "unit": "percent",
        "source": "FRED",
        "source_url": "https://fred.stlouisfed.org/series/FEDFUNDS",
        "calculation": "Latest observations.",
        "requested_limit": 2,
        "returned_count": 2,
        "points": [
            {"observation_date": "2026-08-01", "value": 3.8},
            {"observation_date": "2026-09-01", "value": 3.7},
        ],
    }
    monkeypatch.setattr(
        macro_service,
        "fetch_macro_history",
        lambda _key, limit=12: {**history_payload, "requested_limit": limit},
    )

    response = client.get("/api/macro/history/fed-funds?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["returned_count"] == 2
    assert payload["points"][-1]["value"] == 3.7


def test_history_route_rejects_unsupported_indicator(monkeypatch) -> None:
    from app.services import macro_service

    def fake_history(key: str, limit: int = 12):
        raise MacroDataError(f"Unsupported macro indicator: {key}")

    monkeypatch.setattr(macro_service, "fetch_macro_history", fake_history)

    response = client.get("/api/macro/history/not-supported")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unsupported macro indicator."


def test_score_route_returns_provisional_score_when_inputs_are_fresh(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, str | float]:
        payload = _sample_payload(key)
        if key == "fed-funds":
            payload["value"] = 2.0
        elif key == "us-inflation":
            payload["value"] = 3.2
        elif key == "us-unemployment":
            payload["value"] = 5.0
        return payload

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/score/us-conditions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["score"] == 67.0
    assert payload["provisional"] is True
    assert len(payload["components"]) == 3


def test_score_route_withholds_result_when_source_is_unavailable(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, str | float]:
        if key == "us-inflation":
            raise MacroDataError("upstream unavailable")
        return _sample_payload(key)

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/score/us-conditions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["score"] is None
    assert payload["label"] == "insufficient-data"
