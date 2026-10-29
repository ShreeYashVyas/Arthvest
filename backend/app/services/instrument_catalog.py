"""Search and validate Upstox's supported NSE/BSE equity instruments."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.services.market_data import MarketDataError
from app.services.upstox_service import _analytics_token

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.upstox.com/v2/instruments/search"
MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
REQUEST_TIMEOUT_SECONDS = 10
MAX_PAGE_SIZE = 30
SEARCH_CACHE_SECONDS = 60
MASTER_CACHE_SECONDS = 6 * 60 * 60
EQUITY_SEGMENTS = {"NSE_EQ", "BSE_EQ"}
NSE_EQUITY_TYPES = {"EQ", "BE", "BZ", "SM", "ST"}
BSE_EQUITY_TYPES = {"A", "B", "M", "MT", "MS", "P", "R", "T", "TS", "X", "XT", "Z", "ZP"}
INSTRUMENT_KEY_PATTERN = re.compile(r"^(?:NSE_EQ|BSE_EQ)\|[A-Za-z0-9_-]{2,32}$")

_SEARCH_CACHE: dict[tuple[str, str, int, int], tuple[float, dict[str, Any]]] = {}
_SEARCH_LOCK = threading.Lock()
_MASTER_CACHE: tuple[float, str, list[dict[str, Any]]] | None = None
_MASTER_LOCK = threading.Lock()
_INSTRUMENTS_BY_KEY: dict[str, dict[str, Any]] = {}
_SEARCH_API_BLOCKED = False
_LAST_SEARCH_SOURCE = "Upstox instrument search"
_LAST_SEARCH_AT: str | None = None


def _fetch_json(url: str, *, token: str = "") -> tuple[int, Any]:
    global _SEARCH_API_BLOCKED
    headers = {"Accept": "application/json", "User-Agent": "Arthvest/0.3 market discovery"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            _SEARCH_API_BLOCKED = True
            raise MarketDataError("Upstox rejected the configured credential for instrument discovery.", 502) from exc
        if exc.code == 429:
            raise MarketDataError("Upstox instrument-search rate limit reached; retry later.", 503) from exc
        if exc.code >= 500:
            raise MarketDataError("Upstox instrument discovery is temporarily unavailable.", 503) from exc
        raise MarketDataError("Upstox rejected the instrument-search request.", 502) from exc
    except (TimeoutError, URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        status = 504 if isinstance(reason, TimeoutError) else 503
        message = "Upstox instrument search timed out." if status == 504 else "Could not reach Upstox instrument discovery."
        raise MarketDataError(message, status) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataError("Upstox returned malformed instrument-search data.", 502) from exc


def _normalize_instrument(record: object, source: str, catalogue_updated_at: str | None) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    key = record.get("instrument_key")
    segment = record.get("segment")
    exchange = record.get("exchange")
    symbol = record.get("trading_symbol")
    name = record.get("name")
    if (
        not isinstance(key, str)
        or not INSTRUMENT_KEY_PATTERN.fullmatch(key)
        or segment not in EQUITY_SEGMENTS
        or exchange not in {"NSE", "BSE"}
        or not isinstance(symbol, str)
        or not symbol.strip()
        or not isinstance(name, str)
        or not name.strip()
    ):
        return None
    instrument_type = record.get("instrument_type")
    if not isinstance(instrument_type, str) or not instrument_type.strip():
        return None
    instrument_type = instrument_type.strip().upper()
    allowed_types = NSE_EQUITY_TYPES if segment == "NSE_EQ" else BSE_EQUITY_TYPES
    if instrument_type not in allowed_types:
        return None
    security_type = record.get("security_type")
    if segment == "NSE_EQ" and security_type is not None and security_type not in {"NORMAL", "SME"}:
        return None
    def optional_text(field: str) -> str | None:
        value = record.get(field)
        return value.strip() if isinstance(value, str) and value.strip() else None
    def optional_number(field: str) -> float | None:
        value = record.get(field)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    normalized = {
        "instrument_key": key,
        "trading_symbol": symbol.strip(),
        "name": name.strip(),
        "short_name": optional_text("short_name"),
        "exchange": exchange,
        "segment": segment,
        "instrument_type": instrument_type,
        "isin": optional_text("isin"),
        "lot_size": optional_number("lot_size"),
        "tick_size": optional_number("tick_size"),
        "source": source,
        "catalogue_updated_at": catalogue_updated_at,
    }
    _INSTRUMENTS_BY_KEY[key] = normalized
    return normalized


def _fetch_master() -> tuple[str, list[dict[str, Any]]]:
    global _MASTER_CACHE
    now = time.monotonic()
    with _MASTER_LOCK:
        if _MASTER_CACHE and _MASTER_CACHE[0] > now:
            return _MASTER_CACHE[1], _MASTER_CACHE[2]
    try:
        request = Request(MASTER_URL, headers={"Accept": "application/gzip", "User-Agent": "Arthvest/0.3 market discovery"})
        with urlopen(request, timeout=20) as response:
            raw = response.read()
    except (HTTPError, TimeoutError, URLError, OSError) as exc:
        logger.warning("Upstox instrument master download failed (%s)", type(exc).__name__)
        raise MarketDataError("Upstox's instrument master is unavailable; no catalogue results can be provided.", 503) from exc
    try:
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MarketDataError("Upstox's instrument master could not be validated.", 502) from exc
    if not isinstance(data, list):
        raise MarketDataError("Upstox's instrument master has an unexpected format.", 502)
    updated_at = datetime.now(timezone.utc).isoformat()
    instruments = [item for row in data if (item := _normalize_instrument(row, "Upstox instrument master", updated_at))]
    if not instruments:
        raise MarketDataError("Upstox's instrument master contains no supported NSE/BSE equities.", 502)
    with _MASTER_LOCK:
        _MASTER_CACHE = (time.monotonic() + MASTER_CACHE_SECONDS, updated_at, instruments)
    return updated_at, instruments


def _master_search(query: str, exchange: str, page: int, records: int) -> dict[str, Any]:
    updated_at, all_instruments = _fetch_master()
    needle = query.casefold()
    filtered = [
        instrument for instrument in all_instruments
        if (exchange == "ALL" or instrument["exchange"] == exchange)
        and any(needle in str(instrument.get(field) or "").casefold() for field in ("name", "short_name", "trading_symbol", "isin"))
    ]
    def relevance(instrument: dict[str, Any]) -> tuple[int, str, str]:
        symbol = str(instrument.get("trading_symbol") or "").casefold()
        name = str(instrument.get("name") or "").casefold()
        isin = str(instrument.get("isin") or "").casefold()
        if isin == needle or symbol == needle:
            rank = 0
        elif symbol.startswith(needle):
            rank = 1
        elif name == needle:
            rank = 2
        elif name.startswith(needle):
            rank = 3
        else:
            rank = 4
        return rank, symbol, instrument["instrument_key"]
    filtered.sort(key=relevance)
    total = len(filtered)
    start = (page - 1) * records
    return {
        "query": query,
        "exchange": exchange,
        "instruments": filtered[start : start + records],
        "page": {"page_number": page, "total_pages": (total + records - 1) // records, "records": records, "total_records": total},
        "source": "Upstox instrument master",
        "catalogue_updated_at": updated_at,
    }


def search_instruments(query: str, exchange: str = "ALL", page: int = 1, records: int = 20) -> dict[str, Any]:
    global _LAST_SEARCH_AT, _LAST_SEARCH_SOURCE
    query = query.strip()
    exchange = exchange.upper()
    if not query or len(query) > 50 or not re.search(r"[A-Za-z0-9]", query):
        raise MarketDataError("Search query must contain 1–50 letters or digits.", 422)
    if exchange not in {"ALL", "NSE", "BSE"}:
        raise MarketDataError("Exchange must be ALL, NSE, or BSE.", 422)
    if page < 1 or records < 1 or records > MAX_PAGE_SIZE:
        raise MarketDataError(f"Page must be positive and records must be between 1 and {MAX_PAGE_SIZE}.", 422)
    cache_key = (query.casefold(), exchange, page, records)
    now = time.monotonic()
    with _SEARCH_LOCK:
        cached = _SEARCH_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
    token = _analytics_token()
    if not token or _SEARCH_API_BLOCKED:
        result = _master_search(query, exchange, page, records)
    else:
        params = urlencode({"query": query, "exchanges": exchange, "segments": "EQ", "page_number": page, "records": records})
        try:
            _, payload = _fetch_json(SEARCH_URL + "?" + params, token=token)
            if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), list):
                raise MarketDataError("Upstox returned an unexpected instrument-search response.", 502)
            page_info = payload.get("meta_data", {}).get("page", {}) if isinstance(payload.get("meta_data"), dict) else {}
            instruments = [
                item
                for row in payload["data"]
                if (item := _normalize_instrument(row, "Upstox instrument search", None))
                and (exchange == "ALL" or item["exchange"] == exchange)
            ]
            result = {
                "query": query,
                "exchange": exchange,
                "instruments": instruments,
                "page": {
                    "page_number": page_info.get("page_number", page) if isinstance(page_info, dict) else page,
                    "total_pages": page_info.get("total_pages", 1) if isinstance(page_info, dict) else 1,
                    "records": page_info.get("records", records) if isinstance(page_info, dict) else records,
                    "total_records": page_info.get("total_records", len(instruments)) if isinstance(page_info, dict) else len(instruments),
                },
                "source": "Upstox instrument search",
                "catalogue_updated_at": None,
            }
        except MarketDataError as exc:
            if exc.status_code == 422:
                raise
            logger.warning("Upstox instrument search failed (%s); trying official instrument master", exc.status_code)
            result = _master_search(query, exchange, page, records)
    with _SEARCH_LOCK:
        _SEARCH_CACHE[cache_key] = (time.monotonic() + SEARCH_CACHE_SECONDS, result)
        _LAST_SEARCH_AT = datetime.now(timezone.utc).isoformat()
        _LAST_SEARCH_SOURCE = str(result["source"])
    return result


def get_instrument(instrument_key: str) -> dict[str, Any]:
    if not INSTRUMENT_KEY_PATTERN.fullmatch(instrument_key):
        raise MarketDataError("Instrument key must identify a supported NSE or BSE equity.", 422)
    instrument = _INSTRUMENTS_BY_KEY.get(instrument_key)
    if instrument:
        return instrument
    # A persisted watchlist may be loaded after process restart; resolve its key from the provider's real master.
    _, instruments = _fetch_master()
    instrument = next((item for item in instruments if item["instrument_key"] == instrument_key), None)
    if not instrument:
        raise MarketDataError("Instrument key is not present in Upstox's current NSE/BSE equity catalogue.", 404)
    return instrument


def get_catalog_status() -> dict[str, Any]:
    master_updated_at = _MASTER_CACHE[1] if _MASTER_CACHE else None
    return {
        "provider": "Upstox",
        "search_source": _LAST_SEARCH_SOURCE,
        "search_api_available": not _SEARCH_API_BLOCKED,
        "search_api_note": (
            "Upstox search API is disabled for this process after an authorization/access denial; searches use the official instrument master."
            if _SEARCH_API_BLOCKED
            else "Search API availability is checked on demand."
        ),
        "last_search_at": _LAST_SEARCH_AT,
        "catalogue_source": "Upstox complete instrument master",
        "catalogue_updated_at": master_updated_at,
        "catalogue_cached_in_process": _MASTER_CACHE is not None,
        "catalogue_instrument_count": len(_MASTER_CACHE[2]) if _MASTER_CACHE else None,
    }
