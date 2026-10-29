"""Tests for real-provider instrument discovery, stock quotes, history, and feed decoding."""

import asyncio
import json
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import market_data_feed_pb2
from app.services import instrument_catalog, market_data, market_stream, upstox_service
from app.api.routes import market as market_routes
from app.services.market_feed_manager import UpstoxMarketFeedManager

client = TestClient(app)
REAL_INSTRUMENT = {
    "name": "RELIANCE INDUSTRIES LTD",
    "segment": "NSE_EQ",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
    "short_name": "Reliance Industries",
    "tick_size": 0.05,
    "lot_size": 1,
    "instrument_type": "EQ",
}


@pytest.fixture(autouse=True)
def clear_market_caches():
    instrument_catalog._SEARCH_CACHE.clear()
    instrument_catalog._INSTRUMENTS_BY_KEY.clear()
    instrument_catalog._SEARCH_API_BLOCKED = False
    instrument_catalog._MASTER_CACHE = None
    market_data._CACHE.clear()
    market_data._IN_FLIGHT.clear()
    yield
    instrument_catalog._SEARCH_CACHE.clear()
    instrument_catalog._INSTRUMENTS_BY_KEY.clear()
    instrument_catalog._SEARCH_API_BLOCKED = False
    instrument_catalog._MASTER_CACHE = None
    market_data._CACHE.clear()
    market_data._IN_FLIGHT.clear()


def test_search_normalizes_real_provider_instruments_and_filters_exchange(monkeypatch):
    monkeypatch.setattr(instrument_catalog, "_analytics_token", lambda: "private")
    observed = {}

    def search(url, *, token=""):
        observed["url"] = url
        observed["token"] = token
        return 200, {
            "status": "success",
            "data": [REAL_INSTRUMENT, {**REAL_INSTRUMENT, "exchange": "BSE", "segment": "BSE_EQ", "instrument_key": "BSE_EQ|INE002A01018", "instrument_type": "A"}],
            "meta_data": {"page": {"page_number": 1, "total_pages": 3, "records": 20, "total_records": 48}},
        }

    monkeypatch.setattr(instrument_catalog, "_fetch_json", search)
    result = instrument_catalog.search_instruments("Reliance", "NSE", 1, 20)

    assert result["source"] == "Upstox instrument search"
    assert [item["instrument_key"] for item in result["instruments"]] == ["NSE_EQ|INE002A01018"]
    assert result["instruments"][0]["isin"] == "INE002A01018"
    assert result["page"]["total_pages"] == 3
    assert "segments=EQ" in observed["url"]
    assert observed["token"] == "private"


def test_search_returns_bse_listing_as_a_distinct_instrument(monkeypatch):
    monkeypatch.setattr(instrument_catalog, "_analytics_token", lambda: "private")
    monkeypatch.setattr(instrument_catalog, "_fetch_json", lambda *_args, **_kwargs: (200, {
        "status": "success", "data": [{**REAL_INSTRUMENT, "exchange": "BSE", "segment": "BSE_EQ", "instrument_key": "BSE_EQ|INE002A01018", "instrument_type": "A"}],
        "meta_data": {"page": {"page_number": 1, "total_pages": 1, "records": 20, "total_records": 1}},
    }))
    result = instrument_catalog.search_instruments("INE002A01018", "BSE")
    assert result["instruments"][0]["exchange"] == "BSE"
    assert result["instruments"][0]["instrument_key"] == "BSE_EQ|INE002A01018"


@pytest.mark.parametrize("query", ["Reliance Industries", "Reliance", "RELIANCE", "INE002A01018"])
def test_official_master_search_matches_name_symbol_and_isin_without_duplicate_rows(monkeypatch, query):
    bse_listing = {
        **REAL_INSTRUMENT,
        "name": "RELIANCE INDUSTRIES LTD.",
        "exchange": "BSE",
        "segment": "BSE_EQ",
        "instrument_key": "BSE_EQ|INE002A01018",
        "instrument_type": "A",
    }
    nse_listing = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument master", "2026-10-29T10:00:00+00:00")
    duplicate_nse_listing = {**nse_listing}
    normalized_bse = instrument_catalog._normalize_instrument(bse_listing, "Upstox instrument master", "2026-10-29T10:00:00+00:00")
    monkeypatch.setattr(instrument_catalog, "_fetch_master", lambda: (
        "2026-10-29T10:00:00+00:00", [nse_listing, duplicate_nse_listing, normalized_bse]
    ))

    result = instrument_catalog._master_search(query, "ALL", 1, 20)

    assert {item["instrument_key"] for item in result["instruments"]} == {
        "NSE_EQ|INE002A01018", "BSE_EQ|INE002A01018"
    }
    assert len(result["instruments"]) == 2


def test_search_falls_back_to_official_master_without_sample_records(monkeypatch):
    monkeypatch.setattr(instrument_catalog, "_analytics_token", lambda: "private")
    monkeypatch.setattr(instrument_catalog, "_fetch_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(market_data.MarketDataError("Upstream unavailable", 503)))
    updated = "2026-10-29T10:00:00+00:00"
    monkeypatch.setattr(instrument_catalog, "_fetch_master", lambda: (updated, [instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument master", updated)]))
    result = instrument_catalog.search_instruments("RELIANCE")
    assert result["source"] == "Upstox instrument master"
    assert result["catalogue_updated_at"] == updated
    assert result["instruments"][0]["instrument_key"] == REAL_INSTRUMENT["instrument_key"]


def test_concurrent_cold_catalogue_searches_share_one_master_download(monkeypatch):
    payload = gzip.compress(json.dumps([REAL_INSTRUMENT]).encode("utf-8"))
    calls = {"count": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return payload

    def download(*_args, **_kwargs):
        calls["count"] += 1
        time.sleep(0.05)
        return Response()

    monkeypatch.setattr(instrument_catalog, "urlopen", download)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: instrument_catalog._fetch_master(), range(5)))

    assert calls["count"] == 1
    assert all(result[0] == results[0][0] for result in results)
    assert all(result[1][0]["instrument_key"] == REAL_INSTRUMENT["instrument_key"] for result in results)


@pytest.mark.parametrize("query", ["", " " * 2, "x" * 51, "!!!"])
def test_search_rejects_invalid_query(query):
    with pytest.raises(market_data.MarketDataError) as error:
        instrument_catalog.search_instruments(query)
    assert error.value.status_code == 422


def test_search_rejects_pages_above_provider_record_limit():
    with pytest.raises(market_data.MarketDataError) as error:
        instrument_catalog.search_instruments("TCS", records=31)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "record",
    [
        {**REAL_INSTRUMENT, "instrument_type": "N0"},
        {**REAL_INSTRUMENT, "segment": "BSE_EQ", "exchange": "BSE", "instrument_type": "F", "instrument_key": "BSE_EQ|INF204K01V53"},
    ],
)
def test_catalogue_excludes_debt_and_fund_instruments(record):
    assert instrument_catalog._normalize_instrument(record, "test source", None) is None


def test_search_route_uses_provider_results(monkeypatch):
    monkeypatch.setattr(instrument_catalog, "search_instruments", lambda query, exchange, page, records: {
        "query": query, "exchange": exchange, "page": {}, "source": "Upstox instrument search",
        "catalogue_updated_at": None, "instruments": [instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument search", None)],
    })
    response = client.get("/api/market/instruments/search?q=Reliance&exchange=NSE&page=1&records=20")
    assert response.status_code == 200
    assert response.json()["instruments"][0]["instrument_key"] == REAL_INSTRUMENT["instrument_key"]


def test_resolved_quote_normalizes_actual_provider_fields(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "auto")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "private")
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument search", None)
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(upstox_service, "get_market_quotes", lambda _items: {
        "generated_at": "2026-10-29T10:00:01+00:00",
        "quotes": [{"key": REAL_INSTRUMENT["instrument_key"], "instrument_key": REAL_INSTRUMENT["instrument_key"], "last_price": 1500.0, "previous_close": 1490.0, "change": 10.0, "change_percent": 0.6711, "open": 1495.0, "high": 1505.0, "low": 1490.0, "volume": 1200, "currency": "INR", "timestamp": "2026-10-29T10:00:00+00:00"}],
    })
    result = market_data.get_instrument_quote(REAL_INSTRUMENT["instrument_key"])
    quote_data = result["quote"]
    assert quote_data["last_price"] == 1500.0
    assert quote_data["change"] == 10.0
    assert quote_data["previous_close"] == 1490.0
    assert quote_data["delivery"] == "rest"
    assert quote_data["source_timestamp"] == "2026-10-29T10:00:00+00:00"
    assert quote_data["fetched_at"] == "2026-10-29T10:00:01+00:00"


def test_resolved_quote_endpoint_rejects_invalid_instrument_key():
    response = client.get("/api/market/instruments/NOT_A_VALID_KEY/quote")
    assert response.status_code == 422


def test_concurrent_resolved_quote_requests_share_one_upstream_call(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "auto")
    monkeypatch.setenv("MARKET_DATA_CACHE_SECONDS", "0")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "private")
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument search", None)
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    count = {"value": 0}

    def fetch(_items):
        count["value"] += 1
        time.sleep(0.05)
        return {"generated_at": "2026-10-29T10:00:01+00:00", "quotes": [{
            "key": REAL_INSTRUMENT["instrument_key"], "last_price": 1500.0,
            "timestamp": "2026-10-29T10:00:00+00:00", "change": 1.0,
        }]}

    monkeypatch.setattr(upstox_service, "get_market_quotes", fetch)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: market_data.get_instrument_quote(REAL_INSTRUMENT["instrument_key"]), range(5)))
    assert count["value"] == 1
    assert all(result["quote"]["last_price"] == 1500.0 for result in results)


def test_history_normalizes_and_orders_provider_candles(monkeypatch):
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "Upstox instrument search", None)
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(upstox_service, "get_historical_candles", lambda *_args: {
        "status": "success", "data": {"candles": [
            ["2026-10-29T10:00:00+05:30", 11, 13, 10, 12, 100],
            ["2026-10-28T10:00:00+05:30", 9, 12, 8, 11, 200],
        ]},
    })
    result = market_data.get_instrument_history(
        REAL_INSTRUMENT["instrument_key"],
        from_date=date.today() - timedelta(days=2), to_date=date.today(),
    )
    assert len(result["candles"]) == 2
    assert result["candles"][0]["timestamp"].startswith("2026-10-28")
    assert result["candles"][1]["close"] == 12


def test_market_feed_proto_decoder_returns_only_selected_real_instrument():
    response = market_data_feed_pb2.FeedResponse(type=market_data_feed_pb2.live_feed)
    update = response.feeds[REAL_INSTRUMENT["instrument_key"]].ltpc
    update.ltp = 123.5
    update.cp = 120.0
    update.ltt = 1793268000000
    instrument = {**REAL_INSTRUMENT, "instrument_key": REAL_INSTRUMENT["instrument_key"]}
    decoded = market_stream.decode_market_feed(response.SerializeToString(), instrument)
    assert len(decoded) == 1
    assert decoded[0]["last_price"] == 123.5
    assert decoded[0]["change"] == 3.5
    assert decoded[0]["delivery"] == "stream"


def test_market_feed_proto_decoder_rejects_malformed_bytes():
    with pytest.raises(ValueError):
        market_stream.decode_market_feed(b"\xff", REAL_INSTRUMENT)


def test_websocket_stream_rejects_invalid_keys_before_upstream_connect():
    with client.websocket_connect("/api/market/stream/not-an-equity-key") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "unavailable"
        assert "supported NSE or BSE equity" in message["detail"]


def test_websocket_stream_reports_missing_credentials_without_breaking_rest(monkeypatch):
    monkeypatch.setattr(market_data, "_selected_provider_name", lambda: "upstox")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "")
    monkeypatch.setattr(upstox_service, "_market_feed_access_token", lambda: "")
    monkeypatch.setattr(market_routes, "feed_manager", UpstoxMarketFeedManager())
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "test source", None)
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)

    with client.websocket_connect(f"/api/market/stream/{REAL_INSTRUMENT['instrument_key']}") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "unavailable"
    assert "UPSTOX_ANALYTICS_TOKEN" in message["detail"]


def test_websocket_stream_subscribes_forwards_provider_frame_and_cleans_up(monkeypatch):
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "test source", None)
    frame = market_data_feed_pb2.FeedResponse(type=market_data_feed_pb2.live_feed)
    update = frame.feeds[REAL_INSTRUMENT["instrument_key"]].ltpc
    update.ltp = 1512.5
    update.cp = 1500.0
    update.ltt = 1793268000000

    class FakeUpstream:
        def __init__(self):
            self.sent = []
            self.closed = False
            self.recv_count = 0
            self.incoming = asyncio.Queue()
            self.incoming.put_nowait(frame.SerializeToString())

        async def send(self, payload):
            self.sent.append(json.loads(payload.decode("utf-8")))

        async def recv(self):
            if self.closed:
                raise ConnectionError("closed")
            return await self.incoming.get()

        async def close(self):
            self.closed = True

    fake = FakeUpstream()

    async def connect(_uri, **_kwargs):
        return fake

    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(market_data, "_selected_provider_name", lambda: "upstox")
    monkeypatch.setattr(market_routes, "feed_manager", UpstoxMarketFeedManager(
        authorize=lambda: "wss://feed.example.test/authorized", connect=connect
    ))

    with client.websocket_connect(f"/api/market/stream/{REAL_INSTRUMENT['instrument_key']}") as websocket:
        connected = websocket.receive_json()
        forwarded = websocket.receive_json()
        websocket.send_text("unsubscribe")

    assert connected["type"] == "connected"
    assert fake.sent[0]["method"] == "sub"
    assert fake.sent[0]["data"]["instrumentKeys"] == [REAL_INSTRUMENT["instrument_key"]]
    assert forwarded["type"] == "quote"
    assert forwarded["quote"]["last_price"] == 1512.5
    assert forwarded["quote"]["delivery"] == "stream"
    assert fake.sent[1]["method"] == "unsub"
    assert fake.closed is True


def test_frontend_disconnect_releases_feed_subscription_and_socket(monkeypatch):
    instrument = instrument_catalog._normalize_instrument(REAL_INSTRUMENT, "test source", None)

    class FakeUpstream:
        def __init__(self):
            self.sent = []
            self.closed = False
            self.incoming = asyncio.Queue()

        async def send(self, payload):
            self.sent.append(json.loads(payload.decode("utf-8")))

        async def recv(self):
            return await self.incoming.get()

        async def close(self):
            self.closed = True

    fake = FakeUpstream()

    async def connect(_uri, **_kwargs):
        return fake

    manager = UpstoxMarketFeedManager(
        authorize=lambda: "memory-only",
        connect=connect,
    )
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(market_data, "_selected_provider_name", lambda: "upstox")
    monkeypatch.setattr(market_routes, "feed_manager", manager)

    with client.websocket_connect(f"/api/market/stream/{REAL_INSTRUMENT['instrument_key']}") as websocket:
        assert websocket.receive_json()["type"] == "connected"

    assert manager.status_snapshot()["subscribed_instrument_count"] == 0
    assert fake.sent[-1]["method"] == "unsub"
    assert fake.closed is True


def test_rest_snapshot_remains_available_when_stream_is_unauthorized(monkeypatch):
    class SnapshotProvider:
        name = "Upstox"

        def fetch(self, instruments):
            return [{
                "key": item["key"], "symbol": item["symbol"], "instrument_id": item["instrument_id"],
                "provider_symbol": item["instrument_id"], "last_price": 123.4, "change": 1.2,
                "change_percent": 0.9, "currency": "INR", "source": "Upstox",
                "source_timestamp": "2026-10-29T10:00:00+00:00", "fetched_at": "2026-10-29T10:01:00+00:00",
                "freshness": "stale", "status": "available", "delivery": "rest",
            } for item in instruments]

    manager = UpstoxMarketFeedManager(authorize=lambda: "unused", connect=lambda *_args, **_kwargs: None)
    manager._set_state("unauthorized", "authorization_rejected")
    monkeypatch.setattr(market_routes, "feed_manager", manager)
    monkeypatch.setattr(market_data, "_selected_provider_name", lambda: "upstox")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "private-test-token")
    monkeypatch.setitem(market_data._PROVIDERS, "upstox", SnapshotProvider())

    response = client.get("/api/market/quotes?symbols=nifty-50")

    assert response.status_code == 200
    quote = response.json()["quotes"][0]
    assert quote["last_price"] == 123.4
    assert quote["delivery"] == "rest"
    assert quote["freshness"] == "stale"


def test_market_status_exposes_safe_feed_health_fields(monkeypatch):
    secret = "private-token-value"
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "upstox")
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: secret)
    manager = UpstoxMarketFeedManager(authorize=lambda: "unused", connect=lambda *_args, **_kwargs: None)
    manager.last_message_received_at = "2026-10-29T10:00:00+00:00"
    manager.last_source_timestamp = "2026-10-29T09:59:58+00:00"
    manager.upstream_message_count = 2
    manager._set_state("unauthorized", "authorization_rejected")
    monkeypatch.setattr(market_routes, "feed_manager", manager)

    response = client.get("/api/market/status")

    assert response.status_code == 200
    status = response.json()
    assert status["stream_configured"] is True
    assert status["connection_state"] == "unauthorized"
    assert status["last_message_received_at"] == manager.last_message_received_at
    assert status["last_source_timestamp"] == manager.last_source_timestamp
    assert status["upstream_message_count"] == 2
    assert status["stream_failure_reason"] == "Upstox rejected the configured feed credential."
    assert secret not in response.text
