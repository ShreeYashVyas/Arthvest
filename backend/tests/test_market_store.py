"""Persistence tests for normalized instruments and Upstox candle history."""

from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep

import pytest

from app.services import instrument_catalog, market_data, market_store, observation_store
from sqlalchemy.orm import Session


@pytest.fixture
def market_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'market-history.db'}")
    assert observation_store.initialize_storage()
    return tmp_path


def _instrument(key: str, exchange: str) -> dict:
    return {
        "instrument_key": key, "exchange": exchange, "segment": f"{exchange}_EQ",
        "trading_symbol": "ACME", "name": "Acme Limited", "short_name": "Acme",
        "isin": "INE123A01001", "instrument_type": "EQ", "lot_size": 1,
        "tick_size": 0.05, "source": "Upstox instrument master",
        "catalogue_updated_at": "2026-10-29T10:00:00+00:00",
    }


def _candle(timestamp="2026-10-28T09:15:00+05:30", close=101.25):
    return {
        "timestamp": timestamp, "open": 100, "high": 103, "low": 99,
        "close": close, "volume": 1000, "open_interest": 12,
        "source": "Upstox historical", "fetched_at": "2026-10-29T04:00:00+00:00",
        "quality_status": "provider_validated",
    }


def test_instrument_identity_keeps_nse_and_bse_listings_separate(market_db):
    assert market_store.upsert_instruments([
        _instrument("NSE_EQ|INE123A01001", "NSE"),
        _instrument("BSE_EQ|INE123A01001", "BSE"),
    ]) == {"inserted_count": 2, "updated_count": 0}

    assert market_store.get_instrument("NSE_EQ|INE123A01001")["exchange"] == "NSE"
    assert market_store.get_instrument("BSE_EQ|INE123A01001")["exchange"] == "BSE"
    assert len(market_store.search_instruments("ACME")) == 2


def test_candle_upsert_is_idempotent_and_keeps_utc_timestamp(market_db):
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    market_store.upsert_instruments([instrument])
    run = market_store.create_sync_run(
        instrument_key=instrument["instrument_key"], unit="days", interval=1,
        from_date=date(2026, 10, 28), to_date=date(2026, 10, 28),
    )
    assert market_store.finish_sync_success(run, instrument, "days", 1, [_candle()]) == {
        "inserted_count": 1, "updated_count": 0, "fetched_count": 1,
    }
    update = market_store.create_sync_run(
        instrument_key=instrument["instrument_key"], unit="days", interval=1,
        from_date=date(2026, 10, 28), to_date=date(2026, 10, 28),
    )
    assert market_store.finish_sync_success(update, instrument, "days", 1, [_candle(close=102)]) == {
        "inserted_count": 0, "updated_count": 1, "fetched_count": 1,
    }
    candles = market_store.list_candles(
        instrument["instrument_key"], "days", 1, date(2026, 10, 28), date(2026, 10, 28)
    )
    assert len(candles) == 1
    assert candles[0]["timestamp"] == "2026-10-28T03:45:00+00:00"
    assert candles[0]["close"] == 102
    assert candles[0]["open_interest"] == 12


def test_history_request_persists_then_reads_without_refetch_and_survives_reinit(
    market_db, monkeypatch
):
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    calls = []

    def fake_history(key, unit, interval, to_date, from_date):
        calls.append((key, unit, interval, to_date, from_date))
        return {"data": {"candles": [[
            "2026-10-28T09:15:00+05:30", 100, 103, 99, 101.25, 1000, 12,
        ]]}}

    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", fake_history)
    args = dict(unit="days", interval=1, from_date=date(2026, 10, 28), to_date=date(2026, 10, 28))
    first = market_data.get_instrument_history(instrument["instrument_key"], **args)
    assert first["persistence_status"] == "available"
    assert first["sync_status"] == "synchronized"
    assert first["inserted_count"] == 1
    assert first["candles"][0]["close"] == 101.25
    assert first["technical_indicators"]["status"] == "insufficient_history"

    second = market_data.get_instrument_history(instrument["instrument_key"], **args)
    assert len(calls) == 1
    assert second["candles"] == first["candles"]
    assert second["inserted_count"] == 0

    # A fresh service call after the in-process future/cache is cleared still reads SQL storage.
    market_data._HISTORY_IN_FLIGHT.clear()
    monkeypatch.setattr(
        market_data.upstox_service, "get_historical_candles",
        lambda *_args: pytest.fail("covered history must not refetch after service reinitialization"),
    )
    restarted = market_data.get_instrument_history(instrument["instrument_key"], **args)
    assert restarted["history_source"] == "database"
    assert restarted["candles"][0]["close"] == 101.25


def test_history_fetch_survives_database_write_failure_without_claiming_persistence(
    market_db, monkeypatch
):
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", lambda *_args: {
        "data": {"candles": [["2026-10-28T09:15:00+05:30", 100, 103, 99, 101.25, 1000, 12]]}
    })
    monkeypatch.setattr(market_store, "finish_sync_success", lambda *_args: (_ for _ in ()).throw(OSError("write failure")))

    result = market_data.get_instrument_history(
        instrument["instrument_key"], unit="days", interval=1,
        from_date=date(2026, 10, 28), to_date=date(2026, 10, 28),
    )
    assert result["candles"][0]["close"] == 101.25
    assert result["history_source"] == "Upstox Historical API (not persisted)"
    assert result["persistence_status"] == "write_failed"
    assert result["sync_status"] == "synchronization_failed"
    assert result["coverage_complete"] is True


def test_upstream_failure_returns_existing_history_as_stale(market_db, monkeypatch):
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", lambda *_args: {
        "data": {"candles": [["2026-10-28T09:15:00+05:30", 100, 103, 99, 101.25, 1000, 12]]}
    })
    one_day = dict(unit="days", interval=1, from_date=date(2026, 10, 28), to_date=date(2026, 10, 28))
    market_data.get_instrument_history(instrument["instrument_key"], **one_day)

    def upstream_unavailable(*_args):
        from app.services.upstox_service import UpstoxServiceError
        raise UpstoxServiceError("Upstox history is unavailable.", 503)

    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", upstream_unavailable)
    stale = market_data.get_instrument_history(
        instrument["instrument_key"], unit="days", interval=1,
        from_date=date(2026, 10, 27), to_date=date(2026, 10, 28),
    )
    assert stale["candles"][0]["close"] == 101.25
    assert stale["history_source"] == "database"
    assert stale["sync_status"] == "stale"
    assert stale["coverage_complete"] is False
    assert stale["last_failure_category"] == "upstream_unavailable"


def test_missing_database_serves_real_fetch_without_claiming_persistence(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", lambda *_args: {
        "data": {"candles": [["2026-10-28T09:15:00+05:30", 100, 103, 99, 101.25, 1000, 12]]}
    })
    result = market_data.get_instrument_history(
        instrument["instrument_key"], unit="days", interval=1,
        from_date=date(2026, 10, 28), to_date=date(2026, 10, 28),
    )
    assert result["candles"][0]["close"] == 101.25
    assert result["persistence_status"] == "configuration_missing"
    assert result["history_source"] == "Upstox Historical API (not persisted)"
    assert result["sync_status"] == "synchronization_failed"
    assert result["last_failure_category"] == "database_configuration_missing"


def test_concurrent_identical_history_requests_share_one_upstream_fetch(market_db, monkeypatch):
    instrument = _instrument("NSE_EQ|INE123A01001", "NSE")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda _key: instrument)
    calls = 0
    calls_lock = Lock()

    def fake_history(*_args):
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.12)
        return {"data": {"candles": [["2026-10-28T09:15:00+05:30", 100, 103, 99, 101.25, 1000, 12]]}}

    monkeypatch.setattr(market_data.upstox_service, "get_historical_candles", fake_history)
    start = Barrier(2)
    args = dict(unit="days", interval=1, from_date=date(2026, 10, 28), to_date=date(2026, 10, 28))

    def request_history():
        start.wait(timeout=1)
        return market_data.get_instrument_history(instrument["instrument_key"], **args)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: request_history(), range(2)))

    assert calls == 1
    assert results[0]["candles"] == results[1]["candles"]
    assert results[0]["sync_status"] == "synchronized"


def test_catalogue_sync_status_is_separate_from_history_sync_status(market_db):
    market_store.upsert_instruments([_instrument("NSE_EQ|INE123A01001", "NSE")])
    run = market_store.create_catalogue_sync_run()
    market_store.finish_catalogue_sync(run, fetched_count=3, inserted_count=2, updated_count=1)
    result = market_store.global_history_summary()
    assert result["catalogue_sync_status"] == "synchronized"
    assert result["market_history_status"] == "initial_sync_pending"
    assert result["catalogue_last_successful_sync_at"] is not None


def test_recent_history_coverage_expires_for_bounded_incremental_refresh(market_db):
    instrument_key = "NSE_EQ|INE123A01001"
    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(timezone.utc).astimezone(ist).date()
    start = today - timedelta(days=14)
    recent_start = today - timedelta(days=market_store.COVERAGE_REFRESH_DAYS)
    run = market_store.create_sync_run(
        instrument_key=instrument_key, unit="days", interval=1,
        from_date=start, to_date=today,
    )
    with Session(market_store._engine()) as session, session.begin():
        row = session.get(market_store.MarketHistorySyncRun, run)
        row.status = "synchronized"
        row.finished_at = datetime.now(timezone.utc) - timedelta(minutes=market_store.COVERAGE_REFRESH_MINUTES + 1)

    assert market_store.successful_coverage(instrument_key, "days", 1) == [
        (start, recent_start - timedelta(days=1))
    ]
