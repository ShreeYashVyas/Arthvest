"""Contract tests for the optional AI research-agent API."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_agent_status_never_exposes_api_key(monkeypatch) -> None:
    key = "test-secret-openai-key"
    monkeypatch.setenv("OPENAI_API_KEY", key)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "OpenAI Agents SDK"
    assert payload["configured"] is True
    assert len(payload["agents"]) == 3
    assert key not in response.text


def test_agent_status_reports_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "OPENAI_API_KEY" in response.json()["note"]


def test_research_requires_openai_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.post(
        "/api/agents/research",
        json={"question": "Summarize current macro risks for India"},
    )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_research_rejects_empty_question(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    response = client.post("/api/agents/research", json={"question": ""})

    assert response.status_code == 422
