"""Deterministic calculations over provider-shaped candle series."""

from datetime import datetime, timedelta, timezone

from app.services.technical_analysis import calculate_technical_indicators


def _candles(count: int) -> list[dict]:
    return [{
        "timestamp": (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)).isoformat(),
        "open": 100 + index, "high": 102 + index, "low": 99 + index,
        "close": 101 + index, "volume": 1000,
    } for index in range(count)]


def test_indicator_calculation_withholds_metrics_without_sufficient_history():
    result = calculate_technical_indicators(_candles(10))
    assert result["status"] == "available"
    assert result["values"]["sma_10"] is not None
    assert result["values"]["sma_20"] is None
    assert result["values"]["ema_12"] is None
    assert result["values"]["rsi_14"] is None
    assert result["values"]["vwap_session"] is None


def test_indicator_calculation_uses_valid_candles_and_reports_periods():
    candles = _candles(220)
    candles.append({"timestamp": "2026-12-01", "close": float("nan"), "open": 1, "high": 1, "low": 1})
    result = calculate_technical_indicators(candles)
    assert result["status"] == "available"
    assert result["input_candle_count"] == 220
    assert result["values"]["sma_20"] is not None
    assert result["values"]["sma_50"] is not None
    assert result["values"]["sma_200"] is not None
    assert result["values"]["rsi_14"] == 100
    assert result["values"]["macd_signal"] is not None
    assert result["values"]["atr_14"] == 3
    assert result["values"]["adx_14"] == 100
    assert result["values"]["stochastic_k_14"] is not None
    assert result["values"]["obv"] == 219000


def test_flat_series_has_finite_neutral_indicators():
    candles = [{**candle, "open": 10, "high": 10, "low": 10, "close": 10} for candle in _candles(40)]
    result = calculate_technical_indicators(candles)
    assert result["values"]["rsi_14"] == 50
    assert result["values"]["bollinger_upper_20_2"] == 10
    assert result["values"]["bollinger_lower_20_2"] == 10
    assert all(value is None or __import__("math").isfinite(value) for value in result["values"].values())
