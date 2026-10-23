"""Unit tests for the provisional U.S. macro conditions score."""

import pytest

from app.services.scoring_service import (
    _component_score,
    calculate_us_conditions_score,
)


def _indicator(value: float, freshness: str = "fresh") -> dict[str, object]:
    return {
        "value": value,
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
    assert result["threshold_rules"]["fed-funds"][0] == "value <= 2.00% -> score 85"
    assert len(result["threshold_rules"]["us-inflation"]) == 5
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
    assert any("test source failure" in blocker for blocker in result["blockers"])


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


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("fed-funds", 2.00, 85.0),
        ("fed-funds", 2.01, 75.0),
        ("fed-funds", 3.50, 75.0),
        ("fed-funds", 3.51, 60.0),
        ("fed-funds", 4.50, 60.0),
        ("fed-funds", 4.51, 40.0),
        ("fed-funds", 5.50, 40.0),
        ("fed-funds", 5.51, 20.0),
        ("us-inflation", 2.00, 90.0),
        ("us-inflation", 2.01, 80.0),
        ("us-inflation", 3.00, 80.0),
        ("us-inflation", 3.01, 65.0),
        ("us-inflation", 4.00, 65.0),
        ("us-inflation", 4.01, 45.0),
        ("us-inflation", 5.00, 45.0),
        ("us-inflation", 5.01, 25.0),
        ("us-unemployment", 3.50, 85.0),
        ("us-unemployment", 3.51, 75.0),
        ("us-unemployment", 4.50, 75.0),
        ("us-unemployment", 4.51, 55.0),
        ("us-unemployment", 5.50, 55.0),
        ("us-unemployment", 5.51, 35.0),
        ("us-unemployment", 6.50, 35.0),
        ("us-unemployment", 6.51, 20.0),
    ],
)
def test_all_scoring_threshold_boundaries(
    key: str,
    value: float,
    expected: float,
) -> None:
    assert _component_score(key, value) == expected



def test_score_is_withheld_when_an_input_period_is_in_progress() -> None:
    inputs = _complete_inputs()
    inputs["fed-funds"] = _indicator(4.0, freshness="in-progress")

    result = calculate_us_conditions_score(inputs)

    assert result["available"] is False
    assert result["score"] is None
    assert any("period that has not ended" in blocker for blocker in result["blockers"])
    component = next(
        item for item in result["components"] if item["key"] == "fed-funds"
    )
    assert component["status"] == "in-progress"
    assert component["component_score"] is None
