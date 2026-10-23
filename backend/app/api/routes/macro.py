"""Macro indicator HTTP endpoints."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.schemas.macro import (
    MacroCatalogResponse,
    MacroHistoryResponse,
    MacroIndicatorMetadata,
    MacroIndicatorResponse,
    MacroOverviewItem,
    MacroOverviewResponse,
    MacroQualityItem,
    MacroQualityResponse,
    USMacroScoreResponse,
)
from app.services.macro_service import (
    INDICATORS,
    MacroDataError,
    fetch_macro_history,
    fetch_macro_indicator,
    fetch_fed_funds_rate,
)
from app.services.scoring_service import SCORE_WEIGHTS, calculate_us_conditions_score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/macro", tags=["macro indicators"])

OVERVIEW_CATEGORIES = {
    "fed-funds": "Global liquidity",
    "us-inflation": "Global economy",
    "us-unemployment": "Global economy",
    "india-gdp-growth": "Indian economy",
    "india-cpi-inflation-annual": "Indian economy",
    "india-policy-uncertainty": "Indian economy",
    "usd-inr": "FX & commodities",
    "india-reer": "FX & commodities",
}


@router.get(
    "/catalog",
    response_model=MacroCatalogResponse,
    summary="List supported macro indicators and their source definitions",
)
def get_macro_catalog() -> MacroCatalogResponse:
    """Return indicator definitions without making any upstream network calls."""
    metadata = [
        MacroIndicatorMetadata(
            key=key,
            indicator=config["indicator"],
            description=config["description"],
            series_id=config["series_id"],
            frequency=config["frequency"],
            unit=config["unit"],
            source=config["source"],
            source_url=f"https://fred.stlouisfed.org/series/{config['series_id']}",
            calculation=config["calculation"],
            freshness_threshold_days=int(config["max_age_days"]),
        )
        for key, config in INDICATORS.items()
    ]
    return MacroCatalogResponse(
        generated_at=datetime.now(timezone.utc),
        total_count=len(metadata),
        indicators=metadata,
    )


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


@router.get(
    "/quality",
    response_model=MacroQualityResponse,
    summary="Summarize availability and freshness of macro data",
)
def get_macro_quality() -> MacroQualityResponse:
    """Report data coverage and staleness; do not treat retrieval time as freshness."""
    overview = get_macro_overview()
    available = [item for item in overview.indicators if item.data is not None]
    fresh = [
        item
        for item in available
        if item.data is not None and item.data.freshness_status == "fresh"
    ]
    stale = [
        item
        for item in available
        if item.data is not None and item.data.freshness_status == "stale"
    ]
    in_progress = [
        item
        for item in available
        if item.data is not None and item.data.freshness_status == "in-progress"
    ]
    unavailable = [item for item in overview.indicators if item.data is None]

    if not available:
        quality_status = "unavailable"
        note = "No indicator currently has a validated observation."
    elif len(fresh) == len(overview.indicators):
        quality_status = "good"
        note = "All configured indicators have completed observations within their provisional freshness thresholds."
    else:
        quality_status = "partial"
        note = "At least one indicator is unavailable, stale, or still within an unfinished observation period; dependent scoring may be withheld."

    quality_items = []
    for item in overview.indicators:
        if item.data is None:
            quality_items.append(
                MacroQualityItem(
                    key=item.key,
                    status="unavailable",
                    issue=item.error or "Source data unavailable.",
                )
            )
        else:
            quality_items.append(
                MacroQualityItem(
                    key=item.key,
                    status="available",
                    freshness_status=item.data.freshness_status,
                    observation_age_days=item.data.observation_age_days,
                    issue=(
                        "Observation is older than the configured threshold."
                        if item.data.freshness_status == "stale"
                        else (
                            "Observation belongs to a period that has not ended yet."
                            if item.data.freshness_status == "in-progress"
                            else None
                        )
                    ),
                )
            )

    total = overview.total_count
    coverage = round((len(available) / total) * 100, 2) if total else 0.0
    return MacroQualityResponse(
        generated_at=datetime.now(timezone.utc),
        total_count=total,
        available_count=len(available),
        unavailable_count=len(unavailable),
        fresh_count=len(fresh),
        stale_count=len(stale),
        in_progress_count=len(in_progress),
        coverage_percent=coverage,
        quality_status=quality_status,
        note=note,
        indicators=quality_items,
    )



@router.get(
    "/history/{indicator_key}",
    response_model=MacroHistoryResponse,
    summary="Get historical observations for one macro indicator",
)
def get_macro_history(
    indicator_key: str,
    limit: int = Query(default=12, ge=1, le=60),
) -> MacroHistoryResponse:
    """Return at most 60 validated historical points for a supported indicator."""
    try:
        return MacroHistoryResponse.model_validate(
            fetch_macro_history(indicator_key, limit=limit)
        )
    except MacroDataError as exc:
        logger.warning("Macro history unavailable for %s: %s", indicator_key, exc)
        raise HTTPException(
            status_code=404 if "Unsupported macro indicator" in str(exc) else 502,
            detail=(
                "Unsupported macro indicator."
                if "Unsupported macro indicator" in str(exc)
                else "Historical macro observations are temporarily unavailable."
            ),
        ) from exc



@router.get(
    "/score/us-conditions",
    response_model=USMacroScoreResponse,
    summary="Get the provisional U.S. macro conditions subscore",
)
def get_us_conditions_score() -> USMacroScoreResponse:
    """Calculate a provisional U.S.-only score, withholding it when inputs are not fresh."""
    keys = list(SCORE_WEIGHTS)
    inputs: dict[str, dict[str, str | float] | None] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=len(keys)) as executor:
        futures = {
            key: executor.submit(fetch_macro_indicator, key)
            for key in keys
        }
        for key, future in futures.items():
            try:
                inputs[key] = future.result()
            except MacroDataError as exc:
                logger.warning("Score input %s unavailable: %s", key, exc)
                inputs[key] = None
                errors[key] = "Source is temporarily unavailable or could not be validated."

    result = calculate_us_conditions_score(inputs, errors)
    return USMacroScoreResponse.model_validate(result)
