"""Tests for the historical analytics endpoint and its storage requirements."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import observation_store

client = TestClient(app)


def test_analytics_requires_database_configuration(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/analytics/fed-funds")

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_analytics_rejects_unknown_indicator(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/analytics/not-an-indicator")

    assert response.status_code == 404


def test_analytics_validates_window_limit(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/arthvest-analytics-validation.db")

    response = client.get("/api/macro/analytics/fed-funds?limit=61")

    assert response.status_code == 422


def test_analytics_returns_archived_summary_when_storage_is_available(monkeypatch) -> None:
    monkeypatch.setattr(
        observation_store,
        "get_storage_summary",
        lambda: {
            "enabled": True, "available": True, "backend": "sqlite",
            "observation_count": 3, "revision_count": 0, "source_check_count": 1,
            "last_check_at": "2026-10-23T10:00:00+00:00", "note": "test store",
        },
    )
    monkeypatch.setattr(
        observation_store,
        "list_archived_observations",
        lambda _series_id, limit=12: [
            {"observation_date": "2026-07-01", "source_value": 4.0},
            {"observation_date": "2026-08-01", "source_value": 3.9},
            {"observation_date": "2026-09-01", "source_value": 3.8},
        ][-limit:],
    )

    response = client.get("/api/macro/analytics/fed-funds?limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "fed-funds"
    assert payload["summary"]["direction"] == "lower"
    assert payload["summary"]["absolute_change"] == -0.2
    assert payload["returned_count"] == 3
