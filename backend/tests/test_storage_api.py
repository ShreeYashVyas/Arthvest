"""Tests for the optional archive API contract."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_storage_endpoint_reports_disabled_without_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/storage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["backend"] == "disabled"
    assert payload["observation_count"] == 0


def test_archive_returns_clear_service_unavailable_when_database_is_unset(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/archive/fed-funds")

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_revision_route_validates_indicator_and_query_limit(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    unknown = client.get("/api/macro/revisions/not-a-real-indicator")
    invalid_limit = client.get("/api/macro/revisions/fed-funds?limit=101")

    assert unknown.status_code == 404
    assert invalid_limit.status_code == 422


def test_source_checks_returns_clear_service_unavailable_without_database(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = client.get("/api/macro/source-checks")

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
