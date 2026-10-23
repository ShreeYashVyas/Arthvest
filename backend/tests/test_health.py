"""Basic API smoke tests."""

from fastapi.testclient import TestClient

from app.main import app, configured_cors_origins

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "project": "Arthvest",
        "phase": "Macro Intelligence",
    }


def test_root_endpoint() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_cors_origins_default_to_local_frontend(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert configured_cors_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_support_comma_separated_deploy_hosts(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        " https://arthvest.example.com/ , https://preview.arthvest.example.com ",
    )

    assert configured_cors_origins() == [
        "https://arthvest.example.com",
        "https://preview.arthvest.example.com",
    ]
