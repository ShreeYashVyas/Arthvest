"""Tests for macro history API behavior and input validation."""

from fastapi.testclient import TestClient

from app.api.routes import macro as macro_routes
from app.main import app
from app.services.macro_service import MacroDataError

client = TestClient(app)


def _history_payload(key: str, limit: int) -> dict[str, object]:
    return {
        "generated_at": "2026-10-23T09:00:00+00:00",
        "retrieved_at": "2026-10-23T08:59:00+00:00",
        "key": key,
        "indicator": "Indian Rupees per U.S. Dollar",
        "series_id": "DEXINUS",
        "unit": "INR per USD",
        "source": "Board of Governors of the Federal Reserve System via FRED",
        "source_url": "https://fred.stlouisfed.org/series/DEXINUS",
        "calculation": "Latest available spot exchange-rate observation.",
        "requested_limit": limit,
        "returned_count": 2,
        "points": [
            {"observation_date": "2026-10-15", "value": 95.06},
            {"observation_date": "2026-10-16", "value": 94.96},
        ],
    }


def test_history_route_returns_native_units_and_history(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_history(key: str, limit: int) -> dict[str, object]:
        calls.append((key, limit))
        return _history_payload(key, limit)

    monkeypatch.setattr(macro_routes, "fetch_macro_history", fake_history)

    response = client.get("/api/macro/history/usd-inr?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["key"] == "usd-inr"
    assert payload["unit"] == "INR per USD"
    assert payload["points"][-1]["value"] == 94.96
    assert calls == [("usd-inr", 2)]


def test_history_route_rejects_limits_above_sixty() -> None:
    response = client.get("/api/macro/history/usd-inr?limit=61")

    assert response.status_code == 422


def test_history_route_returns_not_found_for_unknown_indicator(monkeypatch) -> None:
    def fail(_key: str, limit: int) -> dict[str, object]:
        raise MacroDataError("Unsupported macro indicator: unknown")

    monkeypatch.setattr(macro_routes, "fetch_macro_history", fail)

    response = client.get("/api/macro/history/unknown")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unsupported macro indicator."
