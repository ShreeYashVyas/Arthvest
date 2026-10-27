"""Six-role, evidence-grounded research council for Arthvest."""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal

from agents import Agent, Runner
from pydantic import BaseModel, Field

from app.services import geopolitical_news, upstox_service
from app.services.macro_service import INDICATORS, MacroDataError, fetch_macro_history, fetch_macro_indicator

logger = logging.getLogger(__name__)


class EvidenceFinding(BaseModel):
    """A concise analytical claim tied to evidence identifiers."""

    title: str = Field(min_length=1, max_length=180)
    explanation: str = Field(min_length=1, max_length=1200)
    evidence_keys: list[str] = Field(default_factory=list)


class SpecialistReport(BaseModel):
    """Structured output from one specialist."""

    summary: str = Field(min_length=1, max_length=1800)
    findings: list[EvidenceFinding] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]


class ResearchBrief(BaseModel):
    """Structured user-facing output from the lead analyst."""

    headline: str = Field(min_length=1, max_length=180)
    executive_summary: str = Field(min_length=1, max_length=2400)
    key_findings: list[EvidenceFinding] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]


AGENT_NAMES = [
    {"name": "Macro Analyst", "role": "Interprets available macroeconomic observations and freshness."},
    {"name": "India Market Analyst", "role": "Interprets Upstox index quotes when available; reports gaps otherwise."},
    {"name": "Lead Research Analyst", "role": "Synthesizes findings and challenges unsupported claims."},
    {"name": "Geopolitical Risk Analyst", "role": "Analyzes recent GDELT headline signals and their possible economic transmission channels."},
    {"name": "Cross-Asset Analyst", "role": "Explores descriptive relationships among available macro and market observations without claiming causation."},
    {"name": "Risk & Evidence Auditor", "role": "Audits evidence references, freshness, uncertainty and unsupported conclusions."},
]


def get_agent_status() -> dict[str, object]:
    """Expose safe configuration status without revealing credentials."""
    configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {
        "provider": "OpenAI Agents SDK",
        "configured": configured,
        "model": os.getenv("ARTHVEST_AGENT_MODEL", "gpt-6-luna"),
        "agents": AGENT_NAMES,
        "workflow": "six-role council",
        "note": (
            "Configure OPENAI_API_KEY in backend/.env to run research."
            if not configured
            else "Six-role council configured. Geopolitical analysis is limited by the supplied evidence; no dedicated live-news feed is connected."
        ),
    }


def _model_name() -> str:
    return os.getenv("ARTHVEST_AGENT_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"


def _load_one_indicator(key: str) -> dict[str, object]:
    config = INDICATORS[key]
    try:
        data = fetch_macro_indicator(key)
        return {
            "key": key,
            "status": "available",
            "indicator": data.get("indicator", config["indicator"]),
            "series_id": data.get("series_id", config["series_id"]),
            "value": data.get("value"),
            "unit": data.get("unit", config["unit"]),
            "observation_date": data.get("observation_date"),
            "retrieved_at": data.get("retrieved_at"),
            "freshness_status": data.get("freshness_status", "unknown"),
            "source": data.get("source", config["source"]),
            "source_url": data.get("source_url", f"https://fred.stlouisfed.org/series/{config['series_id']}"),
            "calculation": data.get("calculation", config["calculation"]),
        }
    except MacroDataError:
        return {
            "key": key, "status": "unavailable", "indicator": config["indicator"],
            "series_id": config["series_id"], "unit": config["unit"], "source": config["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
            "reason": "Source is unavailable or its response could not be validated.",
        }
    except Exception as exc:
        logger.warning("Research context could not load indicator %s (%s)", key, type(exc).__name__)
        return {
            "key": key, "status": "unavailable", "indicator": config["indicator"],
            "series_id": config["series_id"], "unit": config["unit"], "source": config["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
            "reason": "Source is temporarily unavailable.",
        }


def _load_one_history(key: str) -> dict[str, object]:
    """Load a short source-attributed series for descriptive macro trend context."""
    config = INDICATORS[key]
    try:
        result = fetch_macro_history(key, limit=12)
        points = []
        for point in result.get("points", []):
            if not isinstance(point, dict):
                continue
            obs_date, value = point.get("observation_date"), point.get("value")
            if isinstance(obs_date, str) and isinstance(value, (int, float)) and math.isfinite(float(value)):
                points.append({"observation_date": obs_date, "value": float(value)})
        return {
            "key": key,
            "status": "available" if points else "insufficient-history",
            "unit": result.get("unit", config["unit"]),
            "frequency": result.get("frequency", config["frequency"]),
            "source_url": result.get("source_url", f"https://fred.stlouisfed.org/series/{config['series_id']}"),
            "point_count": len(points),
            "points": points,
        }
    except Exception as exc:
        logger.warning("Research history unavailable for %s (%s)", key, type(exc).__name__)
        return {
            "key": key, "status": "unavailable", "unit": config["unit"],
            "frequency": config["frequency"], "point_count": 0, "points": [],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
        }


def _load_evidence_context() -> dict[str, object]:
    """Collect validated macro observations and a best-effort read-only market snapshot."""
    keys = list(INDICATORS)
    with ThreadPoolExecutor(max_workers=min(8, len(keys))) as executor:
        macro_items = list(executor.map(_load_one_indicator, keys))

    try:
        snapshot = upstox_service.get_market_quotes()
        market = {
            "status": "available" if snapshot.get("available_count", 0) else "unavailable",
            "provider": snapshot.get("provider", "Upstox"),
            "source_url": snapshot.get("source_url"),
            "generated_at": snapshot.get("generated_at"),
            "data_as_of": snapshot.get("data_as_of"),
            "quotes": snapshot.get("quotes", []),
            "limitations": snapshot.get("limitations", []),
        }
        if not snapshot.get("available_count", 0):
            market["reason"] = "The provider returned no usable index quotes."
    except upstox_service.UpstoxServiceError:
        market = {
            "status": "unavailable", "provider": "Upstox",
            "reason": "Upstox is not configured or its read-only quote endpoint is unavailable.",
            "quotes": [],
        }

    news = geopolitical_news.fetch_geopolitical_news()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_observations": macro_items,
        "macro_history": macro_history,
        "market_snapshot": market,
        "news_snapshot": news,
        "data_quality_notes": [
            "Observation dates describe the source period; retrieval time does not make an old observation fresh.",
            "Unavailable or stale values must remain explicit and must not be imputed.",
            "No dedicated geopolitical news source is connected; geopolitical conclusions must not be framed as live-news monitoring.",
            "Cross-asset observations are descriptive and do not establish causal relationships.",
        ],
    }


def _build_agents() -> tuple[Agent, Agent, Agent, Agent, Agent, Agent]:
    model = _model_name()
    macro_agent = Agent(
        name="Macro Analyst", model=model, output_type=SpecialistReport,
        instructions=(
            "Analyze only supplied macro evidence. Distinguish observation dates from retrieval times; "
            "flag stale, in-progress, annual, quarterly and unavailable data. Use evidence_keys only from "
            "supplied indicator keys. Never invent figures, sources, events, causation, forecasts or trade advice."
        ),
    )
    market_agent = Agent(
        name="India Market Analyst", model=model, output_type=SpecialistReport,
        instructions=(
            "Analyze only the supplied Upstox snapshot. If quotes are unavailable, state that clearly. "
            "Never invent news, market breadth, price history or volatility statistics. Do not recommend trades. "
            "Use only supplied quote keys as evidence."
        ),
    )
    geopolitics_agent = Agent(
        name="Geopolitical Risk Analyst", model=model, output_type=SpecialistReport,
        instructions=(
            "Assess geopolitical risk only to the extent supported by the provided context. No live news source "
            "is connected: do not claim to know today's conflicts, announcements, sanctions or events unless "
            "explicitly present in the evidence. Distinguish general transmission channels (energy, trade, FX, "
            "risk appetite) from observed events. Label unsupported current-event questions as a data gap. "
            "Use only evidence keys present in the context; no invented facts or trading instructions."
        ),
    )
    cross_asset_agent = Agent(
        name="Cross-Asset Analyst", model=model, output_type=SpecialistReport,
        instructions=(
            "Explore descriptive relationships only among the supplied macro observations and available index "
            "quotes. The context may contain only latest values, not aligned time series, so do not calculate "
            "correlations, returns, beta or lead-lag effects unless the required historical observations exist. "
            "Do not imply causation or invent asset classes or values. Explicitly state data gaps and use only "
            "provided evidence keys."
        ),
    )
    auditor_agent = Agent(
        name="Risk & Evidence Auditor", model=model, output_type=SpecialistReport,
        instructions=(
            "Audit the question, raw evidence, and every specialist report for unsupported factual claims, "
            "missing/invalid evidence references, stale or unavailable data treated as current, causal overreach, "
            "false precision, and overconfident language. Report concrete limitations and monitoring checks. "
            "You are a critic, not a source of new market facts. Never invent evidence or give trade advice. "
            "Use only evidence keys supplied in the audit input."
        ),
    )
    lead_agent = Agent(
        name="Lead Research Analyst", model=model, output_type=ResearchBrief,
        instructions=(
            "Synthesize all five specialist reports and the raw evidence into a concise research brief. Give "
            "priority to the Risk & Evidence Auditor's valid objections. Challenge unsupported claims and prefer "
            "explicit gaps over speculation. Evidence keys must refer to supplied indicator or quote keys. "
            "Do not claim causation from co-movement, give personalized financial advice, or present output as "
            "a calibrated forecast. State material limitations clearly."
        ),
    )
    return macro_agent, market_agent, geopolitics_agent, cross_asset_agent, auditor_agent, lead_agent


def _validate_report(value: object) -> SpecialistReport:
    if isinstance(value, SpecialistReport):
        return value
    return SpecialistReport.model_validate(value)


def _valid_evidence_keys(context: dict[str, object]) -> set[str]:
    """Build the canonical evidence key set for this research run."""
    keys: set[str] = set()
    for item in context.get("macro_observations", []):
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            keys.add(item["key"])
    market = context.get("market_snapshot", {})
    quotes = market.get("quotes", []) if isinstance(market, dict) else []
    for item in quotes:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            keys.add(item["key"])
    news = context.get("news_snapshot", {})
    articles = news.get("articles", []) if isinstance(news, dict) else []
    for item in articles:
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            keys.add(item["key"])
    return keys


def _sanitize_specialist_report(report: SpecialistReport, valid_keys: set[str]) -> SpecialistReport:
    """Remove model-generated evidence keys that do not exist in the source index."""
    removed = any(key not in valid_keys for finding in report.findings for key in finding.evidence_keys)
    findings = [
        finding.model_copy(update={
            "evidence_keys": [key for key in finding.evidence_keys if key in valid_keys]
        })
        for finding in report.findings
    ]
    gaps = list(report.data_gaps)
    if removed:
        gaps.append("Unrecognized evidence references were removed by server-side validation.")
    return report.model_copy(update={"findings": findings, "data_gaps": gaps})


def _sanitize_research_brief(brief: ResearchBrief, valid_keys: set[str]) -> ResearchBrief:
    """Validate evidence identifiers in the final brief before returning it."""
    removed = any(key not in valid_keys for finding in brief.key_findings for key in finding.evidence_keys)
    findings = [
        finding.model_copy(update={
            "evidence_keys": [key for key in finding.evidence_keys if key in valid_keys]
        })
        for finding in brief.key_findings
    ]
    limitations = list(brief.limitations)
    if removed:
        limitations.append("Unsupported evidence references were removed by server-side validation.")
    return brief.model_copy(update={"key_findings": findings, "limitations": limitations})


async def run_research(question: str) -> dict[str, object]:
    """Run four specialist agents concurrently, audit their output, then synthesize."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    context = await asyncio.to_thread(_load_evidence_context)
    macro_agent, market_agent, geopolitics_agent, cross_asset_agent, auditor_agent, lead_agent = _build_agents()
    valid_keys = _valid_evidence_keys(context)
    context_json = json.dumps(context, ensure_ascii=False, allow_nan=False)
    shared_input = f"Research question: {question}\nEvidence JSON:\n{context_json}"
    macro_input = "Analyze the macroeconomic evidence.\n" + shared_input
    market_input = "Analyze the Indian market snapshot.\n" + shared_input
    geopolitical_input = "Assess geopolitical risk transmission channels and explicitly report the absence of live news evidence.\n" + shared_input
    cross_asset_input = "Analyze descriptive cross-asset context and state whether aligned time series are available.\n" + shared_input

    macro_result, market_result, geopolitical_result, cross_asset_result = await asyncio.gather(
        Runner.run(macro_agent, macro_input, max_turns=2),
        Runner.run(market_agent, market_input, max_turns=2),
        Runner.run(geopolitics_agent, geopolitical_input, max_turns=2),
        Runner.run(cross_asset_agent, cross_asset_input, max_turns=2),
    )
    macro_report = _validate_report(macro_result.final_output)
    market_report = _validate_report(market_result.final_output)
    geopolitical_report = _validate_report(geopolitical_result.final_output)
    cross_asset_report = _validate_report(cross_asset_result.final_output)

    audit_input = json.dumps({
        "question": question,
        "evidence_context": context,
        "macro_report": macro_report.model_dump(mode="json"),
        "market_report": market_report.model_dump(mode="json"),
        "geopolitical_report": geopolitical_report.model_dump(mode="json"),
        "cross_asset_report": cross_asset_report.model_dump(mode="json"),
    }, ensure_ascii=False, allow_nan=False)
    audit_result = await Runner.run(auditor_agent, audit_input, max_turns=2)
    audit_report = _sanitize_specialist_report(_validate_report(audit_result.final_output), valid_keys)

    lead_input = json.dumps({
        "question": question,
        "evidence_context": context,
        "specialist_reports": {
            "macro": macro_report.model_dump(mode="json"),
            "market": market_report.model_dump(mode="json"),
            "geopolitical_risk": geopolitical_report.model_dump(mode="json"),
            "cross_asset": cross_asset_report.model_dump(mode="json"),
            "risk_evidence_audit": audit_report.model_dump(mode="json"),
        },
    }, ensure_ascii=False, allow_nan=False)
    lead_result = await Runner.run(lead_agent, lead_input, max_turns=2)
    brief = lead_result.final_output
    if not isinstance(brief, ResearchBrief):
        brief = ResearchBrief.model_validate(brief)
    brief = _sanitize_research_brief(brief, valid_keys)

    market_available = context["market_snapshot"]["status"] == "available"
    news_status = context.get("news_snapshot", {}).get("status", "unavailable")
    news_status = context.get("news_snapshot", {}).get("status", "unavailable")
    return {
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "model": _model_name(),
        "agents": [
            {"name": "Macro Analyst", "status": "completed"},
            {"name": "India Market Analyst", "status": "completed" if market_available else "partial"},
            {"name": "Geopolitical Risk Analyst", "status": "completed" if news_status == "available" else "partial"},
            {"name": "Cross-Asset Analyst", "status": "completed_with_data_limitations"},
            {"name": "Risk & Evidence Auditor", "status": "completed"},
            {"name": "Lead Research Analyst", "status": "completed"},
        ],
        "brief": brief.model_dump(mode="json"),
        "specialist_reports": {
            "macro": macro_report.model_dump(mode="json"),
            "market": market_report.model_dump(mode="json"),
            "geopolitical_risk": geopolitical_report.model_dump(mode="json"),
            "cross_asset": cross_asset_report.model_dump(mode="json"),
            "risk_evidence_audit": audit_report.model_dump(mode="json"),
        },
        "evidence": context,
        "disclaimer": (
            "Research and decision support only. Not personalized financial advice, a calibrated forecast, "
            "or a recommendation to buy or sell securities."
        ),
    }
