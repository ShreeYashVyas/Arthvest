"""Tests for provider selection and normalized independent market-data routes."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import market_data, upstox_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_market_cache():
    market_data._CACHE.clear()
    yield
    market_data._CACHE.clear()


def _yahoo_payload(
    *,
    source_time: int | None = None,
    price: float = 123.4,
    previous_close: float = 120.0,
    currency: str | None = "INR",
) -> dict[str, object]:
    meta: dict[str, object] = {
        "symbol": "^NSEI",
        "regularMarketPrice": price,
        "chartPreviousClose": previous_close,
    }
    if source_time is not None:
        meta["regularMarketTime"] = source_time
    if currency is not None:
        meta["currency"] = currency
    return {
        "chart": {
            "result": [{
                "meta": meta,
                "timestamp": [source_time] if source_time is not None else [],
                "indicators": {"quote": [{"close": [price]}]},
            }],
            "error": None,
        }
    }


def test_auto_provider_uses_yahoo_when_upstox_token_is_absent(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "auto")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "")

    status = market_data.get_market_data_status()

    assert status["provider"] == "Yahoo Finance"
    assert status["configured"] is True
    assert status["stream_configured"] is False


def test_auto_provider_prefers_upstox_when_token_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "auto")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "private-token")
    monkeypatch.setattr(upstox_service, "_market_feed_access_token", lambda: "oauth-token")

    status = market_data.get_market_data_status()

    assert status["provider"] == "Upstox"
    assert status["configured"] is True
    assert status["stream_configured"] is True
    assert "private-token" not in json.dumps(status)


def test_explicit_yahoo_does_not_require_upstox_token(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "")

    assert market_data.get_market_data_status()["provider"] == "Yahoo Finance"
    assert market_data.get_market_data_status()["stream_configured"] is False


def test_explicit_upstox_without_token_returns_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "")

    with pytest.raises(market_data.MarketDataError) as error:
        market_data.get_market_quotes(["nifty-50"])

    assert error.value.status_code == 503
    assert "UPSTOX_ANALYTICS_TOKEN" in str(error.value)


def test_yahoo_chart_response_is_normalized_from_provider_values(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(
        market_data,
        "_yahoo_chart_payload",
        lambda _instrument: _yahoo_payload(source_time=now),
    )
    instrument = market_data.INSTRUMENT_BY_KEY["nifty-50"]

    quote = market_data.YahooFinanceProvider().fetch([instrument])[0]

    assert quote["last_price"] == 123.4
    assert quote["change"] == pytest.approx(3.4)
    assert quote["change_percent"] == pytest.approx(2.8333333)
    assert quote["currency"] == "INR"
    assert quote["provider_symbol"] == "^NSEI"
    assert quote["instrument_id"] == "NSE_INDEX|Nifty 50"
    assert quote["source"] == "Yahoo Finance"
    assert quote["freshness"] == "delayed"
    assert quote["status"] == "available"
    assert isinstance(quote["fetched_at"], str)


def test_yahoo_missing_fields_are_null_and_old_timestamp_is_stale(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    old_timestamp = int((datetime.now(timezone.utc) - timedelta(minutes=20)).timestamp())
    payload = _yahoo_payload(source_time=old_timestamp, currency=None)
    payload["chart"]["result"][0]["meta"].pop("chartPreviousClose")
    monkeypatch.setattr(market_data, "_yahoo_chart_payload", lambda _instrument: payload)

    quote = market_data.YahooFinanceProvider().fetch(
        [market_data.INSTRUMENT_BY_KEY["nifty-50"]]
    )[0]

    assert quote["status"] == "available"
    assert quote["currency"] is None
    assert quote["change"] is None
    assert quote["change_percent"] is None
    assert quote["freshness"] == "stale"


def test_yahoo_missing_source_timestamp_is_unknown(monkeypatch) -> None:
    payload = _yahoo_payload(source_time=None)
    monkeypatch.setattr(market_data, "_yahoo_chart_payload", lambda _instrument: payload)

    quote = market_data.YahooFinanceProvider().fetch(
        [market_data.INSTRUMENT_BY_KEY["nifty-50"]]
    )[0]

    assert quote["source_timestamp"] is None
    assert quote["freshness"] == "unknown"


def test_freshness_classifies_normal_timestamp_as_fresh() -> None:
    observed = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert market_data._freshness(observed.isoformat(), "Upstox") == "fresh"


def test_freshness_allows_small_future_clock_skew() -> None:
    observed = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert market_data._freshness(observed.isoformat(), "Upstox") == "fresh"


def test_freshness_rejects_significantly_future_timestamp() -> None:
    observed = datetime.now(timezone.utc) + timedelta(seconds=10)
    assert market_data._freshness(observed.isoformat(), "Upstox") == "unknown"


def test_freshness_marks_old_timestamp_stale() -> None:
    observed = datetime.now(timezone.utc) - timedelta(seconds=market_data.STALE_AFTER_SECONDS + 1)
    assert market_data._freshness(observed.isoformat(), "Upstox") == "stale"


def test_freshness_marks_missing_timestamp_unknown() -> None:
    assert market_data._freshness(None, "Upstox") == "unknown"


def test_upstox_quote_preserves_source_and_fetch_timestamps(monkeypatch) -> None:
    source_timestamp = "2026-10-29T10:00:00+05:30"
    fetched_timestamp = "2026-10-29T04:30:01+00:00"
    monkeypatch.setattr(
        upstox_service,
        "get_market_quotes",
        lambda: {
            "generated_at": fetched_timestamp,
            "quotes": [{
                "key": "nifty-50",
                "timestamp": source_timestamp,
                "last_price": 23000.0,
                "change": 10.0,
                "change_percent": 0.1,
                "currency": "INR",
            }],
        },
    )

    quote = market_data.UpstoxProvider().fetch(
        [market_data.INSTRUMENT_BY_KEY["nifty-50"]]
    )[0]

    assert quote["source_timestamp"] == "2026-10-29T04:30:00+00:00"
    assert quote["fetched_at"] == "2026-10-29T04:30:01+00:00"


@pytest.mark.parametrize(
    "symbols",
    [["not-an-index"], ["nifty-50", "nifty-50"], ["NSE_EQ|FAKE"]],
)
def test_invalid_or_duplicate_symbols_are_rejected(symbols) -> None:
    with pytest.raises(market_data.MarketDataError) as error:
        market_data.get_market_quotes(symbols)
    assert error.value.status_code == 422


def test_yahoo_wrapped_timeout_is_gateway_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        market_data,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError(TimeoutError("timeout"))),
    )
    with pytest.raises(market_data.MarketDataError) as error:
        market_data._yahoo_chart_payload(market_data.INSTRUMENT_BY_KEY["nifty-50"])
    assert error.value.status_code == 504


def test_yahoo_upstream_rate_limit_is_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        market_data,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTTPError("https://query1.finance.yahoo.com/", 429, "rate limited", None, None)
        ),
    )
    with pytest.raises(market_data.MarketDataError) as error:
        market_data._yahoo_chart_payload(market_data.INSTRUMENT_BY_KEY["nifty-50"])
    assert error.value.status_code == 503
    assert "query1.finance.yahoo.com" not in str(error.value)


def test_market_quotes_api_returns_provider_independent_normalized_shape(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(
        market_data,
        "_yahoo_chart_payload",
        lambda _instrument: _yahoo_payload(source_time=now),
    )

    response = client.get("/api/market/quotes?symbols=NSE_INDEX%7CNifty%2050")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "Yahoo Finance"
    quote = payload["quotes"][0]
    assert quote["instrument_id"] == "NSE_INDEX|Nifty 50"
    assert quote["last_price"] == 123.4
    assert quote["currency"] == "INR"
    assert quote["source"] == "Yahoo Finance"
    assert quote["source_timestamp"] is not None


def test_upstox_auth_failure_does_not_fall_back_to_yahoo(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "auto")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "invalid-token")

    def rejected():
        raise upstox_service.UpstoxServiceError("Upstox rejected the configured token.", 502)

    monkeypatch.setattr(upstox_service, "get_market_quotes", rejected)
    monkeypatch.setattr(
        market_data._PROVIDERS["yahoo"],
        "fetch",
        lambda _instruments: pytest.fail("auto mode must not hide Upstox authentication failures"),
    )

    response = client.get("/api/market/quotes?symbols=nifty-50")

    assert response.status_code == 502
    assert response.json()["detail"] == "Upstox rejected the configured token."


def test_upstox_wrapped_timeout_returns_504(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "configured-token")
    monkeypatch.setattr(
        upstox_service,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError(TimeoutError("timeout"))),
    )

    response = client.get("/api/market/quotes?symbols=nifty-50")

    assert response.status_code == 504
    assert "timeout" not in response.json()["detail"].lower()


def test_markets_page_has_no_numeric_quote_fixtures() -> None:
    page = Path(__file__).parents[2] / "frontend" / "src" / "app" / "markets" / "page.tsx"
    source = page.read_text(encoding="utf-8")

    assert "emptyQuotes" not in source
    assert re.search(r"(?:last_price|change|change_percent|volume)\s*:\s*-?\d", source) is None
    assert "fetchMarketQuotes" in source
    assert "No historical chart is available" in source
