"""Contract tests for the optional AI research-agent API."""

import asyncio
from types import SimpleNamespace

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
    assert [agent["name"] for agent in payload["agents"]] == [
        "Macro Analyst",
        "India Market Analyst",
        "Geopolitical Risk Analyst",
        "Cross-Asset Analyst",
        "Risk & Evidence Auditor",
        "Lead Research Analyst",
    ]
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



def test_research_runs_four_specialists_then_auditor_then_lead(monkeypatch) -> None:
    from app.services import research_agents

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    context = {
        "generated_at": "2026-10-28T00:00:00+00:00",
        "macro_observations": [
            {"key": "fed-funds", "status": "available", "value": 3.5}
        ],
        "market_snapshot": {
            "status": "available",
            "quotes": [{"key": "nifty-50", "status": "available", "last_price": 25000.0}],
        },
        "data_quality_notes": [],
    }
    monkeypatch.setattr(research_agents, "_load_evidence_context", lambda: context)

    roles = [
        "Macro Analyst",
        "India Market Analyst",
        "Geopolitical Risk Analyst",
        "Cross-Asset Analyst",
        "Risk & Evidence Auditor",
        "Lead Research Analyst",
    ]
    monkeypatch.setattr(
        research_agents,
        "_build_agents",
        lambda: tuple(SimpleNamespace(name=name) for name in roles),
    )
    call_order: list[str] = []

    async def fake_run(agent, input_text, max_turns=2):
        call_order.append(agent.name)
        if agent.name == "Lead Research Analyst":
            output = ResearchBrief(
                headline="Test brief",
                executive_summary="Brief based on mocked evidence.",
                key_findings=[
                    EvidenceFinding(
                        title="Policy rate",
                        explanation="Evidence is present in the test context.",
                        evidence_keys=["fed-funds"],
                    )
                ],
                watch_items=[],
                limitations=[],
                confidence="moderate",
            )
        else:
            output = SpecialistReport(
                summary=f"{agent.name} completed.",
                findings=[
                    EvidenceFinding(
                        title="Source reading",
                        explanation="A mocked finding.",
                        evidence_keys=["fed-funds"],
                    )
                ],
                watch_items=["Monitor the next source update."],
                data_gaps=[],
                confidence="moderate",
            )
        return SimpleNamespace(final_output=output)

    monkeypatch.setattr(research_agents.Runner, "run", staticmethod(fake_run))

    result = asyncio.run(research_agents.run_research("Review macro and market risk"))

    assert call_order == roles
    assert [agent["name"] for agent in result["agents"]] == roles
    assert result["evidence_validation"]["invalid_reference_count"] == 0
    assert result["brief"]["key_findings"][0]["evidence_keys"] == ["fed-funds"]
    assert set(result["specialist_reports"]) == {
        "macro",
        "market",
        "geopolitical_risk",
        "cross_asset",
        "risk_evidence_audit",
    }
