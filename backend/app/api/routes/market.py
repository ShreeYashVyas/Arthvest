"""Read-only Upstox market-data endpoints."""

import asyncio
import json
import logging
import uuid
from datetime import date, timedelta
from typing import Literal
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from websockets.asyncio.client import connect as websocket_connect

from app.services import instrument_catalog, market_data, market_stream, upstox_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/market/upstox", tags=["market data"])
market_data_router = APIRouter(prefix="/api/market", tags=["market data"])
_STREAM_SLOT = asyncio.Semaphore(1)


@market_data_router.get("/status", summary="Check the selected market-data provider")
def get_market_data_status() -> dict[str, object]:
    try:
        return market_data.get_market_data_status()
    except market_data.MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@market_data_router.get("/quotes", summary="Get normalized market quotes from the selected provider")
def get_market_data_quotes(
    symbols: str | None = Query(default=None, description="Comma-separated symbol keys, names, or instrument IDs"),
) -> dict[str, object]:
    requested_symbols = None if symbols is None else [item.strip() for item in symbols.split(",")]
    try:
        return market_data.get_market_quotes(requested_symbols)
    except market_data.MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@market_data_router.get("/instruments/search", summary="Search Upstox NSE and BSE equity instruments")
def search_market_instruments(
    q: str = Query(min_length=1, max_length=50),
    exchange: Literal["ALL", "NSE", "BSE"] = Query(default="ALL"),
    page: int = Query(default=1, ge=1),
    records: int = Query(default=20, ge=1, le=30),
) -> dict[str, object]:
    try:
        return instrument_catalog.search_instruments(q, exchange, page, records)
    except market_data.MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@market_data_router.get("/instruments/catalog/status", summary="Instrument catalogue source and cache status")
def get_instrument_catalog_status() -> dict[str, object]:
    return instrument_catalog.get_catalog_status()


@market_data_router.get("/instruments/{instrument_key:path}/quote", summary="Get a quote for a resolved NSE/BSE equity")
def get_instrument_quote(instrument_key: str) -> dict[str, object]:
    try:
        return market_data.get_instrument_quote(unquote(instrument_key))
    except market_data.MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@market_data_router.get("/instruments/{instrument_key:path}/history", summary="Get genuine Upstox historical candles")
def get_instrument_history(
    instrument_key: str,
    unit: Literal["minutes", "hours", "days", "weeks", "months"] = Query(default="days"),
    interval: int = Query(default=1, ge=1, le=300),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> dict[str, object]:
    try:
        return market_data.get_instrument_history(
            unquote(instrument_key), unit=unit, interval=interval,
            from_date=from_date or date.today() - timedelta(days=365),
            to_date=to_date or date.today(),
        )
    except market_data.MarketDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@market_data_router.websocket("/stream/{instrument_key:path}")
async def stream_instrument_quote(websocket: WebSocket, instrument_key: str) -> None:
    """Bridge one selected instrument's Upstox V3 feed to a browser websocket."""
    await websocket.accept()
    instrument_key = unquote(instrument_key)
    upstream = None
    acquired = False
    upstream_task: asyncio.Task | None = None
    browser_task: asyncio.Task | None = None
    try:
        instrument = instrument_catalog.get_instrument(instrument_key)
        if market_data._selected_provider_name() != "upstox":
            raise market_data.MarketDataError("Live stock streaming requires Upstox to be selected.", 503)
        try:
            await asyncio.wait_for(_STREAM_SLOT.acquire(), timeout=2)
            acquired = True
        except TimeoutError as exc:
            raise market_data.MarketDataError("The live-feed connection limit is currently in use.", 503) from exc
        authorized_uri = await asyncio.to_thread(upstox_service.get_market_feed_authorized_url)
        upstream = await websocket_connect(authorized_uri, open_timeout=10, ping_interval=20, max_size=1_000_000)
        subscribe = {
            "guid": uuid.uuid4().hex,
            "method": "sub",
            "data": {"mode": "ltpc", "instrumentKeys": [instrument_key]},
        }
        await upstream.send(json.dumps(subscribe).encode("utf-8"))
        await websocket.send_json({"type": "connected", "provider": "Upstox Market Data Feed V3", "mode": "ltpc"})
        upstream_task = asyncio.create_task(upstream.recv())
        browser_task = asyncio.create_task(websocket.receive())
        while True:
            done, _ = await asyncio.wait(
                {upstream_task, browser_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if browser_task in done:
                message = browser_task.result()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("text") == "unsubscribe":
                    await upstream.send(json.dumps({
                        "guid": uuid.uuid4().hex,
                        "method": "unsub",
                        "data": {"mode": "ltpc", "instrumentKeys": [instrument_key]},
                    }).encode("utf-8"))
                    break
                browser_task = asyncio.create_task(websocket.receive())
            if upstream_task in done:
                payload = upstream_task.result()
                if isinstance(payload, bytes):
                    try:
                        updates = market_stream.decode_market_feed(payload, instrument)
                    except ValueError as exc:
                        raise market_data.MarketDataError("Upstox sent a malformed live-feed update.", 502) from exc
                    for update in updates:
                        await websocket.send_json({"type": "quote", "quote": update})
                upstream_task = asyncio.create_task(upstream.recv())
    except WebSocketDisconnect:
        pass
    except (market_data.MarketDataError, upstox_service.UpstoxServiceError) as exc:
        try:
            await websocket.send_json({"type": "unavailable", "detail": str(exc)})
            await websocket.close(code=1011)
        except Exception:
            pass
    except Exception as exc:
        logger.warning("Upstox live stream ended (%s)", type(exc).__name__)
        try:
            await websocket.send_json({"type": "disconnected", "detail": "The Upstox live feed disconnected."})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        for task in (upstream_task, browser_task):
            if task is not None and not task.done():
                task.cancel()
        if upstream is not None:
            try:
                await upstream.close()
            except Exception:
                pass
        if acquired:
            _STREAM_SLOT.release()


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
