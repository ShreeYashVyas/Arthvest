"""Network-free tests for the public macro API contract."""

from typing import Any

from fastapi.testclient import TestClient

from app.api.routes import macro as macro_routes
from app.main import app
from app.services.macro_service import INDICATORS, MacroDataError

client = TestClient(app)


def _observation(
    key: str,
    *,
    freshness: str = "fresh",
    value: float = 2.5,
) -> dict[str, Any]:
    config = INDICATORS[key]
    return {
        "indicator": config["indicator"],
        "series_id": config["series_id"],
        "value": value,
        "observation_date": "2026-09-01",
        "frequency": config["frequency"],
        "unit": config["unit"],
        "source": config["source"],
        "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
        "retrieved_at": "2026-10-23T00:00:00+00:00",
        "calculation": config["calculation"],
        "observation_age_days": 0,
        "freshness_status": freshness,
    }


def test_health_endpoint_is_independent_of_upstream_data() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "project": "Arthvest",
        "phase": "Macro Intelligence",
    }


def test_catalog_returns_all_configured_indicators_without_fetching_data(
    monkeypatch,
) -> None:
    def unexpected_fetch(_key: str) -> dict[str, Any]:
        raise AssertionError("Catalog must not fetch upstream data")

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", unexpected_fetch)

    response = client.get("/api/macro/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    assert {item["key"] for item in payload["indicators"]} == set(INDICATORS)
    assert all(item["source_url"].startswith("https://fred.stlouisfed.org/series/") for item in payload["indicators"])


def test_overview_keeps_partial_results_when_a_source_fails(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, Any]:
        if key == "fed-funds":
            return _observation(key)
        raise MacroDataError("simulated upstream outage")

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == len(INDICATORS)
    assert payload["available_count"] == 1
    items = {item["key"]: item for item in payload["indicators"]}
    assert items["fed-funds"]["status"] == "available"
    assert items["us-inflation"]["status"] == "unavailable"
    assert items["us-inflation"]["data"] is None


def test_quality_endpoint_counts_fresh_stale_in_progress_and_unavailable(
    monkeypatch,
) -> None:
    freshness_by_key = {
        key: state
        for key, state in zip(
            INDICATORS,
            ["fresh", "fresh", "fresh", "fresh", "stale", "in-progress", "in-progress", "unavailable"],
            strict=True,
        )
    }

    def fake_fetch(key: str) -> dict[str, Any]:
        state = freshness_by_key[key]
        if state == "unavailable":
            raise MacroDataError("simulated source outage")
        return _observation(key, freshness=state)

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/quality")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] == 8
    assert payload["available_count"] == 7
    assert payload["unavailable_count"] == 1
    assert payload["fresh_count"] == 4
    assert payload["stale_count"] == 1
    assert payload["in_progress_count"] == 2
    assert payload["coverage_percent"] == 87.5
    assert payload["quality_status"] == "partial"


def test_score_is_withheld_when_a_required_source_is_unavailable(monkeypatch) -> None:
    def fake_fetch(key: str) -> dict[str, Any]:
        if key == "us-inflation":
            raise MacroDataError("simulated upstream outage")
        return _observation(key, value=3.0)

    monkeypatch.setattr(macro_routes, "fetch_macro_indicator", fake_fetch)

    response = client.get("/api/macro/score/us-conditions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["score"] is None
    assert payload["label"] == "insufficient-data"
    assert any("unavailable" in blocker.lower() for blocker in payload["blockers"])


def test_history_rejects_unknown_indicators_and_invalid_limits() -> None:
    unknown = client.get("/api/macro/history/not-a-real-indicator")
    invalid_limit = client.get("/api/macro/history/fed-funds?limit=61")

    assert unknown.status_code == 404
    assert invalid_limit.status_code == 422


def test_legacy_fed_funds_endpoint_maps_source_failure_to_502(monkeypatch) -> None:
    def failed_fetch() -> dict[str, Any]:
        raise MacroDataError("simulated upstream outage")

    monkeypatch.setattr(macro_routes, "fetch_fed_funds_rate", failed_fetch)

    response = client.get("/api/macro/fed-funds")

    assert response.status_code == 502
    assert "temporarily unavailable" in response.json()["detail"]



def test_history_returns_metadata_and_requested_number_of_points(monkeypatch) -> None:
    def fake_history(key: str, *, limit: int) -> dict[str, Any]:
        assert key == "fed-funds"
        assert limit == 2
        return {
            "generated_at": "2026-10-23T00:00:00+00:00",
            "retrieved_at": "2026-10-23T00:00:00+00:00",
            "key": key,
            "indicator": INDICATORS[key]["indicator"],
            "series_id": INDICATORS[key]["series_id"],
            "unit": INDICATORS[key]["unit"],
            "frequency": INDICATORS[key]["frequency"],
            "source": INDICATORS[key]["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{INDICATORS[key]['series_id']}",
            "calculation": INDICATORS[key]["calculation"],
            "requested_limit": limit,
            "returned_count": 2,
            "points": [
                {"observation_date": "2026-08-01", "value": 3.75},
                {"observation_date": "2026-09-01", "value": 3.62},
            ],
        }

    monkeypatch.setattr(macro_routes, "fetch_macro_history", fake_history)

    response = client.get("/api/macro/history/fed-funds?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_limit"] == 2
    assert payload["returned_count"] == 2
    assert payload["series_id"] == "FEDFUNDS"
    assert payload["points"][-1]["value"] == 3.62


def test_score_returns_a_provisional_result_when_all_inputs_are_fresh(
    monkeypatch,
) -> None:
    values = {"fed-funds": 2.0, "us-inflation": 3.2, "us-unemployment": 5.0}
    monkeypatch.setattr(
        macro_routes,
        "fetch_macro_indicator",
        lambda key: _observation(key, value=values[key]),
    )

    response = client.get("/api/macro/score/us-conditions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["score"] == 67.0
    assert payload["label"] == "mixed"
    assert payload["provisional"] is True
    assert payload["blockers"] == []
