"""Persistent Upstox instrument, candle, and history-sync storage."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, delete, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.services import observation_store


Base = observation_store.Base
COVERAGE_REFRESH_DAYS = 7
COVERAGE_REFRESH_MINUTES = 15


class MarketInstrumentRecord(Base):
    """One exchange listing from the provider catalogue."""

    __tablename__ = "market_instruments"
    __table_args__ = (Index("ix_market_instruments_symbol_exchange", "trading_symbol", "exchange"),)

    instrument_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    segment: Mapped[str] = mapped_column(String(16), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    lot_size: Mapped[Decimal | None] = mapped_column(Numeric(16, 4), nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(16, 8), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    catalogue_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketCandleRecord(Base):
    """Provider-native OHLCV candle keyed by exchange listing and interval."""

    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("instrument_key", "unit", "interval", "candle_at", name="uq_market_candle_identity"),
        Index("ix_market_candles_range", "instrument_key", "unit", "interval", "candle_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_key: Mapped[str] = mapped_column(String(100), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    unit: Mapped[str] = mapped_column(String(12), nullable=False)
    interval: Mapped[int] = mapped_column(Integer, nullable=False)
    candle_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 4), nullable=False)
    open_interest: Mapped[Decimal | None] = mapped_column(Numeric(24, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False, default="provider_validated")


class MarketHistorySyncRun(Base):
    """A bounded catalogue or candle synchronization attempt."""

    __tablename__ = "market_history_sync_runs"
    __table_args__ = (Index("ix_market_sync_coverage", "instrument_key", "unit", "interval", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    instrument_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit: Mapped[str | None] = mapped_column(String(12), nullable=True)
    interval: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)


class MarketWatchlistRecord(Base):
    """Local-development single-user watchlist; identity is never client supplied."""

    __tablename__ = "market_watchlists"
    __table_args__ = (UniqueConstraint("owner_key", "name", name="uq_market_watchlist_owner_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketWatchlistEntryRecord(Base):
    """Ordered, exchange-specific entries belonging to one local watchlist."""

    __tablename__ = "market_watchlist_entries"

    watchlist_id: Mapped[int] = mapped_column(ForeignKey("market_watchlists.id", ondelete="CASCADE"), primary_key=True)
    instrument_key: Mapped[str] = mapped_column(ForeignKey("market_instruments.instrument_key"), primary_key=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketStorageDisabledError(RuntimeError):
    """Raised when market persistence is requested without DATABASE_URL."""


LOCAL_WATCHLIST_OWNER = "development-single-user"


def _watchlist_payload(session: Session, row: MarketWatchlistRecord) -> dict[str, Any]:
    entries = session.scalars(
        select(MarketWatchlistEntryRecord).where(
            MarketWatchlistEntryRecord.watchlist_id == row.id
        ).order_by(MarketWatchlistEntryRecord.order_index)
    ).all()
    instruments = [session.get(MarketInstrumentRecord, entry.instrument_key) for entry in entries]
    return {
        "id": row.id, "name": row.name,
        "created_at": _utc(row.created_at).isoformat(),
        "updated_at": _utc(row.updated_at).isoformat(),
        "instruments": [{
            "instrument_key": item.instrument_key, "exchange": item.exchange,
            "segment": item.segment, "trading_symbol": item.trading_symbol,
            "short_name": item.short_name, "name": item.name, "isin": item.isin,
            "instrument_type": item.instrument_type,
            "lot_size": float(item.lot_size) if item.lot_size is not None else None,
            "tick_size": float(item.tick_size) if item.tick_size is not None else None,
            "source": item.source,
            "catalogue_updated_at": _utc(item.catalogue_updated_at).isoformat() if item.catalogue_updated_at else None,
        } for item in instruments if item is not None],
    }


def list_watchlists() -> list[dict[str, Any]]:
    with Session(_engine()) as session:
        rows = session.scalars(select(MarketWatchlistRecord).where(
            MarketWatchlistRecord.owner_key == LOCAL_WATCHLIST_OWNER
        ).order_by(MarketWatchlistRecord.created_at, MarketWatchlistRecord.id)).all()
        return [_watchlist_payload(session, row) for row in rows]


def create_watchlist(name: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with Session(_engine()) as session, session.begin():
        row = MarketWatchlistRecord(
            owner_key=LOCAL_WATCHLIST_OWNER, name=name.strip(), created_at=now, updated_at=now,
        )
        session.add(row)
        session.flush()
        return _watchlist_payload(session, row)


def rename_watchlist(watchlist_id: int, name: str) -> dict[str, Any] | None:
    with Session(_engine()) as session, session.begin():
        row = session.scalar(select(MarketWatchlistRecord).where(
            MarketWatchlistRecord.id == watchlist_id,
            MarketWatchlistRecord.owner_key == LOCAL_WATCHLIST_OWNER,
        ))
        if row is None:
            return None
        row.name = name.strip()
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        return _watchlist_payload(session, row)


def delete_watchlist(watchlist_id: int) -> bool:
    with Session(_engine()) as session, session.begin():
        row = session.scalar(select(MarketWatchlistRecord).where(
            MarketWatchlistRecord.id == watchlist_id,
            MarketWatchlistRecord.owner_key == LOCAL_WATCHLIST_OWNER,
        ))
        if row is None:
            return False
        session.execute(delete(MarketWatchlistEntryRecord).where(
            MarketWatchlistEntryRecord.watchlist_id == watchlist_id
        ))
        session.delete(row)
        return True


def replace_watchlist_entries(watchlist_id: int, instrument_keys: list[str]) -> dict[str, Any] | None:
    with Session(_engine()) as session, session.begin():
        row = session.scalar(select(MarketWatchlistRecord).where(
            MarketWatchlistRecord.id == watchlist_id,
            MarketWatchlistRecord.owner_key == LOCAL_WATCHLIST_OWNER,
        ))
        if row is None:
            return None
        available = set(session.scalars(select(MarketInstrumentRecord.instrument_key).where(
            MarketInstrumentRecord.instrument_key.in_(instrument_keys)
        )).all()) if instrument_keys else set()
        if len(available) != len(instrument_keys):
            raise ValueError("Every watchlist instrument must exist in the validated catalogue")
        session.execute(delete(MarketWatchlistEntryRecord).where(
            MarketWatchlistEntryRecord.watchlist_id == watchlist_id
        ))
        now = datetime.now(timezone.utc)
        session.add_all([
            MarketWatchlistEntryRecord(
                watchlist_id=watchlist_id, instrument_key=key, order_index=index, added_at=now,
            ) for index, key in enumerate(instrument_keys)
        ])
        row.updated_at = now
        session.flush()
        return _watchlist_payload(session, row)


def create_catalogue_sync_run() -> int:
    with Session(_engine()) as session, session.begin():
        row = MarketHistorySyncRun(
            task_type="catalogue", status="synchronizing", started_at=datetime.now(timezone.utc),
            fetched_count=0, inserted_count=0, updated_count=0,
        )
        session.add(row)
        session.flush()
        return row.id


def finish_catalogue_sync(
    run_id: int, *, fetched_count: int, inserted_count: int = 0,
    updated_count: int = 0, error_category: str | None = None,
) -> None:
    with Session(_engine()) as session, session.begin():
        row = session.get(MarketHistorySyncRun, run_id)
        if row is None or row.status != "synchronizing":
            raise RuntimeError("Catalogue synchronization run is not active")
        row.status = "failed" if error_category else "synchronized"
        row.finished_at = datetime.now(timezone.utc)
        row.fetched_count = fetched_count
        row.inserted_count = inserted_count
        row.updated_count = updated_count
        row.error_category = error_category


def _engine():
    url = observation_store._database_url()
    if url is None:
        raise MarketStorageDisabledError("DATABASE_URL is not configured")
    observation_store._ensure_schema(url)
    return observation_store._engine(url)


def _utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"Invalid provider candle {field}")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid provider candle {field}") from exc
    if not result.is_finite():
        raise ValueError(f"Invalid provider candle {field}")
    return result


def upsert_instruments(instruments: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Upsert valid provider listings without deleting the prior catalogue."""
    now = datetime.now(timezone.utc)
    rows = [item for item in instruments if isinstance(item.get("instrument_key"), str)
            and item.get("instrument_key") and item.get("exchange") in {"NSE", "BSE"}]
    rows = list({str(item["instrument_key"]): item for item in rows}.values())
    inserted = updated = 0
    with Session(_engine()) as session, session.begin():
        for offset in range(0, len(rows), 500):
            chunk = rows[offset : offset + 500]
            keys = [str(item["instrument_key"]) for item in chunk]
            existing = session.scalars(select(MarketInstrumentRecord).where(MarketInstrumentRecord.instrument_key.in_(keys))).all()
            by_key = {row.instrument_key: row for row in existing}
            new_records = []
            for item in chunk:
                key = str(item["instrument_key"])
                record = by_key.get(key)
                if record is None:
                    record = MarketInstrumentRecord(instrument_key=key, last_seen_at=now)
                    new_records.append(record)
                    inserted += 1
                else:
                    updated += 1
                record.exchange = str(item["exchange"])
                record.segment = str(item["segment"])
                record.trading_symbol = str(item["trading_symbol"])
                record.short_name = item.get("short_name") if isinstance(item.get("short_name"), str) else None
                record.name = str(item["name"])
                record.isin = item.get("isin") if isinstance(item.get("isin"), str) else None
                record.instrument_type = str(item["instrument_type"])
                record.lot_size = Decimal(str(item["lot_size"])) if isinstance(item.get("lot_size"), (int, float)) else None
                record.tick_size = Decimal(str(item["tick_size"])) if isinstance(item.get("tick_size"), (int, float)) else None
                record.source = str(item.get("source") or "Upstox instrument master")[:80]
                catalogue_timestamp = item.get("catalogue_updated_at")
                record.catalogue_updated_at = _utc(catalogue_timestamp) if isinstance(catalogue_timestamp, str) else None
                record.last_seen_at = now
            session.add_all(new_records)
    return {"inserted_count": inserted, "updated_count": updated}


def get_instrument(instrument_key: str) -> dict[str, Any] | None:
    with Session(_engine()) as session:
        row = session.get(MarketInstrumentRecord, instrument_key)
        if row is None:
            return None
        return {
            "instrument_key": row.instrument_key, "exchange": row.exchange,
            "segment": row.segment, "trading_symbol": row.trading_symbol,
            "short_name": row.short_name, "name": row.name, "isin": row.isin, "instrument_type": row.instrument_type,
            "lot_size": float(row.lot_size) if row.lot_size is not None else None,
            "tick_size": float(row.tick_size) if row.tick_size is not None else None,
            "source": row.source,
            "catalogue_updated_at": row.catalogue_updated_at.isoformat() if row.catalogue_updated_at else None,
        }


def search_instruments(query: str, exchange: str = "ALL", limit: int = 100) -> list[dict[str, Any]]:
    pattern = f"%{query.strip()}%"
    with Session(_engine()) as session:
        statement = select(MarketInstrumentRecord).where(
            (MarketInstrumentRecord.trading_symbol.ilike(pattern)) |
            (MarketInstrumentRecord.name.ilike(pattern)) |
            (MarketInstrumentRecord.isin.ilike(pattern))
        )
        if exchange != "ALL":
            statement = statement.where(MarketInstrumentRecord.exchange == exchange)
        rows = session.scalars(statement.order_by(MarketInstrumentRecord.trading_symbol).limit(limit)).all()
        return [{
            "instrument_key": row.instrument_key, "exchange": row.exchange,
            "segment": row.segment, "trading_symbol": row.trading_symbol,
            "short_name": row.short_name, "name": row.name, "isin": row.isin, "instrument_type": row.instrument_type,
            "lot_size": float(row.lot_size) if row.lot_size is not None else None,
            "tick_size": float(row.tick_size) if row.tick_size is not None else None,
            "source": row.source,
            "catalogue_updated_at": row.catalogue_updated_at.isoformat() if row.catalogue_updated_at else None,
        } for row in rows]


def create_sync_run(
    *, instrument_key: str, unit: str, interval: int, from_date: date, to_date: date,
) -> int:
    with Session(_engine()) as session, session.begin():
        row = MarketHistorySyncRun(
            task_type="history", instrument_key=instrument_key, unit=unit, interval=interval,
            requested_from=from_date, requested_to=to_date, status="synchronizing",
            started_at=datetime.now(timezone.utc), fetched_count=0, inserted_count=0, updated_count=0,
        )
        session.add(row)
        session.flush()
        return row.id


def finish_sync_success(run_id: int, instrument: dict[str, Any], unit: str, interval: int, candles: list[dict[str, Any]]) -> dict[str, int]:
    """Atomically upsert all returned candles and mark their coverage successful."""
    now = datetime.now(timezone.utc)
    inserted = updated = 0
    with Session(_engine()) as session, session.begin():
        run = session.get(MarketHistorySyncRun, run_id)
        if run is None or run.status != "synchronizing":
            raise RuntimeError("Market synchronization run is not active")
        for offset in range(0, len(candles), 500):
            chunk = candles[offset : offset + 500]
            timestamps = [_utc(str(item["timestamp"])) for item in chunk]
            existing = session.scalars(select(MarketCandleRecord).where(
                MarketCandleRecord.instrument_key == str(instrument["instrument_key"]),
                MarketCandleRecord.unit == unit,
                MarketCandleRecord.interval == interval,
                MarketCandleRecord.candle_at.in_(timestamps),
            )).all()
            # SQLite drops timezone metadata; normalize ORM results before comparing
            # them with the provider timestamps, which are normalized to UTC above.
            by_timestamp = {_utc(row.candle_at): row for row in existing}
            new_records = []
            for item, timestamp in zip(chunk, timestamps):
                record = by_timestamp.get(timestamp)
                values = {
                    "exchange": str(instrument["exchange"]), "open": _decimal(item["open"], "open"),
                    "high": _decimal(item["high"], "high"), "low": _decimal(item["low"], "low"),
                    "close": _decimal(item["close"], "close"), "volume": _decimal(item["volume"], "volume"),
                    "open_interest": _decimal(item["open_interest"], "open_interest") if item.get("open_interest") is not None else None,
                    "source": str(item.get("source") or "Upstox historical")[:80],
                    "fetched_at": _utc(str(item.get("fetched_at") or now.isoformat())),
                    "quality_status": str(item.get("quality_status") or "provider_validated")[:24],
                }
                if record is None:
                    new_records.append(MarketCandleRecord(
                        instrument_key=str(instrument["instrument_key"]), unit=unit, interval=interval,
                        candle_at=timestamp, **values,
                    ))
                    inserted += 1
                else:
                    for field, value in values.items():
                        setattr(record, field, value)
                    updated += 1
            session.add_all(new_records)
        run.status = "synchronized" if candles else "partial"
        run.finished_at = now
        run.fetched_count = len(candles)
        run.inserted_count = inserted
        run.updated_count = updated
        run.error_category = None
    return {"inserted_count": inserted, "updated_count": updated, "fetched_count": len(candles)}


def finish_sync_failure(run_id: int, category: str) -> None:
    with Session(_engine()) as session, session.begin():
        row = session.get(MarketHistorySyncRun, run_id)
        if row is not None and row.status == "synchronizing":
            row.status = "failed"
            row.finished_at = datetime.now(timezone.utc)
            row.error_category = category[:80]


def successful_coverage(instrument_key: str, unit: str, interval: int) -> list[tuple[date, date]]:
    """Return durable old coverage and recent coverage within its refresh window."""
    now = datetime.now(timezone.utc)
    ist = timezone(timedelta(hours=5, minutes=30))
    recent_start = now.astimezone(ist).date() - timedelta(days=COVERAGE_REFRESH_DAYS)
    fresh_after = now - timedelta(minutes=COVERAGE_REFRESH_MINUTES)
    with Session(_engine()) as session:
        rows = session.scalars(select(MarketHistorySyncRun).where(
            MarketHistorySyncRun.instrument_key == instrument_key,
            MarketHistorySyncRun.unit == unit,
            MarketHistorySyncRun.interval == interval,
            MarketHistorySyncRun.status == "synchronized",
        )).all()
        coverage: list[tuple[date, date]] = []
        for row in rows:
            if not row.requested_from or not row.requested_to:
                continue
            if row.requested_to < recent_start or (row.finished_at and _utc(row.finished_at) >= fresh_after):
                coverage.append((row.requested_from, row.requested_to))
            elif row.requested_from < recent_start:
                # Keep old immutable history covered; refresh only the recent tail.
                coverage.append((row.requested_from, recent_start - timedelta(days=1)))
        return coverage


def list_candles(instrument_key: str, unit: str, interval: int, from_date: date, to_date: date) -> list[dict[str, Any]]:
    start = datetime.combine(from_date, datetime.min.time(), timezone.utc)
    end = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), timezone.utc)
    with Session(_engine()) as session:
        rows = session.scalars(select(MarketCandleRecord).where(
            MarketCandleRecord.instrument_key == instrument_key,
            MarketCandleRecord.unit == unit,
            MarketCandleRecord.interval == interval,
            MarketCandleRecord.candle_at >= start,
            MarketCandleRecord.candle_at < end,
        ).order_by(MarketCandleRecord.candle_at)).all()
        return [{
            "timestamp": _utc(row.candle_at).isoformat(), "open": float(row.open),
            "high": float(row.high), "low": float(row.low), "close": float(row.close),
            "volume": float(row.volume), "open_interest": float(row.open_interest) if row.open_interest is not None else None,
            "source": row.source, "fetched_at": _utc(row.fetched_at).isoformat(),
            "quality_status": row.quality_status,
        } for row in rows]


def history_status(instrument_key: str, unit: str, interval: int) -> dict[str, Any]:
    with Session(_engine()) as session:
        rows = session.scalars(select(MarketHistorySyncRun).where(
            MarketHistorySyncRun.instrument_key == instrument_key,
            MarketHistorySyncRun.unit == unit,
            MarketHistorySyncRun.interval == interval,
        ).order_by(MarketHistorySyncRun.id.desc()).limit(20)).all()
    latest_attempt = rows[0] if rows else None
    latest_success = next((row for row in rows if row.status == "synchronized"), None)
    return {
        "last_successful_sync_at": _utc(latest_success.finished_at).isoformat() if latest_success and latest_success.finished_at else None,
        "last_attempted_sync_at": _utc(latest_attempt.started_at).isoformat() if latest_attempt else None,
        "last_failure_category": next((row.error_category for row in rows if row.status == "failed"), None),
        "last_run_status": latest_attempt.status if latest_attempt else "never_synchronized",
    }


def global_history_summary() -> dict[str, Any]:
    with Session(_engine()) as session:
        instruments = session.scalar(select(func.count()).select_from(MarketInstrumentRecord)) or 0
        candle_count = session.scalar(select(func.count()).select_from(MarketCandleRecord)) or 0
        latest = session.scalar(select(func.max(MarketCandleRecord.candle_at)))
        earliest = session.scalar(select(func.min(MarketCandleRecord.candle_at)))
        latest_fetch = session.scalar(select(func.max(MarketCandleRecord.fetched_at)))
        intervals = session.execute(select(
            MarketCandleRecord.unit, MarketCandleRecord.interval, func.count()
        ).group_by(MarketCandleRecord.unit, MarketCandleRecord.interval)).all()
        history_runs = select(MarketHistorySyncRun).where(MarketHistorySyncRun.task_type == "history")
        last_attempt = session.scalars(history_runs.order_by(MarketHistorySyncRun.id.desc()).limit(1)).first()
        last_success = session.scalars(select(MarketHistorySyncRun).where(
            MarketHistorySyncRun.task_type == "history", MarketHistorySyncRun.status == "synchronized"
        ).order_by(MarketHistorySyncRun.id.desc()).limit(1)).first()
        catalogue_attempt = session.scalars(select(MarketHistorySyncRun).where(MarketHistorySyncRun.task_type == "catalogue").order_by(MarketHistorySyncRun.id.desc()).limit(1)).first()
    if last_attempt and last_attempt.status == "synchronizing":
        sync_status = "synchronizing"
    elif last_attempt and last_attempt.status == "partial":
        sync_status = "partially_synchronized"
    elif not last_success:
        sync_status = (
            "synchronization_failed" if last_attempt and last_attempt.status == "failed"
            else "initial_sync_pending" if instruments else "never_synchronized"
        )
    elif last_attempt and last_attempt.status == "failed":
        sync_status = "partially_synchronized"
    elif last_success and last_success.finished_at and (datetime.now(timezone.utc) - _utc(last_success.finished_at)).days > 7:
        sync_status = "stale"
    else:
        sync_status = "synchronized"
    return {
        "market_history_status": sync_status,
        "instruments_tracked": instruments,
        "candles_by_interval": {f"{unit}:{interval}": count for unit, interval, count in intervals},
        "candle_count": candle_count,
        "latest_stored_candle_at": _utc(latest).isoformat() if latest else None,
        "coverage_start": _utc(earliest).isoformat() if earliest else None,
        "coverage_end": _utc(latest).isoformat() if latest else None,
        "latest_upstream_fetch_at": _utc(latest_fetch).isoformat() if latest_fetch else None,
        "last_successful_sync_at": _utc(last_success.finished_at).isoformat() if last_success and last_success.finished_at else None,
        "last_attempted_sync_at": _utc(last_attempt.started_at).isoformat() if last_attempt else None,
        "last_failure_category": last_attempt.error_category if last_attempt and last_attempt.status == "failed" else None,
        "catalogue_sync_status": catalogue_attempt.status if catalogue_attempt else "never_synchronized",
        "catalogue_last_successful_sync_at": _utc(catalogue_attempt.finished_at).isoformat() if catalogue_attempt and catalogue_attempt.status == "synchronized" and catalogue_attempt.finished_at else None,
    }
