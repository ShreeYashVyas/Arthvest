"""Transparent, provisional scoring rules for U.S. macro conditions.

This is a research prototype, not a validated forecast or investment recommendation.
A result is withheld unless all required inputs are available and fresh.
"""

import math
from datetime import datetime, timezone
from typing import Any

SCORE_WEIGHTS: dict[str, float] = {
    "fed-funds": 0.25,
    "us-inflation": 0.45,
    "us-unemployment": 0.30,
}

SCORE_NAMES: dict[str, str] = {
    "fed-funds": "Federal Funds Effective Rate",
    "us-inflation": "U.S. CPI Inflation (year over year)",
    "us-unemployment": "U.S. Unemployment Rate",
}

SCORE_THRESHOLD_RULES: dict[str, list[str]] = {
    "fed-funds": [
        "value <= 2.00% -> score 85",
        "2.00% < value <= 3.50% -> score 75",
        "3.50% < value <= 4.50% -> score 60",
        "4.50% < value <= 5.50% -> score 40",
        "value > 5.50% -> score 20",
    ],
    "us-inflation": [
        "value <= 2.00% -> score 90",
        "2.00% < value <= 3.00% -> score 80",
        "3.00% < value <= 4.00% -> score 65",
        "4.00% < value <= 5.00% -> score 45",
        "value > 5.00% -> score 25",
    ],
    "us-unemployment": [
        "value <= 3.50% -> score 85",
        "3.50% < value <= 4.50% -> score 75",
        "4.50% < value <= 5.50% -> score 55",
        "5.50% < value <= 6.50% -> score 35",
        "value > 6.50% -> score 20",
    ],
}

METHODOLOGY = (
    "Provisional heuristic: convert each input into a 0–100 component score "
    "using fixed threshold bands, then calculate a weighted average. Higher "
    "scores indicate lower pressure under these specific rules; this is not a "
    "market return forecast. Thresholds have not been empirically calibrated."
)

LIMITATIONS = [
    "This is a U.S. macro conditions subscore, not the full Arthvest global/India macro regime score.",
    "Thresholds and weights are illustrative and have not been backtested or calibrated.",
    "The index uses three indicators and does not include Indian economic data, market pricing, geopolitical risk, or investor-specific circumstances.",
    "A score is withheld if any required observation is missing or stale.",
]


def _component_score(key: str, value: float) -> float:
    """Map raw values to a provisional score where higher is less restrictive."""
    if key == "fed-funds":
        if value <= 2.0:
            return 85.0
        if value <= 3.5:
            return 75.0
        if value <= 4.5:
            return 60.0
        if value <= 5.5:
            return 40.0
        return 20.0

    if key == "us-inflation":
        if value <= 2.0:
            return 90.0
        if value <= 3.0:
            return 80.0
        if value <= 4.0:
            return 65.0
        if value <= 5.0:
            return 45.0
        return 25.0

    if key == "us-unemployment":
        if value <= 3.5:
            return 85.0
        if value <= 4.5:
            return 75.0
        if value <= 5.5:
            return 55.0
        if value <= 6.5:
            return 35.0
        return 20.0

    raise ValueError(f"Unknown score component: {key}")


def calculate_us_conditions_score(
    inputs: dict[str, dict[str, Any] | None],
    errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Calculate a weighted score only when all three inputs are fresh and valid."""
    errors = errors or {}
    components: list[dict[str, Any]] = []
    blockers: list[str] = []

    for key, weight in SCORE_WEIGHTS.items():
        data = inputs.get(key)
        if data is None:
            blockers.append(f"{SCORE_NAMES[key]} is unavailable.")
            components.append(
                {
                    "key": key,
                    "indicator": SCORE_NAMES[key],
                    "status": "unavailable",
                    "value_percent": None,
                    "observation_date": None,
                    "freshness_status": None,
                    "component_score": None,
                    "weight": weight,
                    "weighted_points": None,
                }
            )
            continue

        try:
            value = float(data["value"])
        except (KeyError, TypeError, ValueError):
            value = math.nan

        if not math.isfinite(value):
            blockers.append(f"{SCORE_NAMES[key]} has an invalid value.")
            components.append(
                {
                    "key": key,
                    "indicator": SCORE_NAMES[key],
                    "status": "unavailable",
                    "value_percent": None,
                    "observation_date": data.get("observation_date"),
                    "freshness_status": data.get("freshness_status"),
                    "component_score": None,
                    "weight": weight,
                    "weighted_points": None,
                }
            )
            continue

        freshness = data.get("freshness_status")
        if freshness != "fresh":
            component_status = (
                "in-progress" if freshness == "in-progress" else "stale"
            )
            if freshness == "in-progress":
                blockers.append(
                    f"{SCORE_NAMES[key]} belongs to a period that has not ended yet."
                )
            else:
                blockers.append(
                    f"{SCORE_NAMES[key]} is stale or has unknown freshness."
                )
            components.append(
                {
                    "key": key,
                    "indicator": SCORE_NAMES[key],
                    "status": component_status,
                    "value_percent": value,
                    "observation_date": data.get("observation_date"),
                    "freshness_status": freshness,
                    "component_score": None,
                    "weight": weight,
                    "weighted_points": None,
                }
            )
            continue

        component = _component_score(key, value)
        components.append(
            {
                "key": key,
                "indicator": SCORE_NAMES[key],
                "status": "available",
                "value_percent": value,
                "observation_date": data.get("observation_date"),
                "freshness_status": freshness,
                "component_score": component,
                "weight": weight,
                "weighted_points": component * weight,
            }
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    if blockers:
        return {
            "generated_at": generated_at,
            "available": False,
            "score": None,
            "label": "insufficient-data",
            "provisional": True,
            "weights": SCORE_WEIGHTS,
            "threshold_rules": SCORE_THRESHOLD_RULES,
            "components": components,
            "methodology": METHODOLOGY,
            "limitations": LIMITATIONS,
            "blockers": blockers,
        }

    score = round(
        sum(float(component["weighted_points"]) for component in components),
        1,
    )
    label = "supportive" if score >= 70 else "mixed" if score >= 50 else "pressured"
    return {
        "generated_at": generated_at,
        "available": True,
        "score": score,
        "label": label,
        "provisional": True,
        "weights": SCORE_WEIGHTS,
        "threshold_rules": SCORE_THRESHOLD_RULES,
        "components": components,
        "methodology": METHODOLOGY,
        "limitations": LIMITATIONS,
        "blockers": [],
    }
