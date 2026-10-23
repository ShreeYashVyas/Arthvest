"""Unit tests for the scheduled macro archive ingestion command."""

from app.services import macro_service
from scripts import ingest_macro_archive as ingest


def _summary(*, available=True, checks=10):
    return {
        "enabled": True,
        "available": available,
        "backend": "sqlite",
        "observation_count": 100,
        "revision_count": 2,
        "source_check_count": checks,
        "last_check_at": "2026-10-23T10:00:00+00:00",
        "note": "test storage",
    }


def test_ingestion_requires_database_url(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = ingest.main()

    assert result == 2
    assert "DATABASE_URL is not configured" in capsys.readouterr().out


def test_ingestion_stops_before_fetching_when_database_is_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(ingest, "get_storage_summary", lambda: _summary(available=False))
    fetches = []
    monkeypatch.setattr(ingest, "fetch_macro_indicator", lambda key: fetches.append(key))

    assert ingest.main() == 2
    assert fetches == []


def test_ingestion_fetches_all_indicators_and_verifies_archive_writes(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(ingest, "INDICATORS", {"fed-funds": {}, "us-unemployment": {}})
    summaries = iter([_summary(checks=10), _summary(checks=12)])
    monkeypatch.setattr(ingest, "get_storage_summary", lambda: next(summaries))
    calls = []
    monkeypatch.setattr(
        ingest,
        "fetch_macro_indicator",
        lambda key: calls.append(key) or {
            "observation_date": "2026-09-01",
            "freshness_status": "fresh",
        },
    )

    result = ingest.main()

    assert result == 0
    assert calls == ["fed-funds", "us-unemployment"]
    output = capsys.readouterr().out
    assert "new_checks=2" in output
    assert "2 succeeded, 0 failed, 2 attempted" in output


def test_ingestion_fails_when_archive_check_count_does_not_advance(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(ingest, "INDICATORS", {"fed-funds": {}, "us-unemployment": {}})
    summaries = iter([_summary(checks=10), _summary(checks=11)])
    monkeypatch.setattr(ingest, "get_storage_summary", lambda: next(summaries))
    monkeypatch.setattr(
        ingest,
        "fetch_macro_indicator",
        lambda _key: {"observation_date": "2026-09-01", "freshness_status": "fresh"},
    )

    result = ingest.main()

    assert result == 2
    assert "expected archive check records were not confirmed" in capsys.readouterr().out


def test_ingestion_reports_partial_source_failure_after_recording_attempts(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
    monkeypatch.setattr(ingest, "INDICATORS", {"fed-funds": {}, "us-unemployment": {}})
    summaries = iter([_summary(checks=10), _summary(checks=12)])
    monkeypatch.setattr(ingest, "get_storage_summary", lambda: next(summaries))

    def fetch(key):
        if key == "us-unemployment":
            raise macro_service.MacroDataError("simulated upstream error")
        return {"observation_date": "2026-09-01", "freshness_status": "fresh"}

    monkeypatch.setattr(ingest, "fetch_macro_indicator", fetch)

    assert ingest.main() == 1
    assert "1 succeeded, 1 failed, 2 attempted" in capsys.readouterr().out
