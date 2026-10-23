"""Tests for optional persistence, value revisions, and source-check tracking."""

from app.services import observation_store as store


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
