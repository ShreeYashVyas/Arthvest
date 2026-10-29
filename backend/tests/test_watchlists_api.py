"""Database-backed watchlist API tests using an isolated SQLite test database."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import instrument_catalog


client = TestClient(app)


def _instrument(key: str, exchange: str) -> dict:
    return {
        "instrument_key": key, "exchange": exchange, "segment": f"{exchange}_EQ",
        "trading_symbol": "ACME", "name": "Acme Limited", "short_name": None,
        "isin": None, "instrument_type": "EQ", "lot_size": 1, "tick_size": 0.05,
        "source": "Upstox instrument master", "catalogue_updated_at": None,
    }


@pytest.fixture
def configured_store(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'watchlists.db'}")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(instrument_catalog, "get_instrument", lambda key: _instrument(
        key, "NSE" if key.startswith("NSE_EQ") else "BSE"
    ))


def test_watchlist_crud_persists_ordered_exchange_specific_entries(configured_store):
    first = client.post("/api/watchlists", json={"name": "Core"})
    second = client.post("/api/watchlists", json={"name": "Long term"})
    assert first.status_code == second.status_code == 201
    watchlist_id = first.json()["id"]

    updated = client.put(f"/api/watchlists/{watchlist_id}/entries", json={
        "instrument_keys": ["BSE_EQ|INE123A01001", "NSE_EQ|INE123A01001"]
    })
    assert updated.status_code == 200
    assert [entry["exchange"] for entry in updated.json()["instruments"]] == ["BSE", "NSE"]

    listed = client.get("/api/watchlists")
    assert listed.status_code == 200
    assert len(listed.json()["watchlists"]) == 2
    assert [entry["exchange"] for entry in listed.json()["watchlists"][0]["instruments"]] == ["BSE", "NSE"]

    renamed = client.patch(f"/api/watchlists/{watchlist_id}", json={"name": "Core Portfolio"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Core Portfolio"
    assert client.delete(f"/api/watchlists/{watchlist_id}").status_code == 204
    assert client.get("/api/watchlists").json()["watchlists"][0]["id"] == second.json()["id"]


@pytest.mark.parametrize("keys", [
    ["NSE_EQ|INE123A01001", "NSE_EQ|INE123A01001"],
    ["NSE_INDEX|Nifty 50"],
])
def test_watchlist_rejects_duplicate_or_unsupported_instrument_keys(configured_store, keys):
    created = client.post("/api/watchlists", json={"name": "Core"})
    response = client.put(f"/api/watchlists/{created.json()['id']}/entries", json={"instrument_keys": keys})
    assert response.status_code == 422


def test_watchlist_is_explicitly_unavailable_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    response = client.get("/api/watchlists")
    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]


def test_watchlist_is_disabled_outside_single_user_development_mode(configured_store, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert client.get("/api/watchlists").status_code == 403
