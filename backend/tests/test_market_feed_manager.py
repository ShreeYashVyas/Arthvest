"""Deterministic unit tests for Upstox feed authorization, ownership, and recovery."""

import asyncio
import json
from urllib.error import HTTPError

import pytest

from app.services import upstox_service
from app.services.market_feed_manager import MarketFeedManagerError, UpstoxMarketFeedManager


INSTRUMENT = {
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
    "name": "Reliance Industries Ltd",
    "exchange": "NSE",
    "segment": "NSE_EQ",
}


class FakeSocket:
    def __init__(self):
        self.sent: list[dict[str, object]] = []
        self.incoming: asyncio.Queue[bytes] = asyncio.Queue()
        self.closed = False

    async def send(self, payload: bytes):
        self.sent.append(json.loads(payload.decode("utf-8")))

    async def recv(self) -> bytes:
        if self.closed:
            raise ConnectionError("closed")
        return await self.incoming.get()

    async def close(self):
        self.closed = True


def test_feed_authorization_accepts_real_camel_case_field_and_uses_analytics_token(monkeypatch):
    secret = "analytics-token-never-logged"
    socket_uri = "wss://feed.example.test/one-time?code=sensitive"
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: secret)
    monkeypatch.setattr(upstox_service, "_market_feed_access_token", lambda: "oauth-fallback")
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"status": "success", "data": {"authorizedRedirectUri": socket_uri}}).encode()

    def open_request(request, timeout):
        observed["authorization"] = request.get_header("Authorization")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(upstox_service, "urlopen", open_request)
    assert upstox_service.get_market_feed_authorized_url() == socket_uri
    assert observed["authorization"] == f"Bearer {secret}"
    assert observed["timeout"] <= 10


def test_feed_authorization_uses_oauth_fallback_and_sanitizes_rejection(monkeypatch):
    monkeypatch.setattr(upstox_service, "_analytics_token", lambda: "")
    monkeypatch.setattr(upstox_service, "_market_feed_access_token", lambda: "oauth-secret")

    def reject(request, timeout):
        assert request.get_header("Authorization") == "Bearer oauth-secret"
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(upstox_service, "urlopen", reject)
    with pytest.raises(upstox_service.UpstoxServiceError) as error:
        upstox_service.get_market_feed_authorized_url()
    assert error.value.status_code == 502
    assert "oauth-secret" not in str(error.value)
    assert "rejected the configured credential" in str(error.value)


def test_multiple_clients_share_connection_and_reference_counted_subscriptions():
    async def run():
        sockets: list[FakeSocket] = []

        async def connect(_uri, **_kwargs):
            socket = FakeSocket()
            sockets.append(socket)
            return socket

        manager = UpstoxMarketFeedManager(
            authorize=lambda: "wss://memory-only.example.test/authorized",
            connect=connect,
        )
        first = await manager.subscribe(INSTRUMENT)
        second = await manager.subscribe(INSTRUMENT)
        assert len(sockets) == 1
        assert [msg["method"] for msg in sockets[0].sent] == ["sub"]
        assert manager.status_snapshot()["subscribed_instrument_count"] == 1

        await manager.change_mode(INSTRUMENT["instrument_key"], first, "full")
        assert sockets[0].sent[-1]["method"] == "change_mode"
        assert sockets[0].sent[-1]["data"]["mode"] == "full"

        await manager.unsubscribe(INSTRUMENT["instrument_key"], first)
        assert manager.status_snapshot()["subscribed_instrument_count"] == 1
        assert sockets[0].sent[-1]["method"] == "change_mode"
        assert sockets[0].sent[-1]["data"]["mode"] == "ltpc"

        await manager.unsubscribe(INSTRUMENT["instrument_key"], second)
        assert sockets[0].sent[-1]["method"] == "unsub"
        assert sockets[0].closed is True
        assert manager.status_snapshot()["connection_state"] == "disconnected"

    asyncio.run(run())


def test_unit_protobuf_tick_is_fanned_out_with_distinct_timestamps():
    async def run():
        from app.schemas import market_data_feed_pb2

        socket = FakeSocket()

        async def connect(_uri, **_kwargs):
            return socket

        manager = UpstoxMarketFeedManager(authorize=lambda: "wss://memory-only.test", connect=connect)
        queue1 = await manager.subscribe(INSTRUMENT)
        queue2 = await manager.subscribe(INSTRUMENT)
        response = market_data_feed_pb2.FeedResponse(type=market_data_feed_pb2.live_feed)
        ltpc = response.feeds[INSTRUMENT["instrument_key"]].ltpc
        ltpc.ltp = 1520.25
        ltpc.cp = 1500
        ltpc.ltt = 1793268000000
        await socket.incoming.put(response.SerializeToString())
        event1 = await asyncio.wait_for(queue1.get(), timeout=1)
        event2 = await asyncio.wait_for(queue2.get(), timeout=1)
        assert event1["type"] == event2["type"] == "quote"
        quote = event1["quote"]
        assert quote["last_price"] == 1520.25
        assert quote["source_timestamp"] != quote["fetched_at"]
        status = manager.status_snapshot()
        assert status["last_message_received_at"] is not None
        assert status["last_tick_received_at"] == quote["fetched_at"]
        assert status["last_source_timestamp"] == quote["source_timestamp"]
        assert status["upstream_message_count"] == 1
        assert event1["received_at"] == status["last_message_received_at"]
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue1)
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue2)

    asyncio.run(run())


def test_reconnect_uses_bounded_backoff_and_recovers_after_temporary_network_failure():
    async def run():
        class FailingSocket(FakeSocket):
            async def recv(self):
                raise OSError("private network diagnostic")

        first = FailingSocket()
        third = FakeSocket()
        connect_calls = {"count": 0}
        waits = []

        async def connect(_uri, **_kwargs):
            connect_calls["count"] += 1
            if connect_calls["count"] == 1:
                return first
            if connect_calls["count"] == 2:
                raise OSError("private connection diagnostic")
            socket = third
            return socket

        async def no_real_wait(seconds):
            waits.append(seconds)
            await asyncio.sleep(0)

        manager = UpstoxMarketFeedManager(
            authorize=lambda: "wss://memory-only.test",
            connect=connect,
            sleep=no_real_wait,
            jitter=lambda low, _high: low,
        )
        queue = await asyncio.wait_for(manager.subscribe(INSTRUMENT), timeout=1)
        for _ in range(100):
            if manager.connection_state == "connected" and connect_calls["count"] == 3:
                break
            await asyncio.sleep(0.001)
        assert manager.connection_state == "connected"
        assert connect_calls["count"] == 3
        assert waits == [pytest.approx(0.4), pytest.approx(0.8)]
        assert third.sent[0]["method"] == "sub"
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue)

    asyncio.run(asyncio.wait_for(run(), timeout=2))


def test_initial_invalid_credential_is_unauthorized_and_sanitized(caplog):
    async def run():
        secret = "never-return-this-secret"
        calls = {"count": 0}

        def reject():
            calls["count"] += 1
            raise upstox_service.UpstoxServiceError(
                f"Upstox rejected the configured credential {secret} for live market data.", 502
            )

        manager = UpstoxMarketFeedManager(authorize=reject, connect=lambda *_args, **_kwargs: None)
        with pytest.raises(MarketFeedManagerError) as error:
            await asyncio.wait_for(manager.subscribe(INSTRUMENT), timeout=1)
        snapshot = manager.status_snapshot()
        assert snapshot["connection_state"] == "unauthorized"
        assert snapshot["stream_error_category"] == "authorization_rejected"
        assert snapshot["stream_failure_reason"] == "Upstox rejected the configured feed credential."
        assert calls["count"] == 1
        assert secret not in str(error.value)
        assert secret not in caplog.text

    asyncio.run(asyncio.wait_for(run(), timeout=2))


def test_connected_without_provider_message_does_not_report_a_tick():
    async def run():
        socket = FakeSocket()

        async def connect(_uri, **_kwargs):
            return socket

        manager = UpstoxMarketFeedManager(authorize=lambda: "wss://memory-only.test", connect=connect)
        queue = await manager.subscribe(INSTRUMENT)
        status = manager.status_snapshot()
        assert status["connection_state"] == "connected"
        assert status["last_connected_at"] is not None
        assert status["last_message_received_at"] is None
        assert status["last_tick_received_at"] is None
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue)

    asyncio.run(run())


def test_permanent_auth_failure_stops_reconnect_attempts():
    async def run():
        from app.schemas import market_data_feed_pb2

        socket = FakeSocket()
        auth_calls = {"count": 0}

        def authorize():
            auth_calls["count"] += 1
            if auth_calls["count"] > 1:
                raise upstox_service.UpstoxServiceError("Upstox rejected the configured credential for live market data.", 502)
            return "wss://memory-only.test"

        async def connect(_uri, **_kwargs):
            return socket

        async def no_wait(_seconds):
            await asyncio.sleep(0)

        manager = UpstoxMarketFeedManager(authorize=authorize, connect=connect, sleep=no_wait, jitter=lambda low, _high: low)
        queue = await manager.subscribe(INSTRUMENT)
        await socket.incoming.put(b"\xff")
        # A malformed payload is ignored, so close the transport to trigger recovery.
        await socket.close()
        socket.incoming.put_nowait(b"\x00")
        for _ in range(100):
            if manager.connection_state == "unauthorized":
                break
            await asyncio.sleep(0.001)
        status = manager.status_snapshot()
        assert status["connection_state"] == "unauthorized"
        assert status["stream_error_category"] == "authorization_rejected"
        assert auth_calls["count"] == 2
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue)

    asyncio.run(run())


def test_status_keeps_connected_without_new_upstream_messages_unknown():
    async def run():
        socket = FakeSocket()

        async def connect(_uri, **_kwargs):
            return socket

        manager = UpstoxMarketFeedManager(authorize=lambda: "memory-only", connect=connect)
        queue = await asyncio.wait_for(manager.subscribe(INSTRUMENT), timeout=1)
        snapshot = manager.status_snapshot()
        assert snapshot["connection_state"] == "connected"
        assert snapshot["upstream_message_count"] == 0
        assert snapshot["last_message_received_at"] is None
        assert snapshot["last_source_timestamp"] is None
        assert snapshot["last_tick_received_at"] is None
        await manager.unsubscribe(INSTRUMENT["instrument_key"], queue)

    asyncio.run(asyncio.wait_for(run(), timeout=2))
