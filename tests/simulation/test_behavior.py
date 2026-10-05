from __future__ import annotations

import pytest

from evolution_sim.simulation.behavior import (
    ActionName,
    BehaviorDecision,
    BehaviorPerception,
    BehaviorState,
    InstinctVector,
)


@pytest.mark.parametrize(
    "values",
    [(), (0.0,) * 5, (0.0,) * 7, (float("nan"),) * 6, (float("inf"),) * 6, (-0.1,) * 6, (1.1,) * 6],
)
def test_instinct_vector_rejects_invalid_drives(values: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="drives"):
        InstinctVector(values)


def test_instinct_vector_owns_immutable_values_in_named_order() -> None:
    source = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    drives = InstinctVector(source)
    source[0] = 1.0
    assert drives.values == (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
    assert drives.to_dict() == {
        "survival": 0.1,
        "foraging": 0.2,
        "mating": 0.3,
        "offspring_care": 0.4,
        "danger_avoidance": 0.5,
        "territory": 0.6,
    }


def test_default_state_and_perception_are_safe() -> None:
    state = BehaviorState()
    assert state.action is ActionName.EXPLORE
    assert state.drives.values == (0.0,) * 6
    assert state.target_id is None
    perception = BehaviorPerception(food=[])
    assert perception.food == ()
    assert perception.threats == perception.eligible_mates == perception.dependent_offspring == ()


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf")])
def test_decision_rejects_invalid_scores(value: float) -> None:
    with pytest.raises(ValueError, match="scores"):
        BehaviorDecision(BehaviorState(), {ActionName.REST: value})


def test_decision_copies_scores_and_state_copies_utility_breakdown() -> None:
    source = {ActionName.EXPLORE: 0.2}
    state = BehaviorState(utility_breakdown=source)
    decision = BehaviorDecision(state, source)
    source[ActionName.EXPLORE] = 0.9
    assert decision.scores[ActionName.EXPLORE] == 0.2
    assert state.utility_breakdown[ActionName.EXPLORE] == 0.2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"started_tick": -1},
        {"target_id": -1},
        {"target_position": (1.0, float("nan"))},
        {"target_position": (1.0,)},
    ],
)
def test_state_rejects_corrupt_targets_and_ticks(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        BehaviorState(**kwargs)
