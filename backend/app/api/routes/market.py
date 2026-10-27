"""Read-only Upstox market-data endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from app.services import upstox_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market/upstox", tags=["market data"])


@router.get("/status", summary="Check whether the Upstox Analytics Token is configured")
def get_upstox_status() -> dict[str, object]:
    """Return token readiness without exposing the token itself."""
    return upstox_service.get_upstox_status()


@router.get("/quotes", summary="Get a snapshot of selected Indian market indices")
def get_upstox_quotes() -> dict[str, object]:
    """Return read-only quotes for NIFTY 50, NIFTY BANK, and INDIA VIX."""
    try:
        return upstox_service.get_market_quotes()
    except upstox_service.UpstoxServiceError as exc:
        logger.warning("Upstox market quote unavailable: %s", str(exc))
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
