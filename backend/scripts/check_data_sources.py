"""Manually check live FRED source connectivity for all configured indicators.

Run from the backend directory with:
    python scripts/check_data_sources.py

This is intentionally not part of ordinary CI because it depends on live upstream data.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.services.macro_service import (
    INDICATORS,
    MacroDataError,
    fetch_macro_indicator,
)


def main() -> int:
    """Fetch each configured series, report its latest validated reading, and summarize failures."""
    results: dict[str, dict[str, str | float]] = {}
    failures: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=len(INDICATORS)) as executor:
        future_to_key = {
            executor.submit(fetch_macro_indicator, key): key for key in INDICATORS
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                results[key] = future.result()
            except MacroDataError as exc:
                failures[key] = str(exc)
            except Exception as exc:  # Keep checking other series after an unexpected failure.
                failures[key] = f"Unexpected error: {type(exc).__name__}"

    print(
        "Arthvest live FRED source check — "
        f"{datetime.now(timezone.utc).isoformat()}"
    )
    print("-" * 112)
    print(f"{'RESULT':<7} {'KEY':<29} {'SERIES':<18} {'OBSERVATION':<13} {'FRESHNESS':<12} VALUE")
    print("-" * 112)

    for key, config in INDICATORS.items():
        if key in failures:
            print(
                f"{'FAIL':<7} {key:<29} {config['series_id']:<18} "
                f"{'-':<13} {'unavailable':<12} {failures[key]}"
            )
            continue

        result = results[key]
        print(
            f"{'OK':<7} {key:<29} {config['series_id']:<18} "
            f"{str(result['observation_date']):<13} "
            f"{str(result['freshness_status']):<12} "
            f"{float(result['value']):.4g} {result['unit']}"
        )

    print("-" * 112)
    print(
        f"Validated {len(results)} of {len(INDICATORS)} configured sources; "
        f"{len(failures)} unavailable."
    )
    print(
        "Freshness states are reported separately from connectivity: a stale or "
        "in-progress reading is not automatically an unreachable source."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
