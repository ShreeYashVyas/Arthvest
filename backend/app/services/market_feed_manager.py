"""Shared Upstox Market Data Feed V3 connection and subscription ownership."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.schemas import market_data_feed_pb2
from app.services import market_stream, upstox_service

logger = logging.getLogger(__name__)

MAX_SUBSCRIBED_INSTRUMENTS = 500
QUEUE_SIZE = 100
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_BASE_SECONDS = 0.5
RECONNECT_MAX_SECONDS = 8.0
SUPPORTED_MODES = {"ltpc", "full", "full_d30"}
MODE_RANK = {"ltpc": 0, "full": 1, "full_d30": 2}


class MarketFeedManagerError(RuntimeError):
    """Safe feed error with a state suitable for API/UI status."""

    def __init__(self, detail: str, state: str, category: str) -> None:
        super().__init__(detail)
        self.state = state
        self.category = category


ConnectCallable = Callable[..., Awaitable[Any]]
AuthorizeCallable = Callable[[], str]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UpstoxMarketFeedManager:
    """Multiplex selected instruments and clients over one process-wide feed."""

    def __init__(
        self,
        *,
        authorize: AuthorizeCallable | None = None,
        connect: ConnectCallable | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if connect is None:
            from websockets.asyncio.client import connect as websocket_connect

            connect = websocket_connect
        self._authorize = authorize or upstox_service.get_market_feed_authorized_url
        self._connect = connect
        self._sleep = sleep
        self._jitter = jitter
        self._lock = asyncio.Lock()
        self._socket: Any = None
        self._reader_task: asyncio.Task[None] | None = None
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, object]]]] = {}
        self._instruments: dict[str, dict[str, object]] = {}
        self._client_modes: dict[str, dict[asyncio.Queue[dict[str, object]], str]] = {}
        self.connection_state = "disconnected"
        self.last_authorized_at: str | None = None
        self.last_connected_at: str | None = None
        self.last_message_received_at: str | None = None
        self.last_tick_received_at: str | None = None
        self.last_source_timestamp: str | None = None
        self.upstream_message_count = 0
        self.last_error_category: str | None = None
        self.reconnect_attempts = 0

    def status_snapshot(self) -> dict[str, object]:
        return {
            "connection_state": self.connection_state,
            "last_authorized_at": self.last_authorized_at,
            "last_connected_at": self.last_connected_at,
            "last_message_received_at": self.last_message_received_at,
            "last_tick_received_at": self.last_tick_received_at,
            "last_source_timestamp": self.last_source_timestamp,
            "upstream_message_count": self.upstream_message_count,
            "subscribed_instrument_count": len(self._subscribers),
            "reconnect_attempts": self.reconnect_attempts,
            "stream_error_category": self.last_error_category,
            "stream_failure_reason": self._safe_failure_reason(self.last_error_category),
        }

    async def subscribe(
        self, instrument: dict[str, object], mode: str = "ltpc"
    ) -> asyncio.Queue[dict[str, object]]:
        key = instrument.get("instrument_key")
        if not isinstance(key, str) or not key:
            raise MarketFeedManagerError("A resolved instrument key is required.", "unavailable", "invalid_instrument")
        if mode not in SUPPORTED_MODES:
            raise MarketFeedManagerError("The requested Upstox feed mode is unsupported.", "unavailable", "unsupported_mode")

        async with self._lock:
            subscribers = self._subscribers.get(key)
            first_subscriber = subscribers is None
            if first_subscriber and len(self._subscribers) >= MAX_SUBSCRIBED_INSTRUMENTS:
                raise MarketFeedManagerError("The local live-feed subscription limit is currently in use.", "unavailable", "subscription_limit")
            if self._socket is None:
                await self._open_locked()
            queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=QUEUE_SIZE)
            if subscribers is None:
                subscribers = set()
                self._subscribers[key] = subscribers
                self._instruments[key] = instrument
                self._client_modes[key] = {}
            subscribers.add(queue)
            self._client_modes[key][queue] = mode
            if first_subscriber:
                try:
                    await self._send_subscription_locked(key, "sub", self._effective_mode(key))
                except Exception as exc:
                    self._subscribers.pop(key, None)
                    self._instruments.pop(key, None)
                    self._client_modes.pop(key, None)
                    if not self._subscribers:
                        await self._close_locked()
                    raise MarketFeedManagerError("Upstox rejected the instrument subscription.", "unavailable", "subscription_failed") from exc
            self._start_reader_locked()
            return queue

    async def change_mode(
        self,
        instrument_key: str,
        queue: asyncio.Queue[dict[str, object]],
        mode: str,
    ) -> None:
        if mode not in SUPPORTED_MODES:
            raise MarketFeedManagerError("The requested Upstox feed mode is unsupported.", "unavailable", "unsupported_mode")
        async with self._lock:
            modes = self._client_modes.get(instrument_key)
            if modes is None or queue not in modes:
                raise MarketFeedManagerError("This client does not own the instrument subscription.", "unavailable", "subscription_missing")
            prior = self._effective_mode(instrument_key)
            modes[queue] = mode
            effective = self._effective_mode(instrument_key)
            if effective != prior and self._socket is not None:
                await self._send_subscription_locked(instrument_key, "change_mode", effective)

    async def unsubscribe(
        self, instrument_key: str, queue: asyncio.Queue[dict[str, object]]
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(instrument_key)
            modes = self._client_modes.get(instrument_key)
            if subscribers is None or modes is None or queue not in subscribers:
                return
            prior = self._effective_mode(instrument_key)
            subscribers.remove(queue)
            modes.pop(queue, None)
            if not subscribers:
                self._subscribers.pop(instrument_key, None)
                self._client_modes.pop(instrument_key, None)
                self._instruments.pop(instrument_key, None)
                if self._socket is not None:
                    try:
                        await self._send_subscription_locked(instrument_key, "unsub", prior)
                    except Exception as exc:
                        logger.warning("Upstox unsubscribe failed (%s)", type(exc).__name__)
            else:
                effective = self._effective_mode(instrument_key)
                if effective != prior and self._socket is not None:
                    try:
                        await self._send_subscription_locked(instrument_key, "change_mode", effective)
                    except Exception as exc:
                        logger.warning("Upstox feed-mode change failed (%s)", type(exc).__name__)
            if not self._subscribers:
                await self._close_locked()
                self._set_state("disconnected", None)

    async def _open_locked(self) -> None:
        self._set_state("connecting", None)
        try:
            # The URI is single-use and remains only in this stack frame.
            authorized_uri = await asyncio.to_thread(self._authorize)
            self.last_authorized_at = _now()
        except upstox_service.UpstoxServiceError as exc:
            rejected = "rejected the configured credential" in str(exc).lower()
            state = "unauthorized" if rejected else "unavailable"
            missing = exc.status_code == 503 and "requires UPSTOX_ANALYTICS_TOKEN" in str(exc)
            category = "authorization_rejected" if rejected else "credentials_missing" if missing else "authorization_failed"
            self._set_state(state, category)
            detail = (
                "Upstox rejected the configured feed credential."
                if rejected
                else "Live streaming requires UPSTOX_ANALYTICS_TOKEN or UPSTOX_ACCESS_TOKEN."
                if missing
                else "Could not authorize an Upstox live-feed connection."
            )
            raise MarketFeedManagerError(detail, state, category) from None
        try:
            self._socket = await self._connect(
                authorized_uri,
                open_timeout=10,
                close_timeout=3,
                ping_interval=20,
                max_size=1_000_000,
            )
        except Exception as exc:
            self._socket = None
            self._set_state("unavailable", "connection_failed")
            raise MarketFeedManagerError("Could not establish the Upstox live-feed connection.", "unavailable", "connection_failed") from exc
        self.last_connected_at = _now()
        self.reconnect_attempts = 0
        self._set_state("connected", None)

    async def _send_subscription_locked(self, key: str, method: str, mode: str) -> None:
        if self._socket is None:
            raise RuntimeError("Upstream feed is not connected")
        request = {
            "guid": f"arthvest-{random.getrandbits(64):016x}",
            "method": method,
            "data": {"mode": mode, "instrumentKeys": [key]},
        }
        await self._socket.send(json.dumps(request).encode("utf-8"))

    def _effective_mode(self, key: str) -> str:
        modes = self._client_modes.get(key, {}).values()
        return max(modes, key=lambda mode: MODE_RANK[mode], default="ltpc")

    def _start_reader_locked(self) -> None:
        if self._reader_task is None or self._reader_task.done():
            self._reader_task = asyncio.create_task(self._reader_loop())

    async def _reader_loop(self) -> None:
        while True:
            socket = self._socket
            if socket is None:
                return
            try:
                payload = await socket.recv()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not await self._recover(type(exc).__name__):
                    return
                continue
            self.upstream_message_count += 1
            self.last_message_received_at = _now()
            if not isinstance(payload, bytes):
                self.last_error_category = "unexpected_frame_type"
                continue
            response = market_data_feed_pb2.FeedResponse()
            try:
                response.ParseFromString(payload)
            except Exception:
                self.last_error_category = "malformed_protobuf"
                logger.warning("Upstox sent a malformed Protobuf frame")
                continue
            if response.type == market_data_feed_pb2.market_info:
                self._broadcast({"type": "connection", "state": "connected", "message_received_at": self.last_message_received_at})
                continue
            for key in response.feeds:
                instrument = self._instruments.get(key)
                if instrument is None or key not in self._subscribers:
                    continue
                try:
                    updates = market_stream.decode_market_feed(payload, instrument)
                except ValueError:
                    self.last_error_category = "malformed_protobuf"
                    logger.warning("Upstox feed update could not be decoded")
                    continue
                for update in updates:
                    self.last_tick_received_at = update.get("fetched_at") if isinstance(update.get("fetched_at"), str) else _now()
                    self.last_source_timestamp = update.get("source_timestamp") if isinstance(update.get("source_timestamp"), str) else None
                    self._broadcast({"type": "quote", "received_at": self.last_message_received_at, "quote": update}, instrument_key=key)

    async def _recover(self, failure_category: str) -> bool:
        self._set_state("reconnecting", failure_category)
        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            self.reconnect_attempts = attempt + 1
            delay = min(RECONNECT_MAX_SECONDS, RECONNECT_BASE_SECONDS * (2**attempt))
            await self._sleep(self._jitter(delay * 0.8, delay * 1.2))
            async with self._lock:
                if not self._subscribers:
                    self._set_state("disconnected", None)
                    return False
                old_socket = self._socket
                self._socket = None
                if old_socket is not None:
                    try:
                        await old_socket.close()
                    except Exception:
                        pass
                try:
                    await self._open_locked()
                    for key in self._subscribers:
                        await self._send_subscription_locked(key, "sub", self._effective_mode(key))
                    self._set_state("connected", None)
                    return True
                except MarketFeedManagerError as exc:
                    if exc.state == "unauthorized" or exc.category in {"authorization_failed", "authorization_rejected"}:
                        self._broadcast({"type": "unavailable", "detail": str(exc), "state": exc.state})
                        return False
                    self._set_state("reconnecting", exc.category)
                except Exception as exc:
                    logger.warning("Upstox feed reconnect failed (%s)", type(exc).__name__)
                    self._set_state("reconnecting", "connection_failed")
        self._set_state("unavailable", "reconnect_limit_reached")
        self._broadcast({"type": "unavailable", "detail": "The Upstox live feed could not reconnect after bounded retries.", "state": "unavailable"})
        return False

    def _set_state(self, state: str, category: str | None) -> None:
        self.connection_state = state
        self.last_error_category = category
        event: dict[str, object] = {"type": "connection", "state": state}
        if category:
            event["error_category"] = category
        self._broadcast(event)

    @staticmethod
    def _safe_failure_reason(category: str | None) -> str | None:
        reasons = {
            "authorization_rejected": "Upstox rejected the configured feed credential.",
            "credentials_missing": "Live streaming credentials are not configured.",
            "authorization_failed": "Feed authorization failed.",
            "connection_failed": "Could not establish the Upstox WebSocket connection.",
            "subscription_failed": "Upstox rejected the instrument subscription.",
            "reconnect_limit_reached": "The feed stopped after its bounded reconnect attempts.",
            "malformed_protobuf": "Upstox sent an unreadable feed message.",
            "unexpected_frame_type": "Upstox sent an unsupported feed frame.",
        }
        return reasons.get(category) if category else None

    def _broadcast(self, event: dict[str, object], instrument_key: str | None = None) -> None:
        if instrument_key is None:
            targets = [queue for queues in self._subscribers.values() for queue in queues]
        else:
            targets = list(self._subscribers.get(instrument_key, set()))
        for queue in targets:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(dict(event))
            except asyncio.QueueFull:
                pass

    async def _close_locked(self) -> None:
        task = self._reader_task
        self._reader_task = None
        socket = self._socket
        self._socket = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        if socket is not None:
            try:
                await socket.close()
            except Exception as exc:
                logger.warning("Upstox feed close failed (%s)", type(exc).__name__)
        if task is not None and task is not asyncio.current_task() and not task.done():
            await asyncio.gather(task, return_exceptions=True)
