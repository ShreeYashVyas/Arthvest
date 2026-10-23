"""Fetch and validate macroeconomic observations from FRED."""

import csv
import math
from datetime import datetime, timezone
from io import StringIO
from urllib.error import URLError
from urllib.request import Request, urlopen

FRED_FEDFUNDS_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=FEDFUNDS"
REQUEST_TIMEOUT_SECONDS = 15


class MacroDataError(RuntimeError):
    """Raised when upstream macro data is unavailable or invalid."""


def _parse_fed_funds_csv(csv_text: str) -> dict[str, str | float]:
    """Return the newest valid FEDFUNDS row from a FRED CSV response."""
    reader = csv.DictReader(StringIO(csv_text))
    if not reader.fieldnames or not {"observation_date", "FEDFUNDS"}.issubset(
        set(reader.fieldnames)
    ):
        raise MacroDataError("FRED response did not contain expected columns")

    valid_rows: list[tuple[datetime, str, float]] = []
    for row in reader:
        raw_date = (row.get("observation_date") or "").strip()
        raw_value = (row.get("FEDFUNDS") or "").strip()
        if not raw_date or raw_value in {"", "."}:
            continue

        try:
            observation_date = datetime.strptime(raw_date, "%Y-%m-%d")
            value = float(raw_value)
        except (ValueError, TypeError):
            continue

        if not math.isfinite(value):
            continue
        valid_rows.append((observation_date, raw_date, value))

    if not valid_rows:
        raise MacroDataError("FRED returned no valid Federal Funds Rate observations")

    _, date_string, value = max(valid_rows, key=lambda item: item[0])
    return {"observation_date": date_string, "value_percent": value}


def fetch_fed_funds_rate() -> dict[str, str | float]:
    """Fetch the latest available effective federal funds rate from FRED."""
    request = Request(
        FRED_FEDFUNDS_URL,
        headers={"User-Agent": "Arthvest/0.1 (macro research dashboard)"},
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise MacroDataError(f"FRED returned HTTP status {status}")
            csv_text = response.read().decode("utf-8-sig")
    except (URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
        raise MacroDataError("Unable to retrieve Federal Funds Rate data from FRED") from exc

    observation = _parse_fed_funds_csv(csv_text)
    return {
        "indicator": "Federal Funds Effective Rate",
        "series_id": "FEDFUNDS",
        "value_percent": observation["value_percent"],
        "observation_date": observation["observation_date"],
        "unit": "percent",
        "source": "Federal Reserve Bank of St. Louis (FRED)",
        "source_url": FRED_FEDFUNDS_URL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
