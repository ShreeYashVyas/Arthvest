"""Optional database-backed archive for source observations and fetch diagnostics."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    """Declarative base for persistence tables."""


class MacroSourceObservation(Base):
    """Current known value for a source observation date."""

    __tablename__ = "macro_source_observations"
    __table_args__ = (
        UniqueConstraint("series_id", "observation_date", name="uq_macro_series_date"),
        Index("ix_macro_observations_series_date", "series_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    series_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_value: Mapped[float] = mapped_column(Float, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MacroObservationRevision(Base):
    """Audit trail for values revised by the upstream source."""

    __tablename__ = "macro_observation_revisions"
    __table_args__ = (Index("ix_macro_revisions_series_date", "series_id", "observation_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    series_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    previous_value: Mapped[float] = mapped_column(Float, nullable=False)
    revised_value: Mapped[float] = mapped_column(Float, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MacroSourceCheck(Base):
    """One actual upstream fetch attempt, including a sanitized failure code."""

    __tablename__ = "macro_source_checks"
    __table_args__ = (Index("ix_macro_source_checks_series_time", "series_id", "checked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    series_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    observation_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_source_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class ArthvestSchemaVersion(Base):
    """Additive schema marker; existing data tables are never dropped or rewritten."""

    __tablename__ = "arthvest_schema_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


SCHEMA_VERSION = 2


class StorageDisabledError(RuntimeError):
    """Raised when persistence is requested without a configured database."""


_schema_lock = Lock()
_initialized_urls: set[str] = set()


def _database_url() -> str | None:
    """Read and normalize a database URL without ever returning it from an API."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def storage_is_configured() -> bool:
    """Return whether DATABASE_URL is present."""
    return _database_url() is not None


def _connection_failure(exc: Exception) -> tuple[str, str]:
    original = getattr(exc, "orig", exc)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if isinstance(sqlstate, str) and sqlstate.startswith("28"):
        return "authentication_failure", "Database connectivity: the configured database rejected authentication or authorization."
    return "disconnected", "Database connectivity: configured server could not be reached or authenticated."


@lru_cache(maxsize=8)
def _engine(url: str) -> Engine:
    """Cache database connection pools; allow SQLite to be shared by test threads."""
    options: dict[str, Any] = {"pool_pre_ping": True, "pool_timeout": 10}
    if url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 5}
    elif url.startswith(("postgresql:", "postgresql+psycopg:")):
        options["connect_args"] = {"connect_timeout": 5}
    return create_engine(url, **options)


def _ensure_schema(url: str) -> None:
    if url in _initialized_urls:
        return
    with _schema_lock:
        if url in _initialized_urls:
            return
        # Market models are imported lazily to avoid coupling macro startup to markets.
        from alembic import command
        from alembic.config import Config
        from app.services import market_store  # noqa: F401

        engine = _engine(url)
        if inspect(engine).has_table(ArthvestSchemaVersion.__tablename__):
            with Session(engine) as session:
                current_version = session.scalar(
                    select(ArthvestSchemaVersion.version).where(ArthvestSchemaVersion.id == 1)
                )
            if current_version is not None and current_version > SCHEMA_VERSION:
                raise RuntimeError("Database schema version is newer than this application supports")
        project_root = Path(__file__).resolve().parents[2]
        migration_config = Config(str(project_root / "alembic.ini"))
        with engine.begin() as connection:
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")
        with Session(engine) as session, session.begin():
            marker = session.get(ArthvestSchemaVersion, 1)
            if marker is None:
                session.add(ArthvestSchemaVersion(id=1, version=SCHEMA_VERSION, updated_at=datetime.now(timezone.utc)))
            elif marker.version < SCHEMA_VERSION:
                marker.version = SCHEMA_VERSION
                marker.updated_at = datetime.now(timezone.utc)
        _initialized_urls.add(url)


def initialize_storage() -> bool:
    """Create the initial tables if storage is configured."""
    url = _database_url()
    if url is None:
        return False
    _ensure_schema(url)
    return True


def _timestamp(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_source_success(
    indicator_key: str | None,
    series_id: str,
    observations: Iterable[tuple[str, float]],
    retrieved_at: str,
    elapsed_ms: int,
) -> bool:
    """Save raw source values, revisions, and a successful check atomically.

    Values are source-native. CPIAUCSL is archived as the CPI index, not derived
    year-over-year inflation. Re-fetching unchanged data updates last_seen_at only.
    """
    url = _database_url()
    if url is None:
        return False
    _ensure_schema(url)
    checked_at = _timestamp(retrieved_at)
    points = [(date.fromisoformat(day), float(value)) for day, value in observations]
    if not points:
        raise ValueError("Successful source check must contain observations")

    with Session(_engine(url)) as session, session.begin():
        rows = session.scalars(
            select(MacroSourceObservation).where(MacroSourceObservation.series_id == series_id)
        ).all()
        by_date = {row.observation_date: row for row in rows}
        for observation_date, value in points:
            row = by_date.get(observation_date)
            if row is None:
                session.add(MacroSourceObservation(
                    indicator_key=indicator_key,
                    series_id=series_id,
                    observation_date=observation_date,
                    source_value=value,
                    first_seen_at=checked_at,
                    last_seen_at=checked_at,
                    last_changed_at=checked_at,
                ))
                continue
            row.indicator_key = indicator_key
            row.last_seen_at = checked_at
            if row.source_value != value:
                session.add(MacroObservationRevision(
                    indicator_key=indicator_key,
                    series_id=series_id,
                    observation_date=observation_date,
                    previous_value=row.source_value,
                    revised_value=value,
                    detected_at=checked_at,
                    retrieved_at=checked_at,
                ))
                row.source_value = value
                row.last_changed_at = checked_at

        latest_date, latest_value = points[-1]
        session.add(MacroSourceCheck(
            indicator_key=indicator_key,
            series_id=series_id,
            checked_at=checked_at,
            status="success",
            observation_count=len(points),
            latest_observation_date=latest_date,
            latest_source_value=latest_value,
            elapsed_ms=max(int(elapsed_ms), 0),
            error_code=None,
        ))
    return True


def record_source_failure(
    indicator_key: str | None, series_id: str, error_code: str, elapsed_ms: int
) -> bool:
    """Record a failed upstream check without persisting raw exception text."""
    url = _database_url()
    if url is None:
        return False
    _ensure_schema(url)
    with Session(_engine(url)) as session, session.begin():
        session.add(MacroSourceCheck(
            indicator_key=indicator_key,
            series_id=series_id,
            checked_at=datetime.now(timezone.utc),
            status="failure",
            observation_count=None,
            latest_observation_date=None,
            latest_source_value=None,
            elapsed_ms=max(int(elapsed_ms), 0),
            error_code=error_code[:80],
        ))
    return True


def get_storage_summary() -> dict[str, Any]:
    """Return readiness and record counts without exposing the configured URL."""
    url = _database_url()
    if url is None:
        return {
            "enabled": False, "available": False, "backend": "disabled",
            "database_status": "configuration_missing", "schema_status": "not_checked",
            "schema_version": None,
            "observation_count": 0, "revision_count": 0, "source_check_count": 0,
            "last_check_at": None,
            "market_history_status": "initial_sync_pending", "instruments_tracked": 0,
            "candles_by_interval": {}, "candle_count": 0,
            "latest_stored_candle_at": None, "last_successful_sync_at": None,
            "last_attempted_sync_at": None, "last_failure_category": None,
            "coverage_start": None, "coverage_end": None, "latest_upstream_fetch_at": None,
            "catalogue_sync_status": "never_synchronized", "catalogue_last_successful_sync_at": None,
            "note": "Database connectivity: configuration missing. Set DATABASE_URL to enable persistent archives and market history.",
        }
    backend = url.split("://", 1)[0].split("+", 1)[0]
    try:
        make_url(url)
        engine = _engine(url)
    except (ArgumentError, ValueError):
        return {
            "enabled": True, "available": False, "backend": backend,
            "database_status": "configuration_invalid", "schema_status": "not_checked",
            "schema_version": None, "observation_count": None, "revision_count": None,
            "source_check_count": None, "last_check_at": None,
            "market_history_status": "initial_sync_pending", "instruments_tracked": None,
            "candles_by_interval": {}, "candle_count": None,
            "latest_stored_candle_at": None, "last_successful_sync_at": None,
            "last_attempted_sync_at": None, "last_failure_category": None,
            "coverage_start": None, "coverage_end": None, "latest_upstream_fetch_at": None,
            "catalogue_sync_status": "never_synchronized", "catalogue_last_successful_sync_at": None,
            "note": "Database connectivity: DATABASE_URL is invalid. Check its scheme and required connection fields.",
        }
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        database_status, note = _connection_failure(exc)
        return {
            "enabled": True, "available": False, "backend": backend,
            "database_status": database_status, "schema_status": "not_checked",
            "schema_version": None, "observation_count": None, "revision_count": None,
            "source_check_count": None, "last_check_at": None,
            "market_history_status": "initial_sync_pending", "instruments_tracked": None,
            "candles_by_interval": {}, "candle_count": None,
            "latest_stored_candle_at": None, "last_successful_sync_at": None,
            "last_attempted_sync_at": None, "last_failure_category": None,
            "coverage_start": None, "coverage_end": None, "latest_upstream_fetch_at": None,
            "catalogue_sync_status": "never_synchronized", "catalogue_last_successful_sync_at": None,
            "note": note,
        }
    except Exception:
        return {
            "enabled": True, "available": False, "backend": backend,
            "database_status": "configuration_invalid", "schema_status": "not_checked",
            "schema_version": None, "observation_count": None, "revision_count": None,
            "source_check_count": None, "last_check_at": None,
            "market_history_status": "initial_sync_pending", "instruments_tracked": None,
            "candles_by_interval": {}, "candle_count": None,
            "latest_stored_candle_at": None, "last_successful_sync_at": None,
            "last_attempted_sync_at": None, "last_failure_category": None,
            "coverage_start": None, "coverage_end": None, "latest_upstream_fetch_at": None,
            "catalogue_sync_status": "never_synchronized", "catalogue_last_successful_sync_at": None,
            "note": "Database connectivity: configuration could not be validated.",
        }
    try:
        _ensure_schema(url)
        with Session(_engine(url)) as session:
            observations = session.scalar(select(func.count()).select_from(MacroSourceObservation)) or 0
            revisions = session.scalar(select(func.count()).select_from(MacroObservationRevision)) or 0
            checks = session.scalar(select(func.count()).select_from(MacroSourceCheck)) or 0
            last = session.scalar(
                select(MacroSourceCheck.checked_at).order_by(MacroSourceCheck.id.desc()).limit(1)
            )
            schema_version = session.scalar(select(ArthvestSchemaVersion.version).where(ArthvestSchemaVersion.id == 1))
        from app.services import market_store
        market_summary = market_store.global_history_summary()
        return {
            "enabled": True, "available": True, "backend": backend,
            "database_status": "connected", "schema_status": "current",
            "schema_version": schema_version,
            "observation_count": observations, "revision_count": revisions,
            "source_check_count": checks, "last_check_at": last.isoformat() if last else None,
            **market_summary,
            "note": "Database connectivity: connected; schema is current. Market-history synchronization is reported separately.",
        }
    except Exception:
        return {
            "enabled": True, "available": False, "backend": backend,
            "database_status": "schema_error", "schema_status": "error",
            "schema_version": None, "observation_count": None, "revision_count": None,
            "source_check_count": None, "last_check_at": None,
            "market_history_status": "initial_sync_pending", "instruments_tracked": None,
            "candles_by_interval": {}, "candle_count": None,
            "latest_stored_candle_at": None, "last_successful_sync_at": None,
            "last_attempted_sync_at": None, "last_failure_category": None,
            "coverage_start": None, "coverage_end": None, "latest_upstream_fetch_at": None,
            "catalogue_sync_status": "never_synchronized", "catalogue_last_successful_sync_at": None,
            "note": "Database is reachable, but the Arthvest schema could not be initialized or queried.",
        }


def list_archived_observations(series_id: str, limit: int = 12) -> list[dict[str, Any]]:
    """Return latest current-known observations in chronological order."""
    if not 1 <= limit <= 10000:
        raise ValueError("Archive limit must be between 1 and 10000")
    url = _database_url()
    if url is None:
        raise StorageDisabledError("DATABASE_URL is not configured")
    _ensure_schema(url)
    with Session(_engine(url)) as session:
        rows = session.scalars(
            select(MacroSourceObservation)
            .where(MacroSourceObservation.series_id == series_id)
            .order_by(MacroSourceObservation.observation_date.desc())
            .limit(limit)
        ).all()
        return [{
            "observation_date": row.observation_date.isoformat(),
            "source_value": row.source_value,
            "first_seen_at": row.first_seen_at.isoformat(),
            "last_seen_at": row.last_seen_at.isoformat(),
            "last_changed_at": row.last_changed_at.isoformat(),
        } for row in reversed(rows)]


def list_revisions(series_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return revisions newest-first."""
    if not 1 <= limit <= 100:
        raise ValueError("Revision limit must be between 1 and 100")
    url = _database_url()
    if url is None:
        raise StorageDisabledError("DATABASE_URL is not configured")
    _ensure_schema(url)
    with Session(_engine(url)) as session:
        rows = session.scalars(
            select(MacroObservationRevision)
            .where(MacroObservationRevision.series_id == series_id)
            .order_by(MacroObservationRevision.detected_at.desc(), MacroObservationRevision.id.desc())
            .limit(limit)
        ).all()
        return [{
            "series_id": row.series_id,
            "observation_date": row.observation_date.isoformat(),
            "previous_value": row.previous_value,
            "revised_value": row.revised_value,
            "detected_at": row.detected_at.isoformat(),
            "retrieved_at": row.retrieved_at.isoformat(),
        } for row in rows]


def list_source_checks(limit: int = 24) -> list[dict[str, Any]]:
    """Return recent success/failure checks newest-first."""
    if not 1 <= limit <= 100:
        raise ValueError("Source-check limit must be between 1 and 100")
    url = _database_url()
    if url is None:
        raise StorageDisabledError("DATABASE_URL is not configured")
    _ensure_schema(url)
    with Session(_engine(url)) as session:
        rows = session.scalars(
            select(MacroSourceCheck)
            .order_by(MacroSourceCheck.checked_at.desc(), MacroSourceCheck.id.desc())
            .limit(limit)
        ).all()
        return [{
            "indicator_key": row.indicator_key,
            "series_id": row.series_id,
            "checked_at": row.checked_at.isoformat(),
            "status": row.status,
            "observation_count": row.observation_count,
            "latest_observation_date": row.latest_observation_date.isoformat()
            if row.latest_observation_date else None,
            "latest_source_value": row.latest_source_value,
            "elapsed_ms": row.elapsed_ms,
            "error_code": row.error_code,
        } for row in rows]
