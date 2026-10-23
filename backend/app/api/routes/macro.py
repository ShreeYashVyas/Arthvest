"""Macro indicator HTTP endpoints."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.macro import (
    MacroIndicatorResponse,
    MacroOverviewItem,
    MacroOverviewResponse,
)
from app.services.macro_service import (
    INDICATORS,
    MacroDataError,
    fetch_macro_indicator,
    fetch_fed_funds_rate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/macro", tags=["macro indicators"])

OVERVIEW_CATEGORIES = {
    "fed-funds": "Global liquidity",
    "us-inflation": "Global economy",
    "us-unemployment": "Global economy",
}


@router.get(
    "/fed-funds",
    response_model=MacroIndicatorResponse,
    summary="Get the latest Federal Funds Effective Rate",
)
def get_fed_funds_rate() -> MacroIndicatorResponse:
    """Return the latest available FEDFUNDS observation from FRED."""
    try:
        return MacroIndicatorResponse.model_validate(fetch_fed_funds_rate())
    except MacroDataError as exc:
        logger.warning("Federal Funds Rate source unavailable: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Federal Funds Rate data is temporarily unavailable from FRED",
        ) from exc


def _load_overview_item(key: str, category: str) -> MacroOverviewItem:
    """Load one indicator without failing the entire overview if it is unavailable."""
    try:
        data = MacroIndicatorResponse.model_validate(fetch_macro_indicator(key))
        return MacroOverviewItem(
            key=key,
            category=category,
            status="available",
            data=data,
        )
    except (MacroDataError, ValidationError) as exc:
        logger.warning("Macro indicator %s unavailable: %s", key, exc)
        return MacroOverviewItem(
            key=key,
            category=category,
            status="unavailable",
            data=None,
            error="Source data is temporarily unavailable or failed validation.",
        )


@router.get(
    "/overview",
    response_model=MacroOverviewResponse,
    summary="Get a best-effort snapshot of configured macro indicators",
)
def get_macro_overview() -> MacroOverviewResponse:
    """Return all supported indicators, preserving partial results on source failure."""
    with ThreadPoolExecutor(max_workers=len(OVERVIEW_CATEGORIES)) as executor:
        futures = [
            executor.submit(_load_overview_item, key, category)
            for key, category in OVERVIEW_CATEGORIES.items()
        ]
        indicators = [future.result() for future in futures]

    available_count = sum(item.status == "available" for item in indicators)
    return MacroOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        available_count=available_count,
        total_count=len(INDICATORS),
        indicators=indicators,
    )
