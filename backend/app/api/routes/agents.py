"""AI research-agent endpoints."""

import logging
import os
import time
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.services import research_agents

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["AI research agents"])


_RATE_WINDOW_SECONDS = 60 * 60
_RATE_LOCK = Lock()
_REQUEST_TIMESTAMPS: dict[str, list[float]] = {}


def _configured_hourly_limit() -> int:
    try:
        return max(1, min(100, int(os.getenv("ARTHVEST_AGENT_MAX_REQUESTS_PER_HOUR", "5"))))
    except ValueError:
        return 5


def _reserve_research_request(client_id: str, now: float | None = None) -> tuple[bool, int]:
    """Reserve one request per client in a rolling hour; return (allowed, retry_after)."""
    current = time.monotonic() if now is None else now
    with _RATE_LOCK:
        recent = [
            stamp for stamp in _REQUEST_TIMESTAMPS.get(client_id, [])
            if current - stamp < _RATE_WINDOW_SECONDS
        ]
        if len(recent) >= _configured_hourly_limit():
            retry_after = max(1, int(_RATE_WINDOW_SECONDS - (current - recent[0])))
            _REQUEST_TIMESTAMPS[client_id] = recent
            return False, retry_after
        recent.append(current)
        _REQUEST_TIMESTAMPS[client_id] = recent
        if len(_REQUEST_TIMESTAMPS) > 2000:
            stale = [
                key for key, stamps in _REQUEST_TIMESTAMPS.items()
                if not any(current - stamp < _RATE_WINDOW_SECONDS for stamp in stamps)
            ]
            for key in stale:
                _REQUEST_TIMESTAMPS.pop(key, None)
        return True, 0



class ResearchRequest(BaseModel):
    """Bounded user request for a research brief."""

    question: str = Field(min_length=4, max_length=600)

    @field_validator("question", mode="before")
    @classmethod
    def trim_question(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


@router.get("/status", summary="Check AI research-agent configuration")
def get_research_agent_status() -> dict[str, object]:
    """Report readiness without disclosing the configured API key."""
    return research_agents.get_agent_status()


@router.post("/research", summary="Run the six-agent Arthvest research workflow")
async def create_research_brief(request: ResearchRequest, http_request: Request) -> dict[str, object]:
    """Collect source context, run specialist agents, and synthesize a research brief."""
    if not research_agents.get_agent_status()["configured"]:
        raise HTTPException(
            status_code=503,
            detail="AI agents are not configured. Add OPENAI_API_KEY to backend/.env and restart the backend.",
        )

    client_id = http_request.client.host if http_request.client else "unknown"
    allowed, retry_after = _reserve_research_request(client_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Research request limit reached for this client. Try again after the rate-limit window.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        return await research_agents.run_research(request.question.strip())
    except Exception as exc:
        logger.exception("AI research workflow failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The AI research workflow could not complete. Check the backend log and API configuration.",
        ) from exc
