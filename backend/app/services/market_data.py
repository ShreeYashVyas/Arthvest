"""Provider-independent market quote selection, normalization, and short caching."""

from __future__ import annotations

import copy
from concurrent.futures import Future, TimeoutError as FutureTimeout
import json
import logging
import math
import os
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.services import upstox_service

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 8
DEFAULT_CACHE_SECONDS = 30
MAX_CACHE_SECONDS = 300
STALE_AFTER_SECONDS = 300
# Allow small provider/backend clock skew without treating materially future data as current.
FUTURE_TIMESTAMP_TOLERANCE_SECONDS = 2.0
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
YAHOO_SOURCE_URL = "https://finance.yahoo.com/"

INSTRUMENTS: tuple[dict[str, str], ...] = (
    {
        "key": "nifty-50",
        "symbol": "NIFTY 50",
        "instrument_id": "NSE_INDEX|Nifty 50",
        "yahoo_symbol": "^NSEI",
    },
    {
        "key": "nifty-bank",
        "symbol": "NIFTY BANK",
        "instrument_id": "NSE_INDEX|Nifty Bank",
        "yahoo_symbol": "^NSEBANK",
    },
    {
        "key": "india-vix",
        "symbol": "INDIA VIX",
        "instrument_id": "NSE_INDEX|India VIX",
        "yahoo_symbol": "^INDIAVIX",
    },
)
INSTRUMENT_BY_KEY = {item["key"]: item for item in INSTRUMENTS}
INSTRUMENT_BY_ID = {item["instrument_id"].casefold(): item for item in INSTRUMENTS}
INSTRUMENT_BY_SYMBOL = {item["symbol"].casefold(): item for item in INSTRUMENTS}


class MarketDataError(RuntimeError):
    """A safe-to-return provider or configuration failure."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class MarketProvider(Protocol):
    name: str

    def fetch(self, instruments: list[dict[str, str]]) -> list[dict[str, object]]: ...


def _cache_seconds() -> int:
    try:
        requested = int(os.getenv("MARKET_DATA_CACHE_SECONDS", str(DEFAULT_CACHE_SECONDS)))
    except ValueError:
        requested = DEFAULT_CACHE_SECONDS
    return max(0, min(MAX_CACHE_SECONDS, requested))


def _provider_setting() -> str:
    configured = os.getenv("MARKET_DATA_PROVIDER", "auto").strip().lower() or "auto"
    if configured not in {"auto", "upstox", "yahoo"}:
        raise MarketDataError(
            "MARKET_DATA_PROVIDER must be auto, upstox, or yahoo.", 500
        )
    return configured


def _selected_provider_name() -> str:
    setting = _provider_setting()
    if setting == "upstox":
        return "upstox"
    if setting == "yahoo":
        return "yahoo"
    return "upstox" if upstox_service._analytics_token() else "yahoo"


def get_market_data_status() -> dict[str, object]:
    """Describe the selected provider without making a market-data request."""
    setting = _provider_setting()
    provider = _selected_provider_name()
    if provider == "upstox":
        configured = bool(upstox_service._analytics_token())
        provider_name = "Upstox"
        note = (
            "Read-only Upstox market data is selected."
            if configured
            else "Upstox is selected but UPSTOX_ANALYTICS_TOKEN is not configured."
        )
    else:
        configured = True
        provider_name = "Yahoo Finance"
        note = "Public Yahoo Finance chart data is selected; availability is checked when quotes are requested."
    return {
        "provider_setting": setting,
        "provider": provider_name,
        "configured": configured,
        "stream_configured": (
            bool(upstox_service._market_feed_token()) if provider == "upstox" else False
        ),
        "connection_state": "disconnected",
        "last_authorized_at": None,
        "last_connected_at": None,
        "last_message_received_at": None,
        "last_tick_received_at": None,
        "last_source_timestamp": None,
        "upstream_message_count": 0,
        "subscribed_instrument_count": 0,
        "reconnect_attempts": 0,
        "stream_error_category": None,
        "stream_failure_reason": None,
        "note": note,
        "cache_seconds": _cache_seconds(),
        "auto_refresh_seconds": 60,
    }


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _timestamp(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        candidate = value.strip()
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            return None
    return None


def _freshness(source_timestamp: str | None, provider: str) -> str:
    if source_timestamp is None:
        return "unknown"
    try:
        observed = datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    except (ValueError, TypeError):
        return "unknown"
    if age < -FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
        return "unknown"
    age = max(0.0, age)
    if age > STALE_AFTER_SECONDS:
        return "stale"
    return "delayed" if provider == "Yahoo Finance" else "fresh"


def _empty_quote(
    instrument: dict[str, str], provider: str, fetched_at: str
) -> dict[str, object]:
    return {
        "key": instrument["key"],
        "symbol": instrument["symbol"],
        "instrument_id": instrument["instrument_id"],
        "provider_symbol": instrument.get("yahoo_symbol"),
        "last_price": None,
        "change": None,
        "change_percent": None,
        "currency": None,
        "source": provider,
        "source_timestamp": None,
        "fetched_at": fetched_at,
        "freshness": "unknown",
        "status": "unavailable",
    }


class UpstoxProvider:
    name = "Upstox"

    def fetch(self, instruments: list[dict[str, str]]) -> list[dict[str, object]]:
        try:
            snapshot = upstox_service.get_market_quotes()
        except upstox_service.UpstoxServiceError as exc:
            raise MarketDataError(str(exc), exc.status_code) from exc
        raw_quotes = snapshot.get("quotes")
        if not isinstance(raw_quotes, list):
            raise MarketDataError("Upstox returned an unexpected quote format.")
        quote_by_key = {
            item.get("key"): item for item in raw_quotes if isinstance(item, dict)
        }
        fetched_at = _timestamp(snapshot.get("generated_at")) or datetime.now(timezone.utc).isoformat()
        normalized: list[dict[str, object]] = []
        for instrument in instruments:
            quote_row = quote_by_key.get(instrument["key"])
            if not isinstance(quote_row, dict):
                normalized.append(_empty_quote(instrument, self.name, fetched_at))
                continue
            source_timestamp = _timestamp(quote_row.get("timestamp"))
            last_price = _finite_number(quote_row.get("last_price"))
            normalized.append({
                "key": instrument["key"],
                "symbol": instrument["symbol"],
                "instrument_id": instrument["instrument_id"],
                "provider_symbol": instrument["instrument_id"],
                "last_price": last_price,
                "change": _finite_number(quote_row.get("change")),
                "change_percent": _finite_number(quote_row.get("change_percent")),
                "currency": quote_row.get("currency") if isinstance(quote_row.get("currency"), str) else None,
                "source": self.name,
                "source_timestamp": source_timestamp,
                "fetched_at": fetched_at,
                "freshness": _freshness(source_timestamp, self.name),
                "status": "available" if last_price is not None else "unavailable",
            })
        return normalized


def _yahoo_chart_payload(instrument: dict[str, str]) -> dict[str, Any]:
    yahoo_symbol = instrument["yahoo_symbol"]
    query = urlencode({"range": "1d", "interval": "1m", "includePrePost": "false"})
    request = Request(
        f"{YAHOO_CHART_URL}{quote(yahoo_symbol, safe='')}?{query}",
        headers={"Accept": "application/json", "User-Agent": "Arthvest/0.3 market dashboard"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 429:
            raise MarketDataError("Yahoo Finance rate limit reached; retry later.", 503) from exc
        if exc.code >= 500:
            raise MarketDataError("Yahoo Finance is temporarily unavailable.", 503) from exc
        raise MarketDataError("Yahoo Finance rejected the quote request.", 502) from exc
    except (TimeoutError, OSError, URLError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(reason, (TimeoutError,)):
            raise MarketDataError("Yahoo Finance quote request timed out.", 504) from exc
        raise MarketDataError("Could not reach Yahoo Finance.", 503) from exc
    except UnicodeDecodeError as exc:
        raise MarketDataError("Yahoo Finance returned a response that was not valid UTF-8.", 502) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MarketDataError("Yahoo Finance returned malformed JSON.", 502) from exc
    if not isinstance(payload, dict):
        raise MarketDataError("Yahoo Finance returned an unexpected response format.", 502)
    return payload


class YahooFinanceProvider:
    name = "Yahoo Finance"

    def fetch(self, instruments: list[dict[str, str]]) -> list[dict[str, object]]:
        fetched_at = datetime.now(timezone.utc).isoformat()
        normalized: list[dict[str, object]] = []
        errors: list[MarketDataError] = []
        for instrument in instruments:
            try:
                payload = _yahoo_chart_payload(instrument)
                normalized.append(
                    self._normalize(
                        instrument,
                        payload,
                        datetime.now(timezone.utc).isoformat(),
                    )
                )
            except MarketDataError as exc:
                logger.warning("Yahoo quote unavailable for %s (%s)", instrument["key"], exc.status_code)
                errors.append(exc)
                normalized.append(_empty_quote(instrument, self.name, fetched_at))
        if normalized and all(item["status"] == "unavailable" for item in normalized):
            raise errors[0] if errors else MarketDataError("Yahoo Finance returned no usable quotes.")
        return normalized

    @staticmethod
    def _normalize(
        instrument: dict[str, str], payload: dict[str, Any], fetched_at: str
    ) -> dict[str, object]:
        chart = payload.get("chart")
        if not isinstance(chart, dict) or chart.get("error") is not None:
            raise MarketDataError("Yahoo Finance returned no chart data for a configured symbol.")
        results = chart.get("result")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise MarketDataError("Yahoo Finance returned a malformed chart response.")
        result = results[0]
        meta = result.get("meta")
        if not isinstance(meta, dict):
            raise MarketDataError("Yahoo Finance omitted quote metadata.")
        quote_groups = result.get("indicators", {}).get("quote") if isinstance(result.get("indicators"), dict) else None
        quote_group = quote_groups[0] if isinstance(quote_groups, list) and quote_groups and isinstance(quote_groups[0], dict) else {}
        closes = quote_group.get("close") if isinstance(quote_group, dict) else None
        close_values = closes if isinstance(closes, list) else []
        last_close = next((_finite_number(value) for value in reversed(close_values) if _finite_number(value) is not None), None)
        last_price = _finite_number(meta.get("regularMarketPrice"))
        if last_price is None:
            last_price = last_close
        previous_close = _finite_number(meta.get("chartPreviousClose"))
        if previous_close is None:
            previous_close = _finite_number(meta.get("previousClose"))
        change = last_price - previous_close if last_price is not None and previous_close is not None else None
        change_percent = (change / previous_close * 100) if change is not None and previous_close not in (None, 0) else None
        times = result.get("timestamp")
        latest_time = next((value for value in reversed(times) if isinstance(value, (int, float))), None) if isinstance(times, list) else None
        source_timestamp = _timestamp(meta.get("regularMarketTime")) or _timestamp(latest_time)
        symbol = meta.get("symbol") if isinstance(meta.get("symbol"), str) else instrument["yahoo_symbol"]
        currency = meta.get("currency") if isinstance(meta.get("currency"), str) else None
        if last_price is None:
            raise MarketDataError("Yahoo Finance did not provide a valid market price.")
        return {
            "key": instrument["key"],
            "symbol": instrument["symbol"],
            "instrument_id": instrument["instrument_id"],
            "provider_symbol": symbol,
            "last_price": last_price,
            "change": change,
            "change_percent": change_percent,
            "currency": currency,
            "source": YahooFinanceProvider.name,
            "source_timestamp": source_timestamp,
            "fetched_at": fetched_at,
            "freshness": _freshness(source_timestamp, YahooFinanceProvider.name),
            "status": "available",
        }


_PROVIDERS: dict[str, MarketProvider] = {
    "upstox": UpstoxProvider(),
    "yahoo": YahooFinanceProvider(),
}
_CACHE: dict[tuple[str, tuple[str, ...]], tuple[float, dict[str, object]]] = {}
_CACHE_LOCK = threading.Lock()
_IN_FLIGHT: dict[tuple[str, tuple[str, ...]], Future[dict[str, object]]] = {}
_HISTORY_LOCK = threading.Lock()
_HISTORY_IN_FLIGHT: dict[tuple[str, str, int, date, date], Future[dict[str, object]]] = {}


def _requested_instruments(symbols: list[str] | None) -> list[dict[str, str]]:
    if symbols is None:
        return list(INSTRUMENTS)
    if not symbols:
        raise MarketDataError("Select one or more unique supported market symbols.", 422)
    requested: list[dict[str, str]] = []
    for value in symbols:
        normalized = value.strip().casefold()
        instrument = (
            INSTRUMENT_BY_KEY.get(normalized)
            or INSTRUMENT_BY_ID.get(normalized)
            or INSTRUMENT_BY_SYMBOL.get(normalized)
        )
        if instrument is None:
            raise MarketDataError("Unsupported market symbol or instrument identifier.", 422)
        requested.append(instrument)
    keys = [instrument["key"] for instrument in requested]
    if len(set(keys)) != len(keys):
        raise MarketDataError("Select each market symbol only once.", 422)
    return requested


def _refresh_cached_freshness(response: dict[str, object]) -> None:
    quotes = response.get("quotes")
    if not isinstance(quotes, list):
        return
    for quote_row in quotes:
        if isinstance(quote_row, dict) and quote_row.get("status") == "available":
            source = quote_row.get("source")
            quote_row["freshness"] = _freshness(
                quote_row.get("source_timestamp") if isinstance(quote_row.get("source_timestamp"), str) else None,
                source if isinstance(source, str) else "",
            )


def get_market_quotes(symbols: list[str] | None = None) -> dict[str, object]:
    """Get normalized quotes from the configured provider and short-lived cache."""
    instruments = _requested_instruments(symbols)
    provider_key = _selected_provider_name()
    provider = _PROVIDERS[provider_key]
    key = (provider_key, tuple(item["key"] for item in instruments))
    now = time.monotonic()
    ttl = _cache_seconds()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] > now:
            result = copy.deepcopy(cached[1])
            result["cached"] = True
            _refresh_cached_freshness(result)
            return result

    if provider_key == "upstox" and not upstox_service._analytics_token():
        raise MarketDataError("Upstox is selected but UPSTOX_ANALYTICS_TOKEN is not configured.", 503)

    quotes = provider.fetch(instruments)
    fetched_at = datetime.now(timezone.utc).isoformat()
    available_count = sum(item.get("status") == "available" for item in quotes)
    result: dict[str, object] = {
        "provider_setting": _provider_setting(),
        "provider": provider.name,
        "source_url": upstox_service.SOURCE_URL if provider_key == "upstox" else YAHOO_SOURCE_URL,
        "status": "available" if available_count == len(quotes) else "partial",
        "fetched_at": fetched_at,
        "available_count": available_count,
        "total_count": len(quotes),
        "cache_seconds": ttl,
        "cached": False,
        "quotes": quotes,
    }
    if ttl > 0:
        with _CACHE_LOCK:
            _CACHE[key] = (time.monotonic() + ttl, copy.deepcopy(result))
    return result


def get_instrument_quote(instrument_key: str) -> dict[str, object]:
    """Fetch/cache a quote for a validated instrument from Upstox."""
    from app.services import instrument_catalog

    instrument = instrument_catalog.get_instrument(instrument_key)
    if _selected_provider_name() != "upstox":
        raise MarketDataError("Individual NSE/BSE stock quotes require Upstox to be the selected provider.", 503)
    cache_key = ("upstox", (instrument_key,))
    ttl = _cache_seconds()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            result = copy.deepcopy(cached[1])
            result["cached"] = True
            quote_row = result.get("quote")
            if isinstance(quote_row, dict):
                quote_row["freshness"] = _freshness(quote_row.get("source_timestamp"), "Upstox")
            return result
        future = _IN_FLIGHT.get(cache_key)
        owner = future is None
        if owner:
            future = Future()
            _IN_FLIGHT[cache_key] = future
    assert future is not None
    if not owner:
        try:
            result = copy.deepcopy(future.result(timeout=REQUEST_TIMEOUT_SECONDS + 15))
            result["cached"] = True
            return result
        except FutureTimeout as exc:
            raise MarketDataError("A quote request for this instrument is still in progress.", 503) from exc

    try:
        provider_instrument = {
            **instrument,
            "key": instrument_key,
            "instrument_key": instrument_key,
            "name": instrument["name"],
        }
        snapshot = upstox_service.get_market_quotes([provider_instrument])
        rows = snapshot.get("quotes")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            raise MarketDataError("Upstox returned no quote for the selected instrument.", 502)
        row = rows[0]
        source_timestamp = _timestamp(row.get("timestamp"))
        fetched_at = _timestamp(snapshot.get("generated_at")) or datetime.now(timezone.utc).isoformat()
        normalized = {
            "instrument_key": instrument_key,
            "symbol": instrument["trading_symbol"],
            "name": instrument["name"],
            "exchange": instrument["exchange"],
            "segment": instrument["segment"],
            "instrument_type": instrument["instrument_type"],
            "isin": instrument["isin"],
            "last_price": _finite_number(row.get("last_price")),
            "change": _finite_number(row.get("change")),
            "change_percent": _finite_number(row.get("change_percent")),
            "previous_close": _finite_number(row.get("previous_close")),
            "open": _finite_number(row.get("open")),
            "high": _finite_number(row.get("high")),
            "low": _finite_number(row.get("low")),
            "volume": _finite_number(row.get("volume")),
            "currency": row.get("currency") if isinstance(row.get("currency"), str) else None,
            "source": "Upstox",
            "delivery": "rest",
            "source_timestamp": source_timestamp,
            "fetched_at": fetched_at,
            "freshness": _freshness(source_timestamp, "Upstox"),
            "status": "available" if _finite_number(row.get("last_price")) is not None else "unavailable",
        }
        if normalized["status"] == "unavailable":
            raise MarketDataError("Upstox did not provide a valid price for the selected instrument.", 503)
        result: dict[str, object] = {
            "provider": "Upstox",
            "source_url": upstox_service.SOURCE_URL,
            "fetched_at": fetched_at,
            "cached": False,
            "quote": normalized,
        }
        if ttl > 0:
            with _CACHE_LOCK:
                _CACHE[cache_key] = (time.monotonic() + ttl, copy.deepcopy(result))
        future.set_result(copy.deepcopy(result))
        return result
    except upstox_service.UpstoxServiceError as exc:
        error = MarketDataError(str(exc), exc.status_code)
        future.set_exception(error)
        raise error from exc
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _CACHE_LOCK:
            if _IN_FLIGHT.get(cache_key) is future:
                _IN_FLIGHT.pop(cache_key, None)


def get_instrument_history(
    instrument_key: str,
    *,
    unit: str = "days",
    interval: int = 1,
    from_date: date,
    to_date: date,
) -> dict[str, object]:
    """Return persistent provider history, synchronizing only uncovered ranges."""
    from app.services import instrument_catalog
    from app.services import market_store

    instrument = instrument_catalog.get_instrument(instrument_key)
    if unit not in {"minutes", "hours", "days", "weeks", "months"}:
        raise MarketDataError("Unsupported candle unit.", 422)
    max_interval = {"minutes": 300, "hours": 5, "days": 1, "weeks": 1, "months": 1}[unit]
    if not 1 <= interval <= max_interval:
        raise MarketDataError("Candle interval is outside the supported range.", 422)
    if from_date > to_date or to_date > date.today():
        raise MarketDataError("Candle dates must be ordered and cannot be in the future.", 422)
    max_days = 31 if unit == "minutes" and interval <= 15 else 92 if unit in {"minutes", "hours"} else 3650
    if (to_date - from_date).days > max_days:
        raise MarketDataError(f"The requested range exceeds the {max_days}-day limit for this candle unit.", 422)
    cache_key = (instrument_key, unit, interval, from_date, to_date)
    with _HISTORY_LOCK:
        future = _HISTORY_IN_FLIGHT.get(cache_key)
        owner = future is None
        if owner:
            future = Future()
            _HISTORY_IN_FLIGHT[cache_key] = future
    assert future is not None
    if not owner:
        try:
            return copy.deepcopy(future.result(timeout=40))
        except FutureTimeout as exc:
            raise MarketDataError("A history synchronization for this range is still in progress.", 503) from exc

    try:
        result = _synchronize_instrument_history(
            market_store, instrument, unit, interval, from_date, to_date
        )
        future.set_result(copy.deepcopy(result))
        return result
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _HISTORY_LOCK:
            if _HISTORY_IN_FLIGHT.get(cache_key) is future:
                _HISTORY_IN_FLIGHT.pop(cache_key, None)


def _fetch_upstox_candles(
    instrument_key: str, unit: str, interval: int, from_date: date, to_date: date
) -> tuple[list[dict[str, object]], str]:
    try:
        payload = upstox_service.get_historical_candles(
            instrument_key, unit, interval, to_date.isoformat(), from_date.isoformat()
        )
    except upstox_service.UpstoxServiceError as exc:
        raise MarketDataError(str(exc), exc.status_code) from exc
    raw = payload["data"]["candles"]
    fetched_at = datetime.now(timezone.utc).isoformat()
    candles: list[dict[str, object]] = []
    for candle in raw:
        if not isinstance(candle, list) or len(candle) < 6:
            raise MarketDataError("Upstox returned a malformed candle record.", 502)
        timestamp = _timestamp(candle[0])
        values = [_finite_number(value) for value in candle[1:6]]
        open_value, high_value, low_value, close_value, volume = values
        if timestamp is None or any(value is None for value in values):
            raise MarketDataError("Upstox returned an invalid candle value.", 502)
        if any(value <= 0 for value in values[:4]):
            raise MarketDataError("Upstox returned a non-positive equity price.", 502)
        if high_value < max(open_value, close_value, low_value) or low_value > min(open_value, close_value) or volume < 0:
            raise MarketDataError("Upstox returned inconsistent candle values.", 502)
        open_interest = _finite_number(candle[6]) if len(candle) > 6 else None
        if len(candle) > 6 and (open_interest is None or open_interest < 0):
            raise MarketDataError("Upstox returned an invalid open-interest value.", 502)
        candles.append({
            "timestamp": timestamp, "open": open_value, "high": high_value,
            "low": low_value, "close": close_value, "volume": volume,
            "open_interest": open_interest, "source": "Upstox historical",
            "fetched_at": fetched_at, "quality_status": "provider_validated",
        })
    candles.sort(key=lambda item: str(item["timestamp"]))
    return candles, fetched_at


def _missing_history_ranges(
    start: date, end: date, coverage: list[tuple[date, date]]
) -> list[tuple[date, date]]:
    from datetime import timedelta

    merged: list[list[date]] = []
    for left, right in sorted(coverage):
        if right < start or left > end:
            continue
        left, right = max(left, start), min(right, end)
        if merged and left <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    gaps: list[tuple[date, date]] = []
    cursor = start
    for left, right in merged:
        if left > cursor:
            gaps.append((cursor, left - timedelta(days=1)))
        cursor = max(cursor, right + timedelta(days=1))
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


def _synchronize_instrument_history(
    store: Any, instrument: dict[str, Any], unit: str, interval: int,
    from_date: date, to_date: date,
) -> dict[str, object]:
    key = str(instrument["instrument_key"])
    fetched_this_request: list[dict[str, object]] = []
    inserted = updated = 0
    persistence_status = "available"
    error_category: str | None = None
    try:
        stored = store.list_candles(key, unit, interval, from_date, to_date)
        gaps = _missing_history_ranges(from_date, to_date, store.successful_coverage(key, unit, interval))
    except store.MarketStorageDisabledError:
        stored = []
        gaps = [(from_date, to_date)]
        persistence_status = "configuration_missing"
        error_category = "database_configuration_missing"
    except Exception:
        stored = []
        gaps = [(from_date, to_date)]
        persistence_status = "unavailable"
        error_category = "database_read_failed"

    if len(gaps) > 8:
        raise MarketDataError("Stored history has too many uncovered segments; request smaller ranges.", 422)

    for gap_start, gap_end in gaps:
        sync_id: int | None = None
        if persistence_status == "available":
            try:
                sync_id = store.create_sync_run(
                    instrument_key=key, unit=unit, interval=interval,
                    from_date=gap_start, to_date=gap_end,
                )
            except Exception:
                persistence_status = "write_failed"
                error_category = "database_write_failed"
        try:
            candles, _fetched_at = _fetch_upstox_candles(key, unit, interval, gap_start, gap_end)
        except MarketDataError as exc:
            category = "upstream_timeout" if exc.status_code == 504 else "upstream_unavailable" if exc.status_code == 503 else "upstream_invalid_response"
            if sync_id is not None:
                try:
                    store.finish_sync_failure(sync_id, category)
                except Exception:
                    pass
            error_category = category
            if not stored and not fetched_this_request:
                raise
            break
        fetched_this_request.extend(candles)
        if sync_id is not None:
            try:
                counts = store.finish_sync_success(sync_id, instrument, unit, interval, candles)
                inserted += counts["inserted_count"]
                updated += counts["updated_count"]
            except Exception:
                persistence_status = "write_failed"
                error_category = "database_write_failed"
                try:
                    store.finish_sync_failure(sync_id, "database_write_failed")
                except Exception:
                    pass

    if persistence_status == "available":
        try:
            stored = store.list_candles(key, unit, interval, from_date, to_date)
            coverage = store.successful_coverage(key, unit, interval)
            gaps = _missing_history_ranges(from_date, to_date, coverage)
        except Exception:
            persistence_status = "read_failed"
            error_category = "database_read_failed"
    if persistence_status != "available":
        by_timestamp = {str(item["timestamp"]): item for item in stored}
        by_timestamp.update({str(item["timestamp"]): item for item in fetched_this_request})
        candles_for_response = sorted(by_timestamp.values(), key=lambda row: str(row["timestamp"]))
    else:
        candles_for_response = stored

    if persistence_status == "available":
        try:
            history = store.history_status(key, unit, interval)
        except Exception:
            history = {
                "last_successful_sync_at": None, "last_attempted_sync_at": None,
                "last_failure_category": "database_status_unavailable", "last_run_status": "unavailable",
            }
    else:
        history = {
            "last_successful_sync_at": None, "last_attempted_sync_at": None,
            "last_failure_category": error_category, "last_run_status": "failed",
        }
    start_stamp = candles_for_response[0]["timestamp"] if candles_for_response else None
    end_stamp = candles_for_response[-1]["timestamp"] if candles_for_response else None
    upstream_complete = bool(fetched_this_request) and error_category not in {
        "upstream_timeout", "upstream_unavailable", "upstream_invalid_response",
    }
    complete = not gaps if persistence_status == "available" else upstream_complete
    if persistence_status == "available":
        status = "synchronized" if complete else "stale" if error_category and candles_for_response else "partially_synchronized" if candles_for_response else "initial_sync_pending"
    else:
        status = "synchronization_failed"
    fetched_times = [item.get("fetched_at") for item in candles_for_response if isinstance(item.get("fetched_at"), str)]
    from app.services.technical_analysis import calculate_technical_indicators

    return {
        "instrument_key": key, "symbol": instrument["trading_symbol"],
        "exchange": instrument["exchange"], "provider": "Upstox",
        "unit": unit, "interval": interval,
        "from_date": from_date.isoformat(), "to_date": to_date.isoformat(),
        "fetched_at": max(fetched_times) if fetched_times else datetime.now(timezone.utc).isoformat(),
        "candles": candles_for_response,
        "technical_indicators": calculate_technical_indicators(candles_for_response),
        "history_source": "database" if persistence_status == "available" else "Upstox Historical API (not persisted)",
        "persistence_status": persistence_status,
        "sync_status": status,
        "coverage_complete": complete,
        "coverage_start": str(start_stamp) if start_stamp else None,
        "coverage_end": str(end_stamp) if end_stamp else None,
        "candle_count": len(candles_for_response),
        "inserted_count": inserted,
        "updated_count": updated,
        "last_successful_sync_at": history["last_successful_sync_at"],
        "last_attempted_sync_at": history["last_attempted_sync_at"],
        "last_failure_category": error_category or history["last_failure_category"],
        "last_run_status": history["last_run_status"],
    }
