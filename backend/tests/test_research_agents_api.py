"""Contract tests for the optional AI research-agent API."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.research_agents import (
    EvidenceFinding,
    ResearchBrief,
    SpecialistReport,
    _validate_evidence_references,
)

client = TestClient(app)


def test_agent_status_never_exposes_api_key(monkeypatch) -> None:
    key = "test-secret-openai-key"
    monkeypatch.setenv("OPENAI_API_KEY", key)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "OpenAI Agents SDK"
    assert payload["configured"] is True
    assert len(payload["agents"]) == 6
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



def test_evidence_validator_removes_unknown_and_unavailable_keys() -> None:
    macro_finding = EvidenceFinding(
        title="Macro observation",
        explanation="A source-based finding.",
        evidence_keys=["fed-funds", "not-a-real-series", "india-gdp-growth"],
    )
    auditor_finding = EvidenceFinding(
        title="Audit note",
        explanation="The unsupported reference should be removed.",
        evidence_keys=["nifty-50", "fabricated-quote"],
    )
    macro_report = SpecialistReport(
        summary="Macro report",
        findings=[macro_finding],
        watch_items=[],
        data_gaps=[],
        confidence="moderate",
    )
    audit_report = SpecialistReport(
        summary="Audit report",
        findings=[auditor_finding],
        watch_items=[],
        data_gaps=[],
        confidence="low",
    )
    brief = ResearchBrief(
        headline="Research brief",
        executive_summary="Summary.",
        key_findings=[
            EvidenceFinding(
                title="Lead finding",
                explanation="The lead must not cite unavailable data.",
                evidence_keys=["fed-funds", "india-gdp-growth", "unknown-key"],
            )
        ],
        watch_items=[],
        limitations=[],
        confidence="low",
    )
    context = {
        "macro_observations": [
            {"key": "fed-funds", "status": "available"},
            {"key": "india-gdp-growth", "status": "unavailable"},
        ],
        "market_snapshot": {
            "status": "available",
            "quotes": [{"key": "nifty-50", "status": "available"}],
        },
    }

    result = _validate_evidence_references(
        {"macro": macro_report, "risk_evidence_audit": audit_report},
        brief,
        context,
    )

    assert result["allowed_keys"] == ["fed-funds", "nifty-50"]
    assert result["invalid_reference_count"] == 5
    assert macro_finding.evidence_keys == ["fed-funds"]
    assert auditor_finding.evidence_keys == ["nifty-50"]
    assert brief.key_findings[0].evidence_keys == ["fed-funds"]
    assert any("not-a-real-series" in item for item in macro_report.data_gaps)
    assert any("fabricated-quote" in item for item in audit_report.data_gaps)
    assert any("unknown-key" in item for item in brief.limitations)
