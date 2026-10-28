"""Contract tests for the optional AI research-agent API."""

import asyncio
import json
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
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", key)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "OpenAI API"
    assert payload["provider_id"] == "openai"
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


def test_builder_defines_all_six_agent_roles_and_distinct_instructions() -> None:
    """Exercise real Agent construction; orchestration tests must not mock this away."""
    from app.services import research_agents

    agents = research_agents._build_agents()
    expected_names = [item["name"] for item in research_agents.AGENT_NAMES]

    assert [agent.name for agent in agents] == expected_names
    assert len(agents) == 6
    assert all(isinstance(agent.instructions, str) and agent.instructions.strip() for agent in agents)
    assert "only supplied macro evidence" in agents[0].instructions.lower()
    assert "upstox snapshot" in agents[1].instructions.lower()
    assert "no live news source" in agents[2].instructions.lower()
    assert "correlations" in agents[3].instructions.lower()
    assert "audit" in agents[4].instructions.lower()
    assert "synthesize all five specialist reports" in agents[5].instructions.lower()


def test_openai_agent_status_reports_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = client.get("/api/agents/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "OPENAI_API_KEY" in response.json()["note"]


def test_research_requires_openai_key_when_openai_selected(monkeypatch) -> None:
    monkeypatch.setenv("ARTHVEST_AGENT_PROVIDER", "openai")
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
        evidence_keys=["fed-funds", "nifty-50", "not-a-real-series", "india-gdp-growth"],
    )
    market_finding = EvidenceFinding(
        title="Market observation",
        explanation="A market report must cite market evidence only.",
        evidence_keys=["fed-funds", "nifty-50"],
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
    market_report = SpecialistReport(
        summary="Market report",
        findings=[market_finding],
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
        {"macro": macro_report, "market": market_report, "risk_evidence_audit": audit_report},
        brief,
        context,
    )

    assert result["allowed_keys"] == ["fed-funds", "nifty-50"]
    assert result["invalid_reference_count"] == 7
    assert macro_finding.evidence_keys == ["fed-funds"]
    assert market_finding.evidence_keys == ["nifty-50"]
    assert auditor_finding.evidence_keys == ["nifty-50"]
    assert brief.key_findings[0].evidence_keys == ["fed-funds"]
    assert any("not-a-real-series" in item for item in macro_report.data_gaps)
    assert any("nifty-50" in item for item in macro_report.data_gaps)
    assert any("fed-funds" in item for item in market_report.data_gaps)
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
    call_inputs: dict[str, str] = {}

    async def fake_run(agent, input_text, max_turns=2):
        call_order.append(agent.name)
        call_inputs[agent.name] = input_text
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
                        evidence_keys=[
                            "nifty-50" if agent.name == "India Market Analyst" else "fed-funds"
                        ],
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

    # Verify the auditor receives every specialist report and the lead receives the audit.
    audit_payload = json.loads(call_inputs["Risk & Evidence Auditor"])
    assert audit_payload["question"] == "Review macro and market risk"
    assert {
        "macro_report", "market_report", "geopolitical_report", "cross_asset_report"
    }.issubset(audit_payload)
    assert audit_payload["macro_report"]["summary"] == "Macro Analyst completed."
    assert audit_payload["cross_asset_report"]["summary"] == "Cross-Asset Analyst completed."

    lead_payload = json.loads(call_inputs["Lead Research Analyst"])
    assert set(lead_payload["specialist_reports"]) == {
        "macro", "market", "geopolitical_risk", "cross_asset", "risk_evidence_audit"
    }
    assert lead_payload["specialist_reports"]["risk_evidence_audit"]["summary"] == "Risk & Evidence Auditor completed."


def test_research_failure_returns_safe_gateway_error(monkeypatch) -> None:
    from app.services import research_agents

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    async def failing_research(_question: str):
        raise RuntimeError("provider detail that must not reach the client")

    monkeypatch.setattr(research_agents, "run_research", failing_research)
    response = client.post(
        "/api/agents/research",
        json={"question": "Check the six-agent workflow"},
    )

    assert response.status_code == 502
    assert "provider detail" not in response.text
    assert response.json()["detail"] == (
        "The AI research workflow could not complete. Check the backend log and API configuration."
    )
