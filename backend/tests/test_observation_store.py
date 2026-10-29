"""Tests for optional persistence, value revisions, and source-check tracking."""

from app.services import observation_store as store
from datetime import date, datetime, timezone
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError


def _points(september_value: float = 3.62) -> list[tuple[str, float]]:
    return [
        ("2026-08-01", 3.75),
        ("2026-09-01", september_value),
    ]


def test_storage_is_explicitly_disabled_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = store.get_storage_summary()

    assert result["enabled"] is False
    assert result["available"] is False
    assert result["backend"] == "disabled"
    assert result["observation_count"] == 0
    assert result["database_status"] == "configuration_missing"
    assert result["market_history_status"] == "initial_sync_pending"


def test_storage_status_reports_invalid_database_configuration_safely(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "not a valid sqlalchemy url")
    result = store.get_storage_summary()
    assert result["database_status"] == "configuration_invalid"
    assert result["available"] is False
    assert "not a valid sqlalchemy url" not in result["note"]


def test_storage_status_reports_unreachable_sqlite_location(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'missing-dir' / 'database.db'}")
    result = store.get_storage_summary()
    assert result["database_status"] == "disconnected"
    assert result["available"] is False


def test_storage_status_distinguishes_postgres_authentication_failure(monkeypatch) -> None:
    class PostgresAuthError(Exception):
        sqlstate = "28P01"

    class FailedEngine:
        @contextmanager
        def connect(self):
            raise OperationalError("connect", {}, PostgresAuthError())
            yield  # pragma: no cover

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://local@127.0.0.1/arthvest")
    monkeypatch.setattr(store, "_engine", lambda _url: FailedEngine())

    result = store.get_storage_summary()
    assert result["database_status"] == "authentication_failure"
    assert result["available"] is False
    assert "password" not in result["note"].lower()


def test_additive_alembic_baseline_preserves_existing_rows_and_is_repeatable(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'preexisting.db'}"
    engine = store._engine(url)
    store.MacroSourceObservation.__table__.create(engine)
    with Session(engine) as session, session.begin():
        session.add(store.MacroSourceObservation(
            series_id="PRESERVED", observation_date=date(2026, 10, 1), source_value=1.25,
            first_seen_at=datetime.now(timezone.utc), last_seen_at=datetime.now(timezone.utc),
            last_changed_at=datetime.now(timezone.utc),
        ))
    monkeypatch.setenv("DATABASE_URL", url)

    assert store.initialize_storage()
    assert store.initialize_storage()
    with Session(engine) as session:
        assert session.query(store.MacroSourceObservation).filter_by(series_id="PRESERVED").count() == 1
        assert session.get(store.ArthvestSchemaVersion, 1).version == store.SCHEMA_VERSION
    with engine.connect() as connection:
        revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
    assert revision == "0002_local_watchlists"


def test_archive_is_idempotent_and_detects_upstream_revisions(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'arthvest.db'}")
    assert store.initialize_storage() is True

    store.record_source_success(
        "fed-funds", "FEDFUNDS", _points(), "2026-10-23T10:00:00+00:00", 35
    )
    store.record_source_success(
        "fed-funds", "FEDFUNDS", _points(), "2026-10-23T10:15:00+00:00", 29
    )

    summary_before_revision = store.get_storage_summary()
    assert summary_before_revision["observation_count"] == 2
    assert summary_before_revision["revision_count"] == 0
    assert summary_before_revision["source_check_count"] == 2
    assert summary_before_revision["database_status"] == "connected"
    assert summary_before_revision["schema_status"] == "current"
    assert summary_before_revision["schema_version"] == store.SCHEMA_VERSION

    store.record_source_success(
        "fed-funds", "FEDFUNDS", _points(3.60), "2026-10-23T10:30:00+00:00", 42
    )

    summary = store.get_storage_summary()
    archive = store.list_archived_observations("FEDFUNDS", limit=10)
    revisions = store.list_revisions("FEDFUNDS", limit=10)

    assert summary["observation_count"] == 2
    assert summary["revision_count"] == 1
    assert summary["source_check_count"] == 3
    assert [point["observation_date"] for point in archive] == [
        "2026-08-01", "2026-09-01"
    ]
    assert archive[-1]["source_value"] == 3.60
    assert revisions[0]["observation_date"] == "2026-09-01"
    assert revisions[0]["previous_value"] == 3.62
    assert revisions[0]["revised_value"] == 3.60


def test_failed_fetch_is_recorded_without_erasing_archived_observations(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'source-checks.db'}")
    store.record_source_success(
        "fed-funds", "FEDFUNDS", _points(), "2026-10-23T10:00:00+00:00", 30
    )
    store.record_source_failure("fed-funds", "FEDFUNDS", "request-failed", 15000)

    checks = store.list_source_checks(limit=10)
    archive = store.list_archived_observations("FEDFUNDS", limit=10)

    assert checks[0]["status"] == "failure"
    assert checks[0]["error_code"] == "request-failed"
    assert checks[1]["status"] == "success"
    assert len(archive) == 2


def test_live_fred_fetch_is_archived_through_the_service_path(
    monkeypatch, tmp_path
) -> None:
    from app.services import macro_service

    series_id = "ARCHIVEINTEGRATIONTEST"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fetch-path.db'}")

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return (
                f"observation_date,{series_id}\n"
                "2026-08-01,3.2\n"
                "2026-09-01,3.1\n"
            ).encode("utf-8")

    def fake_urlopen(_request, timeout: int):
        assert timeout == macro_service.REQUEST_TIMEOUT_SECONDS
        return FakeResponse()

    monkeypatch.setattr(macro_service, "urlopen", fake_urlopen)
    with macro_service._cache_lock:
        macro_service._series_cache.pop(series_id, None)

    observations, retrieved_at = macro_service._fetch_fred_series(series_id)

    assert observations == [("2026-08-01", 3.2), ("2026-09-01", 3.1)]
    archived = store.list_archived_observations(series_id, limit=10)
    checks = store.list_source_checks(limit=10)
    assert [item["source_value"] for item in archived] == [3.2, 3.1]
    assert checks[0]["series_id"] == series_id
    assert checks[0]["status"] == "success"
    assert checks[0]["observation_count"] == 2
    assert checks[0]["latest_observation_date"] == "2026-09-01"
    assert retrieved_at
    with macro_service._cache_lock:
        macro_service._series_cache.pop(series_id, None)

