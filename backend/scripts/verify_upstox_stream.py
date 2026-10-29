"""Bounded live Upstox V3 feed diagnostic (not a simulated/unit test)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import instrument_catalog, upstox_service
from app.services.market_feed_manager import MarketFeedManagerError, UpstoxMarketFeedManager


def _select_reliance() -> dict[str, Any]:
    result = instrument_catalog.search_instruments("RELIANCE", exchange="NSE", page=1, records=20)
    instruments = result.get("instruments")
    if not isinstance(instruments, list):
        raise RuntimeError("Catalogue returned an unexpected result")
    for instrument in instruments:
        if isinstance(instrument, dict) and instrument.get("trading_symbol", "").upper() == "RELIANCE":
            return instrument
    raise RuntimeError("RELIANCE NSE was not present in the current catalogue search")


async def verify(timeout_seconds: int) -> dict[str, object]:
    manager = UpstoxMarketFeedManager()
    credential_configured = bool(upstox_service._market_feed_token())
    report: dict[str, object] = {
        "credential_configured": credential_configured,
        "authorization": "not_attempted",
        "websocket_connection": "not_attempted",
        "subscription": "not_attempted",
        "upstream_messages_received": 0,
        "instrument_key": None,
        "instrument": None,
        "source_timestamp": None,
        "receipt_timestamp": None,
        "freshness": "unknown",
        "market_session_note": _market_session_note(),
        "decoded_instrument_matches_subscription": False,
        "real_time_acceptance": "not_passed",
        "error_category": None,
    }
    if not credential_configured:
        report["authorization"] = "not_attempted"
        report["error_category"] = "credentials_missing"
        return report

    try:
        instrument = await asyncio.wait_for(asyncio.to_thread(_select_reliance), timeout=min(15, timeout_seconds))
    except asyncio.TimeoutError:
        report["error_category"] = "catalogue_timeout"
        return report
    except Exception:
        report["error_category"] = "catalogue_unavailable"
        return report

    key = instrument.get("instrument_key")
    report["instrument_key"] = key if isinstance(key, str) else None
    report["instrument"] = {
        field: instrument.get(field)
        for field in ("trading_symbol", "name", "exchange", "segment")
        if isinstance(instrument.get(field), str)
    }
    if not isinstance(key, str) or not key:
        report["error_category"] = "catalogue_invalid_instrument"
        return report

    queue: asyncio.Queue[dict[str, object]] | None = None
    try:
        queue = await asyncio.wait_for(manager.subscribe(instrument, mode="ltpc"), timeout=min(25, timeout_seconds))
        report["authorization"] = "succeeded" if manager.last_authorized_at else "failed"
        report["websocket_connection"] = "connected" if manager.last_connected_at else "failed"
        report["subscription"] = "succeeded"
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_quote: dict[str, object] | None = None
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if event.get("type") == "quote" and isinstance(event.get("quote"), dict):
                candidate = event["quote"]
                report["decoded_instrument_matches_subscription"] = candidate.get("instrument_key") == key
                if candidate.get("instrument_key") == key:
                    last_quote = candidate
                    report["receipt_timestamp"] = event.get("received_at") or candidate.get("fetched_at")
                    report["source_timestamp"] = candidate.get("source_timestamp")
                    report["freshness"] = candidate.get("freshness", "unknown")
            if event.get("type") == "unavailable":
                report["error_category"] = "feed_unavailable"
                break
        snapshot = manager.status_snapshot()
        report["upstream_messages_received"] = snapshot["upstream_message_count"]
        if last_quote and last_quote.get("delivery") == "stream" and report["decoded_instrument_matches_subscription"] and last_quote.get("freshness") == "fresh":
            report["real_time_acceptance"] = "passed"
        if manager.last_error_category:
            report["error_category"] = manager.last_error_category
    except asyncio.TimeoutError:
        report["authorization"] = "succeeded" if manager.last_authorized_at else "timed_out"
        report["websocket_connection"] = "connected" if manager.last_connected_at else "not_established"
        report["subscription"] = "not_completed"
        report["error_category"] = "feed_setup_timeout"
    except MarketFeedManagerError as exc:
        report["authorization"] = "succeeded" if manager.last_authorized_at else "failed" if exc.category.startswith("authorization") else "not_attempted"
        report["websocket_connection"] = "connected" if manager.last_connected_at else "failed" if manager.last_authorized_at else "not_established"
        report["subscription"] = "failed"
        report["error_category"] = exc.category
    finally:
        if queue is not None:
            try:
                await asyncio.wait_for(manager.unsubscribe(key, queue), timeout=5)
            except Exception:
                report["error_category"] = report["error_category"] or "cleanup_failed"
        report["upstream_messages_received"] = manager.status_snapshot()["upstream_message_count"]
    return report


def _market_session_note() -> str:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    if now.weekday() >= 5 or not time(9, 15) <= now.time().replace(tzinfo=None) <= time(15, 30):
        return "Outside regular NSE cash-market hours; holiday and special-session calendars are not checked."
    return "Within regular NSE cash-market hours; a fresh tick is not guaranteed for every instrument."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=60, help="Maximum feed observation time in seconds (5–90; default 60)")
    args = parser.parse_args()
    if not 5 <= args.timeout <= 90:
        parser.error("--timeout must be between 5 and 90 seconds")

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    try:
        report = asyncio.run(asyncio.wait_for(verify(args.timeout), timeout=90))
    except TimeoutError:
        report = {
            "credential_configured": bool(upstox_service._market_feed_token()),
            "authorization": "unknown",
            "websocket_connection": "unknown",
            "subscription": "unknown",
            "upstream_messages_received": 0,
            "instrument_key": None,
            "instrument": None,
            "source_timestamp": None,
            "receipt_timestamp": None,
            "freshness": "unknown",
            "market_session_note": _market_session_note(),
            "decoded_instrument_matches_subscription": False,
            "real_time_acceptance": "not_passed",
            "error_category": "diagnostic_timeout",
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["real_time_acceptance"] != "passed":
        print("note: Outside exchange hours, connection and subscription may succeed without a fresh equity tick.")
    return 0 if report["real_time_acceptance"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
