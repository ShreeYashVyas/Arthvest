"""Read-only market quote integration using the Upstox Analytics Token."""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

UPSTOX_QUOTES_URL = "https://api.upstox.com/v2/market-quote/quotes"
REQUEST_TIMEOUT_SECONDS = 10
SOURCE_URL = "https://upstox.com/developer/api-documentation/get-full-market-quote/"
HISTORY_URL = "https://api.upstox.com/v3/historical-candle/"
MARKET_FEED_AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"

INSTRUMENTS: tuple[dict[str, str], ...] = (
    {
        "key": "nifty-50",
        "name": "NIFTY 50",
        "instrument_key": "NSE_INDEX|Nifty 50",
    },
    {
        "key": "nifty-bank",
        "name": "NIFTY BANK",
        "instrument_key": "NSE_INDEX|Nifty Bank",
    },
    {
        "key": "india-vix",
        "name": "INDIA VIX",
        "instrument_key": "NSE_INDEX|India VIX",
    },
)


class UpstoxServiceError(RuntimeError):
    """A safe-to-display provider error with an HTTP status for the API layer."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _analytics_token() -> str:
    """Read the server-side token; never return it in API payloads or logs."""
    return os.getenv("UPSTOX_ANALYTICS_TOKEN", "").strip()


def _market_feed_access_token() -> str:
    """Read the OAuth access token required by Upstox's Market Data Feed V3."""
    return os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()


def get_upstox_status() -> dict[str, object]:
    """Report configuration readiness without disclosing any credential."""
    configured = bool(_analytics_token())
    return {
        "provider": "Upstox",
        "configured": configured,
        "stream_configured": bool(_market_feed_access_token()),
        "auth_mode": "Analytics Token (read-only)" if configured else None,
        "note": (
            "An Analytics Token is configured. Market quotes are fetched from Upstox on request."
            if configured
            else (
                "Set UPSTOX_ANALYTICS_TOKEN in backend/.env and start the backend with "
                "--env-file .env to enable market quotes."
            )
        ),
    }


def _request_quotes_payload(
    token: str, instrument_keys: list[str] | None = None
) -> dict[str, object]:
    """Request one or more resolved Upstox instruments with a bounded timeout."""
    keys = instrument_keys or [item["instrument_key"] for item in INSTRUMENTS]
    query = urlencode({"instrument_key": ",".join(keys)})
    request = Request(
        UPSTOX_QUOTES_URL + "?" + query,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
            "User-Agent": "Arthvest/0.2 (read-only market intelligence)",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise UpstoxServiceError(
                "Upstox rejected the configured token. Confirm the Analytics Token is active and copied in full.",
                502,
            ) from exc
        if exc.code == 429:
            raise UpstoxServiceError(
                "Upstox rate limit reached. Wait briefly before refreshing market data.",
                503,
            ) from exc
        if exc.code >= 500:
            raise UpstoxServiceError(
                "Upstox market-data service is temporarily unavailable.",
                503,
            ) from exc
        raise UpstoxServiceError(
            "Upstox rejected the market-data request. Check the token and API configuration.",
            502,
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Upstox quote request failed: %s", type(exc).__name__)
        reason = exc.reason if isinstance(exc, URLError) else exc
        status_code = 504 if isinstance(reason, TimeoutError) else 503
        raise UpstoxServiceError(
            "Upstox quote request timed out."
            if status_code == 504
            else "Could not reach Upstox. Check your internet connection and try again.",
            status_code,
        ) from exc
    except UnicodeDecodeError as exc:
        raise UpstoxServiceError("Upstox returned an unreadable market-data response.", 502) from exc

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise UpstoxServiceError("Upstox returned invalid JSON for market quotes.", 502) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("status") != "success"
        or not isinstance(payload.get("data"), dict)
    ):
        raise UpstoxServiceError("Upstox returned an unexpected market-quote response.", 502)
    return payload


def _normalise_instrument_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip().replace(":", "|").casefold()


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _quote_timestamp(quote: dict[str, object]) -> str | None:
    """Normalize the quote timestamp where the provider supplies one."""
    value = quote.get("timestamp")
    if isinstance(value, str) and value.strip():
        return value
    trade_time = quote.get("last_trade_time")
    if isinstance(trade_time, (str, int, float)) and not isinstance(trade_time, bool):
        try:
            milliseconds = int(trade_time)
            return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            return None
    return None


def _normalise_quote(
    instrument: dict[str, str],
    quote: dict[str, object] | None,
) -> dict[str, object]:
    if quote is None:
        return {
            **instrument,
            "status": "unavailable",
            "currency": None,
            "last_price": None,
            "previous_close": None,
            "change": None,
            "change_percent": None,
            "open": None,
            "high": None,
            "low": None,
            "volume": None,
            "timestamp": None,
        }

    ohlc = quote.get("ohlc")
    ohlc_data = ohlc if isinstance(ohlc, dict) else {}
    last_price = _finite_number(quote.get("last_price"))
    previous_close = _finite_number(ohlc_data.get("close"))
    change = _finite_number(quote.get("net_change"))
    if change is None and last_price is not None and previous_close is not None:
        change = last_price - previous_close
    change_percent = (
        round((change / previous_close) * 100, 4)
        if change is not None and previous_close is not None and previous_close > 0
        else None
    )

    return {
        **instrument,
        "status": "available" if last_price is not None else "unavailable",
        "currency": quote.get("currency") if isinstance(quote.get("currency"), str) else None,
        "last_price": last_price,
        "previous_close": previous_close,
        "change": change,
        "change_percent": change_percent,
        "open": _finite_number(ohlc_data.get("open")),
        "high": _finite_number(ohlc_data.get("high")),
        "low": _finite_number(ohlc_data.get("low")),
        "volume": _finite_number(quote.get("volume")),
        "timestamp": _quote_timestamp(quote),
    }


def get_market_quotes(
    instruments: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return normalized, source-attributed quotes for configured/resolved instruments."""
    token = _analytics_token()
    if not token:
        raise UpstoxServiceError(
            "Upstox is not configured. Add UPSTOX_ANALYTICS_TOKEN to backend/.env and restart the backend with --env-file .env.",
            503,
        )

    selected = (
        list(INSTRUMENTS)
        if instruments is None
        else [
            {**item, "key": item.get("key", item.get("instrument_key", ""))}
            for item in instruments
        ]
    )
    keys = [item.get("instrument_key") for item in selected]
    if not selected or not all(isinstance(key, str) and key for key in keys):
        raise UpstoxServiceError("At least one valid Upstox instrument key is required.", 422)

    payload = (
        _request_quotes_payload(token)
        if instruments is None
        else _request_quotes_payload(token, [str(key) for key in keys])
    )
    raw_data = payload["data"]
    assert isinstance(raw_data, dict)

    indexed_data: dict[str, dict[str, object]] = {}
    for response_key, raw_quote in raw_data.items():
        if not isinstance(raw_quote, dict):
            continue
        instrument_token = raw_quote.get("instrument_token")
        normalised_key = _normalise_instrument_key(instrument_token)
        if normalised_key is None:
            normalised_key = _normalise_instrument_key(response_key)
        if normalised_key is not None:
            indexed_data[normalised_key] = raw_quote

    quotes: list[dict[str, object]] = []
    for instrument in selected:
        key = _normalise_instrument_key(instrument["instrument_key"])
        quotes.append(_normalise_quote(instrument, indexed_data.get(key or "")))

    available_count = sum(item["status"] == "available" for item in quotes)
    if not indexed_data:
        raise UpstoxServiceError("Upstox returned no quotes for the requested instruments.", 502)

    timestamps = [
        item["timestamp"]
        for item in quotes
        if isinstance(item.get("timestamp"), str)
    ]
    return {
        "provider": "Upstox",
        "source_url": SOURCE_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_as_of": max(timestamps) if timestamps else None,
        "available_count": available_count,
        "total_count": len(quotes),
        "quotes": quotes,
        "read_only": True,
        "limitations": [
            "Quotes are a snapshot returned by Upstox at request time; they are not a continuous WebSocket feed.",
            "An unavailable or closed-market quote is shown as unavailable rather than filled with fabricated data.",
            "This endpoint does not place orders or read account holdings.",
        ],
    }


def get_historical_candles(
    instrument_key: str,
    unit: str,
    interval: int,
    to_date: str,
    from_date: str,
) -> dict[str, object]:
    """Fetch real historical OHLCV candles for one provider-resolved instrument."""
    token = _analytics_token()
    if not token:
        raise UpstoxServiceError("Upstox is not configured for historical market data.", 503)
    path = "/".join((quote(instrument_key, safe=""), unit, str(interval), to_date, from_date))
    request = Request(
        HISTORY_URL + path,
        headers={"Accept": "application/json", "Authorization": "Bearer " + token, "User-Agent": "Arthvest/0.3"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise UpstoxServiceError("Upstox rejected the configured credential for historical data.", 502) from exc
        if exc.code == 429:
            raise UpstoxServiceError("Upstox historical-data rate limit reached; retry later.", 503) from exc
        if exc.code >= 500:
            raise UpstoxServiceError("Upstox historical data is temporarily unavailable.", 503) from exc
        raise UpstoxServiceError("Upstox rejected the historical-data request.", 502) from exc
    except (TimeoutError, URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        status = 504 if isinstance(reason, TimeoutError) else 503
        raise UpstoxServiceError("Upstox historical-data request timed out." if status == 504 else "Could not reach Upstox historical data.", status) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpstoxServiceError("Upstox returned malformed historical data.", 502) from exc
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), dict) or not isinstance(payload["data"].get("candles"), list):
        raise UpstoxServiceError("Upstox returned an unexpected historical-data response.", 502)
    return payload


def get_market_feed_authorized_url() -> str:
    """Fetch the one-time authorized V3 websocket URL without logging or returning it to clients."""
    token = _market_feed_access_token()
    if not token:
        raise UpstoxServiceError("Live streaming requires an UPSTOX_ACCESS_TOKEN OAuth access token; the Analytics Token is not authorized for the V3 feed.", 503)
    request = Request(
        MARKET_FEED_AUTHORIZE_URL,
        headers={"Accept": "application/json", "Authorization": "Bearer " + token},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise UpstoxServiceError("Upstox rejected the configured credential for live market data.", 502) from exc
        if exc.code == 429:
            raise UpstoxServiceError("Upstox live-feed authorization rate limit reached.", 503) from exc
        raise UpstoxServiceError("Upstox could not authorize a live market-data connection.", 503) from exc
    except (TimeoutError, URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        status = 504 if isinstance(reason, TimeoutError) else 503
        raise UpstoxServiceError("Upstox live-feed authorization timed out." if status == 504 else "Could not reach Upstox live-feed authorization.", status) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpstoxServiceError("Upstox returned malformed live-feed authorization data.", 502) from exc
    try:
        uri = payload["data"]["authorized_redirect_uri"]
    except (KeyError, TypeError) as exc:
        raise UpstoxServiceError("Upstox omitted the authorized live-feed URL.", 502) from exc
    if payload.get("status") != "success" or not isinstance(uri, str) or not uri.startswith("wss://"):
        raise UpstoxServiceError("Upstox returned an invalid authorized live-feed URL.", 502)
    return uri
