"""Upstox Market Data Feed V3 Protobuf decoding and upstream bridge helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import math

from google.protobuf.message import DecodeError

from app.schemas import market_data_feed_pb2
from app.services.market_data import _freshness


def decode_market_feed(payload: bytes, instrument: dict[str, object]) -> list[dict[str, object]]:
    """Decode the provider's official V3 protobuf and emit normalized LTPC updates."""
    response = market_data_feed_pb2.FeedResponse()
    try:
        response.ParseFromString(payload)
    except DecodeError as exc:
        raise ValueError("Malformed Upstox market-feed message.") from exc
    if response.type == market_data_feed_pb2.market_info:
        return []
    updates: list[dict[str, object]] = []
    for key, feed in response.feeds.items():
        selected = feed.WhichOneof("FeedUnion")
        ltpc = None
        if selected == "ltpc":
            ltpc = feed.ltpc
        elif selected == "fullFeed":
            full = feed.fullFeed
            variant = full.WhichOneof("FullFeedUnion")
            if variant == "marketFF":
                ltpc = full.marketFF.ltpc
            elif variant == "indexFF":
                ltpc = full.indexFF.ltpc
        if ltpc is None or key != instrument.get("instrument_key"):
            continue
        price = float(ltpc.ltp)
        previous_close = float(ltpc.cp)
        if not math.isfinite(price) or price <= 0:
            continue
        change = price - previous_close if math.isfinite(previous_close) and previous_close > 0 else None
        change_percent = change / previous_close * 100 if change is not None else None
        source_timestamp = (
            datetime.fromtimestamp(ltpc.ltt / 1000, timezone.utc).isoformat()
            if ltpc.ltt > 0
            else None
        )
        now = datetime.now(timezone.utc).isoformat()
        quote = {
            "instrument_key": key,
            "symbol": instrument.get("trading_symbol"),
            "name": instrument.get("name"),
            "exchange": instrument.get("exchange"),
            "last_price": price,
            "change": change,
            "change_percent": change_percent,
            "previous_close": previous_close if previous_close > 0 else None,
            "open": None,
            "high": None,
            "low": None,
            "volume": None,
            "currency": "INR",
            "source": "Upstox Market Data Feed V3",
            "source_timestamp": source_timestamp,
            "fetched_at": now,
            "freshness": _freshness(source_timestamp, "Upstox"),
            "status": "available",
            "delivery": "stream",
        }
        updates.append(quote)
    return updates
