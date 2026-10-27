"""Contract tests for the optional Upstox market-data integration."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import upstox_service

client = TestClient(app)


def test_upstox_status_reports_missing_token_without_exposing_credentials(monkeypatch) -> None:
    monkeypatch.delenv("UPSTOX_ANALYTICS_TOKEN", raising=False)

    response = client.get("/api/market/upstox/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "Upstox"
    assert payload["configured"] is False
    assert payload["auth_mode"] is None
    assert "UPSTOX_ANALYTICS_TOKEN" in payload["note"]


def test_upstox_status_never_returns_token(monkeypatch) -> None:
    token = "example-private-token-not-for-real-use"
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", token)

    response = client.get("/api/market/upstox/status")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert token not in response.text


def test_upstox_quotes_require_token(monkeypatch) -> None:
    monkeypatch.delenv("UPSTOX_ANALYTICS_TOKEN", raising=False)

    response = client.get("/api/market/upstox/quotes")

    assert response.status_code == 503
    assert "UPSTOX_ANALYTICS_TOKEN" in response.json()["detail"]


def test_upstox_quotes_normalise_index_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", "test-token")
    payload = {
        "status": "success",
        "data": {
            "NSE_INDEX:Nifty 50": {
                "instrument_token": "NSE_INDEX|Nifty 50",
                "last_price": 22500.0,
                "net_change": 250.0,
                "ohlc": {"open": 22300.0, "high": 22600.0, "low": 22200.0, "close": 22250.0},
                "volume": 0,
                "timestamp": "2026-10-27T10:00:00+05:30",
            },
            "NSE_INDEX:Nifty Bank": {
                "instrument_token": "NSE_INDEX|Nifty Bank",
                "last_price": 51000.0,
                "net_change": -100.0,
                "ohlc": {"open": 51200.0, "high": 51300.0, "low": 50800.0, "close": 51100.0},
                "timestamp": "2026-10-27T10:00:00+05:30",
            },
        },
    }
    monkeypatch.setattr(upstox_service, "_request_quotes_payload", lambda token: payload)

    response = client.get("/api/market/upstox/quotes")

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "Upstox"
    assert result["read_only"] is True
    assert result["available_count"] == 2
    by_key = {item["key"]: item for item in result["quotes"]}
    assert by_key["nifty-50"]["status"] == "available"
    assert by_key["nifty-50"]["last_price"] == 22500.0
    assert by_key["nifty-50"]["previous_close"] == 22250.0
    assert by_key["nifty-50"]["change_percent"] == 1.1236
    assert by_key["nifty-bank"]["change"] == -100.0
    assert by_key["india-vix"]["status"] == "unavailable"
    assert by_key["india-vix"]["last_price"] is None


def test_upstox_quotes_do_not_echo_provider_credentials(monkeypatch) -> None:
    token = "another-example-private-token"
    monkeypatch.setenv("UPSTOX_ANALYTICS_TOKEN", token)
    payload = {
        "status": "success",
        "data": {
            "NSE_INDEX:Nifty 50": {
                "instrument_token": "NSE_INDEX|Nifty 50",
                "last_price": 100.0,
                "net_change": 0.0,
                "ohlc": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
            }
        },
    }
    monkeypatch.setattr(upstox_service, "_request_quotes_payload", lambda token_value: payload)

    response = client.get("/api/market/upstox/quotes")

    assert response.status_code == 200
    assert token not in response.text
