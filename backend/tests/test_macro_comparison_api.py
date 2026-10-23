"""Tests for the archived macro comparison API."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import observation_store

client = TestClient(app)


def test_compare_requires_database_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get(
        "/api/macro/compare?indicators=fed-funds,us-unemployment&years=5"
    )

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_compare_returns_normalized_series_when_storage_is_available(monkeypatch) -> None:
    monkeypatch.setattr(
        observation_store,
        "get_storage_summary",
        lambda: {
            "enabled": True, "available": True, "backend": "sqlite",
            "observation_count": 4, "revision_count": 0, "source_check_count": 2,
            "last_check_at": "2026-10-23T10:00:00+00:00", "note": "test store",
        },
    )

    def fake_archive(series_id: str, limit: int = 12):
        by_series = {
            "FEDFUNDS": [
                {"observation_date": "2023-01-01", "source_value": 5.0},
                {"observation_date": "2025-01-01", "source_value": 2.5},
            ],
            "UNRATE": [
                {"observation_date": "2023-01-01", "source_value": 4.0},
                {"observation_date": "2025-01-01", "source_value": 6.0},
            ],
        }
        return by_series[series_id][-limit:]

    monkeypatch.setattr(observation_store, "list_archived_observations", fake_archive)
    response = client.get(
        "/api/macro/compare?indicators=fed-funds,us-unemployment&years=5"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["available_count"] == 2
    assert payload["series"][0]["points"][0]["indexed_value"] == 100
    assert payload["series"][0]["relative_change_percent"] == -50
    assert payload["series"][1]["relative_change_percent"] == 50


def test_compare_rejects_less_than_two_indicators(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/compare?indicators=fed-funds&years=5")

    assert response.status_code == 422


def test_compare_rejects_invalid_window(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get(
        "/api/macro/compare?indicators=fed-funds,us-unemployment&years=2"
    )

    assert response.status_code == 422


def test_compare_rejects_unknown_indicator(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get(
        "/api/macro/compare?indicators=fed-funds,not-real&years=5"
    )

    assert response.status_code == 404
