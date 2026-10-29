"""Persistent user-owned application data for local single-user development."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.schemas.watchlist import WatchlistCreate, WatchlistEntriesReplace, WatchlistResponse, WatchlistsResponse
from app.services import instrument_catalog, market_store
from app.services.market_data import MarketDataError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


def _require_local_single_user_mode() -> None:
    if os.getenv("APP_ENV", "development").strip().lower() != "development":
        raise HTTPException(status_code=403, detail="Server-managed watchlists require configured user authentication.")


def _storage_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, market_store.MarketStorageDisabledError):
        return HTTPException(status_code=503, detail="Watchlist persistence requires DATABASE_URL.")
    logger.warning("Watchlist storage operation failed (%s)", type(exc).__name__)
    return HTTPException(status_code=503, detail="Watchlist storage is temporarily unavailable.")


@router.get("", response_model=WatchlistsResponse)
def get_watchlists() -> dict:
    _require_local_single_user_mode()
    try:
        return {"watchlists": market_store.list_watchlists()}
    except Exception as exc:
        raise _storage_failure(exc) from None


@router.post("", response_model=WatchlistResponse, status_code=201)
def create_watchlist(request: WatchlistCreate) -> dict:
    _require_local_single_user_mode()
    try:
        return market_store.create_watchlist(request.name)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A watchlist with that name already exists.") from None
    except Exception as exc:
        raise _storage_failure(exc) from None


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
def rename_watchlist(watchlist_id: int, request: WatchlistCreate) -> dict:
    _require_local_single_user_mode()
    try:
        result = market_store.rename_watchlist(watchlist_id, request.name)
        if result is None:
            raise HTTPException(status_code=404, detail="Watchlist not found.")
        return result
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(status_code=409, detail="A watchlist with that name already exists.") from None
    except Exception as exc:
        raise _storage_failure(exc) from None


@router.delete("/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: int) -> None:
    _require_local_single_user_mode()
    try:
        if not market_store.delete_watchlist(watchlist_id):
            raise HTTPException(status_code=404, detail="Watchlist not found.")
    except HTTPException:
        raise
    except Exception as exc:
        raise _storage_failure(exc) from None


@router.put("/{watchlist_id}/entries", response_model=WatchlistResponse)
def replace_watchlist_entries(watchlist_id: int, request: WatchlistEntriesReplace) -> dict:
    _require_local_single_user_mode()
    try:
        if not any(item["id"] == watchlist_id for item in market_store.list_watchlists()):
            raise HTTPException(status_code=404, detail="Watchlist not found.")
        instruments = [instrument_catalog.get_instrument(key) for key in request.instrument_keys]
        market_store.upsert_instruments(instruments)
        result = market_store.replace_watchlist_entries(watchlist_id, request.instrument_keys)
        if result is None:
            raise HTTPException(status_code=404, detail="Watchlist not found.")
        return result
    except HTTPException:
        raise
    except MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:
        raise _storage_failure(exc) from None
