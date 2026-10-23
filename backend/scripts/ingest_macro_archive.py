"""Scheduled archive ingestion with explicit database-write verification."""

from __future__ import annotations

import os

from app.services.macro_service import INDICATORS, MacroDataError, fetch_macro_indicator
from app.services.observation_store import get_storage_summary


def main() -> int:
    """Fetch all configured indicators and verify persisted source-check records."""
    if not os.getenv("DATABASE_URL", "").strip():
        print("ERROR: DATABASE_URL is not configured. No source fetches were started.")
        return 2

    before = get_storage_summary()
    if not before.get("enabled") or not before.get("available"):
        print("ERROR: The configured observation database is not reachable.")
        print(before.get("note", "Storage readiness could not be confirmed."))
        return 2

    before_checks = before.get("source_check_count")
    successes = 0
    failures: list[str] = []
    attempted = 0

    for key in INDICATORS:
        attempted += 1
        try:
            result = fetch_macro_indicator(key)
        except MacroDataError:
            failures.append(key)
            print(f"FAILED {key}: upstream source unavailable or data failed validation")
            continue
        except Exception:
            failures.append(key)
            print(f"FAILED {key}: unexpected source-fetch error")
            continue

        successes += 1
        print(
            f"OK {key}: observation={result.get('observation_date', 'unknown')} "
            f"freshness={result.get('freshness_status', 'unknown')}"
        )

    after = get_storage_summary()
    if not after.get("enabled") or not after.get("available"):
        print("ERROR: The database became unavailable during ingestion.")
        print(after.get("note", "Storage readiness could not be confirmed."))
        return 2

    after_checks = after.get("source_check_count")
    if (
        not isinstance(before_checks, int)
        or not isinstance(after_checks, int)
        or after_checks - before_checks < attempted
    ):
        print(
            "ERROR: Source fetches were attempted, but the expected archive check "
            "records were not confirmed. Review database connectivity and service logs."
        )
        return 2

    print(
        "Archive verification: "
        f"observations={after.get('observation_count')} "
        f"revisions={after.get('revision_count')} "
        f"source_checks={after_checks} "
        f"new_checks={after_checks - before_checks}"
    )
    print(f"Source summary: {successes} succeeded, {len(failures)} failed, {attempted} attempted.")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
