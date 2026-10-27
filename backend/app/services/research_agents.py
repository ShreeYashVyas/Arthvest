"""Evidence-grounded multi-agent research workflow for Arthvest."""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Literal

from agents import Agent, Runner
from pydantic import BaseModel, Field

from app.services import upstox_service
from app.services.macro_service import INDICATORS, MacroDataError, fetch_macro_indicator

logger = logging.getLogger(__name__)


class EvidenceFinding(BaseModel):
    """A concise analytical claim tied to one or more indicator keys."""

    title: str = Field(min_length=1, max_length=180)
    explanation: str = Field(min_length=1, max_length=1200)
    evidence_keys: list[str] = Field(default_factory=list)


class SpecialistReport(BaseModel):
    """Structured output from a specialist agent."""

    summary: str = Field(min_length=1, max_length=1800)
    findings: list[EvidenceFinding] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]


class ResearchBrief(BaseModel):
    """Structured, user-facing output from the lead research agent."""

    headline: str = Field(min_length=1, max_length=180)
    executive_summary: str = Field(min_length=1, max_length=2400)
    key_findings: list[EvidenceFinding] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: Literal["low", "moderate", "high"]


AGENT_NAMES = [
    {"name": "Macro Analyst", "role": "Interprets available macroeconomic observations and freshness."},
    {"name": "India Market Analyst", "role": "Interprets Upstox index quotes when available; reports gaps otherwise."},
    {"name": "Lead Research Analyst", "role": "Challenges and synthesizes the specialist reports into a brief."},
]


def get_agent_status() -> dict[str, object]:
    """Expose safe configuration status without exposing secrets."""
    return {
        "provider": "OpenAI Agents SDK",
        "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "model": os.getenv("ARTHVEST_AGENT_MODEL", "gpt-4.1-mini"),
        "agents": AGENT_NAMES,
        "note": (
            "Configure OPENAI_API_KEY in backend/.env to run research."
            if not os.getenv("OPENAI_API_KEY", "").strip()
            else "Research agents are configured. Runs use source snapshots available at request time."
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
            "source_url": data.get(
                "source_url", f"https://fred.stlouisfed.org/series/{config['series_id']}"
            ),
            "calculation": data.get("calculation", config["calculation"]),
        }
    except MacroDataError:
        return {
            "key": key,
            "status": "unavailable",
            "indicator": config["indicator"],
            "series_id": config["series_id"],
            "unit": config["unit"],
            "source": config["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
            "reason": "Source is unavailable or its response could not be validated.",
        }
    except Exception as exc:
        logger.warning("Research context could not load indicator %s (%s)", key, type(exc).__name__)
        return {
            "key": key,
            "status": "unavailable",
            "indicator": config["indicator"],
            "series_id": config["series_id"],
            "unit": config["unit"],
            "source": config["source"],
            "source_url": f"https://fred.stlouisfed.org/series/{config['series_id']}",
            "reason": "Source is temporarily unavailable.",
        }


def _load_evidence_context() -> dict[str, object]:
    """Collect validated source observations and a best-effort market snapshot."""
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
            "status": "unavailable",
            "provider": "Upstox",
            "reason": "Upstox is not configured or its read-only quote endpoint is unavailable.",
            "quotes": [],
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "macro_observations": macro_items,
        "market_snapshot": market,
        "data_quality_notes": [
            "Observation dates describe the source period; retrieval time does not make an old observation fresh.",
            "Unavailable or stale values must remain explicit and must not be imputed.",
            "The current U.S. conditions subscore is provisional and is not a market-return forecast.",
        ],
    }


def _build_agents() -> tuple[Agent, Agent, Agent]:
    model = _model_name()
    macro_agent = Agent(
        name="Macro Analyst",
        model=model,
        output_type=SpecialistReport,
        instructions=(
            "You are Arthvest's macroeconomics research specialist. Analyze only the JSON evidence "
            "provided by the application. Distinguish source observation dates from retrieval times, "
            "and call out stale, in-progress, unavailable, annual, and quarterly data correctly. "
            "Use evidence_keys only from the supplied indicator keys. Do not invent figures, sources, "
            "events, causal links, forecasts, or trading advice. If evidence is weak, say so. "
            "Return a concise structured report."
        ),
    )
    market_agent = Agent(
        name="India Market Analyst",
        model=model,
        output_type=SpecialistReport,
        instructions=(
            "You are Arthvest's India market-data specialist. Analyze only the supplied Upstox snapshot. "
            "Use only available quote values and the supplied timestamps. If quotes are unavailable, "
            "state that market analysis is blocked and do not infer prices or market direction. "
            "Never invent external news, market breadth, price history, or volatility statistics. "
            "Do not make trade recommendations. evidence_keys may use only quote keys from the input. "
            "Return a concise structured report."
        ),
    )
    lead_agent = Agent(
        name="Lead Research Analyst",
        model=model,
        output_type=ResearchBrief,
        instructions=(
            "You are the lead analyst for Arthvest, a research-first macro intelligence product. "
            "Synthesize the provided raw evidence and specialist reports; challenge unsupported claims "
            "and prefer explicit gaps over speculation. Evidence keys must refer to supplied indicator "
            "keys or quote keys. Do not claim causation from co-movement. Never give personalized "
            "financial advice or trading instructions. State that this is descriptive decision support, "
            "not a forecast, where relevant. Produce a readable research brief with concise findings."
        ),
    )
    return macro_agent, market_agent, lead_agent


async def run_research(question: str) -> dict[str, object]:
    """Run two specialists in parallel and a lead agent over their evidence-grounded reports."""
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    context = await asyncio.to_thread(_load_evidence_context)
    macro_agent, market_agent, lead_agent = _build_agents()
    context_json = json.dumps(context, ensure_ascii=False, allow_nan=False)
    macro_input = (
        "Analyze the macro portion of this evidence and the user's research question.\n"
        f"Question: {question}\nEvidence JSON:\n{context_json}"
    )
    market_input = (
        "Analyze the Indian market portion of this evidence and the user's research question.\n"
        f"Question: {question}\nEvidence JSON:\n{context_json}"
    )

    macro_result, market_result = await asyncio.gather(
        Runner.run(macro_agent, macro_input, max_turns=2),
        Runner.run(market_agent, market_input, max_turns=2),
    )
    macro_report = macro_result.final_output
    market_report = market_result.final_output
    if not isinstance(macro_report, SpecialistReport):
        macro_report = SpecialistReport.model_validate(macro_report)
    if not isinstance(market_report, SpecialistReport):
        market_report = SpecialistReport.model_validate(market_report)

    lead_input = json.dumps(
        {
            "question": question,
            "evidence_context": context,
            "macro_specialist_report": macro_report.model_dump(mode="json"),
            "market_specialist_report": market_report.model_dump(mode="json"),
        },
        ensure_ascii=False,
        allow_nan=False,
    )
    lead_result = await Runner.run(lead_agent, lead_input, max_turns=2)
    brief = lead_result.final_output
    if not isinstance(brief, ResearchBrief):
        brief = ResearchBrief.model_validate(brief)

    return {
        "status": "ready",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "model": _model_name(),
        "agents": [
            {"name": "Macro Analyst", "status": "completed"},
            {
                "name": "India Market Analyst",
                "status": "completed" if context["market_snapshot"]["status"] == "available" else "partial",
            },
            {"name": "Lead Research Analyst", "status": "completed"},
        ],
        "brief": brief.model_dump(mode="json"),
        "specialist_reports": {
            "macro": macro_report.model_dump(mode="json"),
            "market": market_report.model_dump(mode="json"),
        },
        "evidence": context,
        "disclaimer": (
            "Research and decision support only. Not personalized financial advice, a calibrated forecast, "
            "or a recommendation to buy or sell securities."
        ),
    }
