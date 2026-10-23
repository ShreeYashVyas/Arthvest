"""Unit tests for the provisional U.S. macro conditions score."""

import pytest

from app.services.scoring_service import (
    SCORE_WEIGHTS,
    calculate_us_conditions_score,
)


def _indicator(value: float, freshness: str = "fresh") -> dict[str, object]:
    return {
        "value_percent": value,
        "observation_date": "2026-10-01",
        "freshness_status": freshness,
    }


def _complete_inputs() -> dict[str, dict[str, object] | None]:
    return {
        "fed-funds": _indicator(2.0),
        "us-inflation": _indicator(3.2),
        "us-unemployment": _indicator(5.0),
    }


def test_score_is_weighted_and_explainable() -> None:
    result = calculate_us_conditions_score(_complete_inputs())

    assert result["available"] is True
    assert result["provisional"] is True
    assert result["score"] == 67.0
    assert result["label"] == "mixed"
    assert sum(result["weights"].values()) == pytest.approx(1.0)
    assert sum(item["weighted_points"] for item in result["components"]) == pytest.approx(67.0)
    assert result["blockers"] == []


def test_score_is_withheld_when_an_input_is_stale() -> None:
    inputs = _complete_inputs()
    inputs["us-inflation"] = _indicator(3.2, freshness="stale")

    result = calculate_us_conditions_score(inputs)

    assert result["available"] is False
    assert result["score"] is None
    assert result["label"] == "insufficient-data"
    assert any("stale" in blocker for blocker in result["blockers"])


def test_score_is_withheld_when_an_input_is_missing() -> None:
    inputs = _complete_inputs()
    inputs["us-unemployment"] = None

    result = calculate_us_conditions_score(
        inputs,
        errors={"us-unemployment": "test source failure"},
    )

    assert result["available"] is False
    assert result["score"] is None
    component = next(
        item for item in result["components"] if item["key"] == "us-unemployment"
    )
    assert component["status"] == "unavailable"


def test_non_finite_input_is_not_scored() -> None:
    inputs = _complete_inputs()
    inputs["fed-funds"] = _indicator(float("nan"))

    result = calculate_us_conditions_score(inputs)

    assert result["available"] is False
    assert result["score"] is None
    assert any("invalid value" in blocker for blocker in result["blockers"])


def test_thresholds_are_deterministic() -> None:
    lower_rate = _complete_inputs()
    higher_rate = _complete_inputs()
    lower_rate["fed-funds"] = _indicator(3.5)
    higher_rate["fed-funds"] = _indicator(3.51)

    lower_result = calculate_us_conditions_score(lower_rate)
    higher_result = calculate_us_conditions_score(higher_rate)

    lower_component = next(
        item for item in lower_result["components"] if item["key"] == "fed-funds"
    )
    higher_component = next(
        item for item in higher_result["components"] if item["key"] == "fed-funds"
    )
    assert lower_component["component_score"] == 75.0
    assert higher_component["component_score"] == 60.0
