"""Contract tests for the optional AI research-agent API."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_agent_status_never_exposes_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ARTHVEST_AGENT_MODEL", raising=False)
    key = "test-secret-openai-key"
    monkeypatch.setenv("OPENAI_API_KEY", key)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "OpenAI Agents SDK"
    assert payload["configured"] is True
    assert len(payload["agents"]) == 6
    assert payload["model"] == "gpt-6-luna"
    assert {agent["name"] for agent in payload["agents"]} >= {
        "Geopolitical Risk Analyst", "Cross-Asset Analyst", "Risk & Evidence Auditor"
    }
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


def test_research_rejects_whitespace_question(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    response = client.post("/api/agents/research", json={"question": "    "})

    assert response.status_code == 422


def test_research_rejects_empty_question(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    response = client.post("/api/agents/research", json={"question": ""})

    assert response.status_code == 422


def test_evidence_validator_removes_unknown_keys_from_report() -> None:
    from app.services.research_agents import EvidenceFinding, SpecialistReport
    from app.services import research_agents

    report = SpecialistReport(
        summary="Evidence check",
        findings=[EvidenceFinding(
            title="A claim",
            explanation="One supported source and one unsupported identifier.",
            evidence_keys=["fed-funds", "invented-price"],
        )],
        confidence="moderate",
    )

    result = research_agents._sanitize_specialist_report(report, {"fed-funds"})

    assert result.findings[0].evidence_keys == ["fed-funds"]
    assert any("Unrecognized evidence references were removed" in item for item in result.data_gaps)


def test_evidence_key_index_includes_macro_market_and_news_sources() -> None:
    from app.services import research_agents

    context = {
        "macro_observations": [{"key": "fed-funds"}],
        "market_snapshot": {"quotes": [{"key": "nifty-50"}]},
        "news_snapshot": {"articles": [{"key": "news-1"}]},
    }

    assert research_agents._valid_evidence_keys(context) == {"fed-funds", "nifty-50", "news-1"}
