"""Technical indicators calculated only from validated historical candles.

EMA uses an SMA seed then exponential weighting; RSI and ATR use Wilder
smoothing; Bollinger bands use population standard deviation; stochastic %D is
the simple three-period mean of %K. All values use candles through the response
range's latest candle only. VWAP is withheld for daily data without intraday
session observations.
"""

from __future__ import annotations

import math
from statistics import pstdev
from typing import Any


def _ema(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    current = sum(values[:period]) / period
    output[period - 1] = current
    multiplier = 2 / (period + 1)
    for index in range(period, len(values)):
        current = (values[index] - current) * multiplier + current
        output[index] = current
    return output


def calculate_technical_indicators(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the latest common indicators, withholding values without enough candles."""
    valid: list[dict[str, Any]] = []
    for candle in candles:
        try:
            values = [float(candle[field]) for field in ("open", "high", "low", "close")]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(math.isfinite(value) for value in values):
            continue
        open_value, high, low, close = values
        if high < max(open_value, low, close) or low > min(open_value, close):
            continue
        volume = candle.get("volume")
        try:
            parsed_volume = float(volume) if volume is not None else None
        except (TypeError, ValueError):
            parsed_volume = None
        if parsed_volume is not None and (not math.isfinite(parsed_volume) or parsed_volume < 0):
            parsed_volume = None
        valid.append({"timestamp": candle.get("timestamp"), "high": high, "low": low, "close": close, "volume": parsed_volume})
    valid.sort(key=lambda item: str(item["timestamp"] or ""))
    closes = [item["close"] for item in valid]
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    metrics: dict[str, float | None] = {
        "sma_10": sum(closes[-10:]) / 10 if len(closes) >= 10 else None,
        "sma_20": sum(closes[-20:]) / 20 if len(closes) >= 20 else None,
        "sma_50": sum(closes[-50:]) / 50 if len(closes) >= 50 else None,
        "sma_100": sum(closes[-100:]) / 100 if len(closes) >= 100 else None,
        "sma_200": sum(closes[-200:]) / 200 if len(closes) >= 200 else None,
        "ema_9": _ema(closes, 9)[-1] if len(closes) >= 9 else None,
        "ema_12": ema_12[-1] if ema_12 else None,
        "ema_20": _ema(closes, 20)[-1] if len(closes) >= 20 else None,
        "ema_26": ema_26[-1] if ema_26 else None,
        "ema_50": _ema(closes, 50)[-1] if len(closes) >= 50 else None,
        "rsi_14": None,
        "macd": None,
        "macd_signal": None,
        "atr_14": None,
        "bollinger_middle_20": None,
        "bollinger_upper_20_2": None,
        "bollinger_lower_20_2": None,
        "stochastic_k_14": None,
        "stochastic_d_3": None,
        "roc_12_percent": None,
        "momentum_10": None,
        "obv": None,
        "adx_14": None,
        "vwap_session": None,
    }
    if len(closes) >= 20:
        window = closes[-20:]
        mean = sum(window) / 20
        deviation = pstdev(window)
        metrics["bollinger_middle_20"] = mean
        metrics["bollinger_upper_20_2"] = mean + 2 * deviation
        metrics["bollinger_lower_20_2"] = mean - 2 * deviation
    if len(closes) >= 15:
        changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
        gains = [max(change, 0.0) for change in changes]
        losses = [max(-change, 0.0) for change in changes]
        average_gain = sum(gains[:14]) / 14
        average_loss = sum(losses[:14]) / 14
        for gain, loss in zip(gains[14:], losses[14:]):
            average_gain = (average_gain * 13 + gain) / 14
            average_loss = (average_loss * 13 + loss) / 14
        metrics["rsi_14"] = (
            50.0 if average_gain == 0 and average_loss == 0
            else 100.0 if average_loss == 0
            else 100 - 100 / (1 + average_gain / average_loss)
        )
    macd_values = [a - b for a, b in zip(ema_12, ema_26) if a is not None and b is not None]
    if macd_values:
        metrics["macd"] = macd_values[-1]
        signal = _ema(macd_values, 9)
        metrics["macd_signal"] = signal[-1]
    if len(valid) >= 14:
        highs = [item["high"] for item in valid]
        lows = [item["low"] for item in valid]
        stochastic_values: list[float] = []
        for index in range(13, len(valid)):
            highest = max(highs[index - 13 : index + 1])
            lowest = min(lows[index - 13 : index + 1])
            stochastic_values.append(
                50.0 if highest == lowest else (closes[index] - lowest) / (highest - lowest) * 100
            )
        metrics["stochastic_k_14"] = stochastic_values[-1]
        if len(stochastic_values) >= 3:
            metrics["stochastic_d_3"] = sum(stochastic_values[-3:]) / 3
    if len(valid) >= 15:
        true_ranges = [max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ) for previous, current in zip(valid, valid[1:])]
        atr = sum(true_ranges[:14]) / 14
        for true_range in true_ranges[14:]:
            atr = (atr * 13 + true_range) / 14
        metrics["atr_14"] = atr
    if len(closes) >= 13:
        metrics["roc_12_percent"] = (closes[-1] / closes[-13] - 1) * 100 if closes[-13] else None
    if len(closes) >= 11:
        metrics["momentum_10"] = closes[-1] - closes[-11]
    if len(valid) >= 2 and all(item["volume"] is not None for item in valid):
        obv = 0.0
        for previous, current in zip(valid, valid[1:]):
            if current["close"] > previous["close"]:
                obv += float(current["volume"])
            elif current["close"] < previous["close"]:
                obv -= float(current["volume"])
        metrics["obv"] = obv
    metrics["adx_14"] = _adx(valid, 14)
    return {
        "status": "available" if any(value is not None for value in metrics.values()) else "insufficient_history",
        "input_candle_count": len(valid),
        "latest_candle_at": valid[-1]["timestamp"] if valid else None,
        "source": "Derived from validated historical OHLCV candles; daily-candle VWAP is unavailable",
        "values": {key: round(value, 6) if value is not None else None for key, value in metrics.items()},
        "periods": {
            "sma": [10, 20, 50, 100, 200], "ema": [9, 12, 20, 26, 50],
            "rsi": 14, "macd": [12, 26, 9], "bollinger": [20, 2],
            "atr": 14, "stochastic": [14, 3], "roc": 12, "momentum": 10, "adx": 14,
        },
    }


def _adx(candles: list[dict[str, Any]], period: int) -> float | None:
    """Wilder ADX, requiring two full periods; undefined flat direction returns 0."""
    if len(candles) <= period * 2:
        return None
    true_ranges: list[float] = []
    plus_moves: list[float] = []
    minus_moves: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        up = current["high"] - previous["high"]
        down = previous["low"] - current["low"]
        plus_moves.append(up if up > down and up > 0 else 0.0)
        minus_moves.append(down if down > up and down > 0 else 0.0)
        true_ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    smooth_tr = sum(true_ranges[:period])
    smooth_plus = sum(plus_moves[:period])
    smooth_minus = sum(minus_moves[:period])
    dx_values: list[float] = []
    for index in range(period - 1, len(true_ranges)):
        if index >= period:
            smooth_tr = smooth_tr - smooth_tr / period + true_ranges[index]
            smooth_plus = smooth_plus - smooth_plus / period + plus_moves[index]
            smooth_minus = smooth_minus - smooth_minus / period + minus_moves[index]
        if smooth_tr == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100 * smooth_plus / smooth_tr
        minus_di = 100 * smooth_minus / smooth_tr
        denominator = plus_di + minus_di
        dx_values.append(100 * abs(plus_di - minus_di) / denominator if denominator else 0.0)
    if len(dx_values) < period:
        return None
    adx = sum(dx_values[:period]) / period
    for dx in dx_values[period:]:
        adx = (adx * (period - 1) + dx) / period
    return adx
