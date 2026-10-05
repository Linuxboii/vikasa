from __future__ import annotations

import numpy as np
import pytest

from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genome import Genome
from evolution_sim.model.temperament import Temperament
from evolution_sim.simulation import behavior
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


@pytest.mark.parametrize("coordinate", [True, False, "1.0", None, {}, [], complex(1, 2)])
def test_state_rejects_malformed_target_coordinate_types(coordinate: object) -> None:
    with pytest.raises(ValueError, match="target_position"):
        BehaviorState(target_position=(1.0, coordinate))


def animal(config, entity_id=1, position=(50.0, 50.0), energy=220.0, **kwargs):
    genome = Genome.from_mapping(
        {
            name: (bounds.minimum + bounds.maximum) / 2
            for name, bounds in config.genome.traits.items()
        },
        config.genome,
    )
    return Creature(entity_id, np.array(position), np.zeros(2), 300, energy, genome, **kwargs)


@pytest.mark.parametrize(
    "energy,injury,expected",
    [
        (220.0, 0.0, 0.0),
        (110.0, 0.0, 0.325),
        (0.0, 0.0, 0.65),
        (110.0, 1.0, 0.675),
        (-220.0, 1.0, 1.0),
    ],
)
def test_survival_uses_energy_reserve_and_injury(tiny_config, energy, injury, expected):
    creature = animal(tiny_config, energy=energy, injury=injury)
    drives = behavior.BehaviorController(tiny_config).drives(creature, BehaviorPerception(), 220.0)
    assert drives.to_dict()["survival"] == pytest.approx(expected)


def test_absent_candidates_suppress_invalid_actions_even_when_current(tiny_config):
    creature = animal(tiny_config, behavior_state=BehaviorState(action=ActionName.SEEK_MATE))
    decision = behavior.BehaviorController(tiny_config).decide(
        creature, BehaviorPerception(), 220.0, 10, np.random.default_rng(7)
    )
    for action in (
        ActionName.FORAGE,
        ActionName.SEEK_MATE,
        ActionName.CARE,
        ActionName.CHALLENGE,
        ActionName.FLEE,
    ):
        assert action not in decision.scores
    assert decision.state.action != ActionName.SEEK_MATE
    assert decision.state.drives.to_dict()["mating"] == 0.0
    assert decision.state.drives.to_dict()["offspring_care"] == 0.0
    assert all(0.0 <= value <= 1.0 for value in decision.scores.values())


@pytest.mark.parametrize("current", list(ActionName))
def test_maximum_danger_preempts_every_action(tiny_config, current):
    creature = animal(
        tiny_config, energy=10.0, behavior_state=BehaviorState(action=current, started_tick=2)
    )
    decision = behavior.BehaviorController(tiny_config).decide(
        creature, BehaviorPerception(local_hazard=1.0), 220.0, 10, np.random.default_rng(7)
    )
    assert decision.state.action is ActionName.FLEE
    assert decision.state.drives.to_dict()["danger_avoidance"] == 1.0
    assert decision.state.reason


def test_survival_suppresses_mating_despite_low_reproduction_threshold(tiny_config):
    creature = animal(tiny_config, energy=120.0, injury=0.8)
    mate = animal(tiny_config, entity_id=2, position=(52.0, 50.0))
    decision = behavior.BehaviorController(tiny_config).decide(
        creature, BehaviorPerception(eligible_mates=(mate,)), 220.0, 10, np.random.default_rng(7)
    )
    assert ActionName.SEEK_MATE not in decision.scores
    assert decision.state.action is ActionName.REST


def test_care_selects_nearest_living_dependent_in_radius(tiny_config):
    parent = animal(tiny_config, temperament=Temperament(sociability=1.0))
    children = [
        animal(tiny_config, entity_id=i, position=(x, 50.0), energy=10.0, parents=(1, 99))
        for i, x in [(2, 52.0), (3, 58.0), (4, 80.0)]
    ]
    for child in children:
        child.age = 5
    dead = animal(tiny_config, entity_id=5, position=(51.0, 50.0), parents=(1, 99), alive=False)
    dead.age = 1
    unrelated = animal(tiny_config, entity_id=6, position=(50.5, 50.0))
    unrelated.age = 1
    decision = behavior.BehaviorController(tiny_config).decide(
        parent,
        BehaviorPerception(dependent_offspring=(*children, dead, unrelated)),
        220.0,
        10,
        np.random.default_rng(7),
    )
    assert decision.state.action is ActionName.CARE
    assert decision.state.target_id == 2


def test_food_scarcity_outweighs_return_to_home(tiny_config):
    creature = animal(tiny_config, energy=20.0, home_center=np.array([5.0, 5.0]), home_radius=10.0)
    food = Resource(1, np.array([52.0, 50.0]), 28.0)
    decision = behavior.BehaviorController(tiny_config).decide(
        creature, BehaviorPerception(food=(food,)), 220.0, 10, np.random.default_rng(7)
    )
    assert decision.state.action is ActionName.FORAGE
    assert decision.scores[ActionName.FORAGE] > decision.scores[ActionName.PATROL]


def test_hysteresis_keeps_current_action_and_start_tick(tiny_config):
    creature = animal(
        tiny_config,
        energy=110.0,
        behavior_state=BehaviorState(action=ActionName.REST, started_tick=3),
    )
    controller = behavior.BehaviorController(tiny_config)
    decision = controller.decide(
        creature, BehaviorPerception(), 220.0, 10, np.random.default_rng(7)
    )
    assert decision.state.action is ActionName.REST
    assert decision.state.started_tick == 3
    assert 0.0 < max(decision.scores.values()) - decision.scores[ActionName.REST] < 0.08


def test_seeded_near_tie_decisions_match(tiny_config):
    controller = behavior.BehaviorController(tiny_config)
    first = np.random.default_rng(44)
    second = np.random.default_rng(44)
    creature = animal(tiny_config, behavior_state=BehaviorState(action=ActionName.FORAGE))
    original_rng = first.bit_generator.state
    actions = set()
    for tick in range(20):
        decision = controller.decide(creature, BehaviorPerception(), 220.0, tick, first)
        assert decision == controller.decide(creature, BehaviorPerception(), 220.0, tick, second)
        actions.add(decision.state.action)
    assert first.bit_generator.state != original_rng
    assert actions == {ActionName.EXPLORE, ActionName.PATROL}


def test_courtship_retains_eligible_target_when_another_mate_gets_closer(tiny_config):
    creature = animal(
        tiny_config,
        behavior_state=BehaviorState(
            action=ActionName.SEEK_MATE, started_tick=4, target_kind="creature", target_id=2
        ),
    )
    current_mate = animal(tiny_config, entity_id=2, position=(53.0, 50.0))
    newcomer = animal(tiny_config, entity_id=3, position=(51.0, 50.0))
    decision = behavior.BehaviorController(tiny_config).decide(
        creature,
        BehaviorPerception(eligible_mates=(current_mate, newcomer)),
        220.0,
        10,
        np.random.default_rng(1),
    )
    assert decision.state.action is ActionName.SEEK_MATE
    assert decision.state.target_id == 2
    assert decision.state.started_tick == 4


def test_challenge_can_compete_under_credible_local_pressure_without_alpha(tiny_config):
    creature = animal(
        tiny_config,
        home_center=np.array([5.0, 5.0]),
        home_radius=10.0,
        temperament=Temperament(aggression=1.0),
    )
    rival = animal(
        tiny_config,
        entity_id=2,
        position=(55.0, 50.0),
        hunger=0.9,
        temperament=Temperament(aggression=0.8),
    )
    controller = behavior.BehaviorController(tiny_config)
    actions = {
        controller.decide(
            creature, BehaviorPerception(threats=(rival,)), 220.0, 10, np.random.default_rng(seed)
        ).state.action
        for seed in range(30)
    }
    assert ActionName.CHALLENGE in actions
    creature.temperament = Temperament(aggression=0.0)
    decision = controller.decide(
        creature, BehaviorPerception(threats=(rival,)), 220.0, 10, np.random.default_rng(1)
    )
    assert ActionName.CHALLENGE not in decision.scores


def test_hunger_and_food_proximity_increase_foraging_pressure(tiny_config):
    creature = animal(tiny_config)
    food = Resource(1, np.array([50.0, 50.0]), 33.0)
    controller = behavior.BehaviorController(tiny_config)
    assert controller.drives(creature, BehaviorPerception(food=(food,)), 220.0).values[1] == 0.0
    creature.hunger = 0.8
    assert controller.drives(creature, BehaviorPerception(food=(food,)), 220.0).values[1] == 0.8
    food.position[:] = [100.0, 50.0]
    assert (
        0.4 < controller.drives(creature, BehaviorPerception(food=(food,)), 220.0).values[1] < 0.8
    )


def test_terrain_and_exposure_reduce_active_utility(tiny_config):
    creature = animal(tiny_config, energy=20.0)
    food = Resource(1, np.array([55.0, 50.0]), 28.0)
    controller = behavior.BehaviorController(tiny_config)
    safe = controller.decide(
        creature, BehaviorPerception(food=(food,)), 220.0, 10, np.random.default_rng(1)
    )
    risky = controller.decide(
        creature,
        BehaviorPerception(food=(food,), local_hazard=0.5, terrain_cost=1.0),
        220.0,
        10,
        np.random.default_rng(1),
    )
    assert risky.scores[ActionName.FORAGE] < safe.scores[ActionName.FORAGE]


@pytest.mark.parametrize(
    "field,value", [("age", 0), ("energy", 50.0), ("last_reproduction_tick", 10), ("alive", False)]
)
def test_mating_is_invalid_if_either_partner_loses_eligibility(tiny_config, field, value):
    creature = animal(tiny_config)
    mate = animal(tiny_config, entity_id=2, position=(52.0, 50.0))
    controller = behavior.BehaviorController(tiny_config)
    setattr(mate, field, value)
    decision = controller.decide(
        creature, BehaviorPerception(eligible_mates=(mate,)), 220.0, 10, np.random.default_rng(1)
    )
    assert ActionName.SEEK_MATE not in decision.scores
    setattr(creature, field, value)
    mate = animal(tiny_config, entity_id=2, position=(52.0, 50.0))
    decision = controller.decide(
        creature, BehaviorPerception(eligible_mates=(mate,)), 220.0, 10, np.random.default_rng(1)
    )
    assert ActionName.SEEK_MATE not in decision.scores


def test_food_target_prefers_gain_over_closest_small_patch(tiny_config):
    creature = animal(tiny_config, energy=20.0)
    small = Resource(1, np.array([51.0, 50.0]), 1.0)
    rich = Resource(2, np.array([60.0, 50.0]), 28.0)
    decision = behavior.BehaviorController(tiny_config).decide(
        creature, BehaviorPerception(food=(small, rich)), 220.0, 10, np.random.default_rng(1)
    )
    assert decision.state.action is ActionName.FORAGE
    assert decision.state.target_id == 2


def test_danger_uses_maximum_threat_and_hazard_pressure(tiny_config):
    creature = animal(tiny_config, injury=1.0)
    threat = animal(tiny_config, entity_id=2, temperament=Temperament(aggression=1.0))
    controller = behavior.BehaviorController(tiny_config)
    drives = controller.drives(
        creature, BehaviorPerception(threats=(threat,), local_hazard=0.3), 220.0
    )
    assert drives.values[4] == pytest.approx(2.0 / 3.0)
    drives = controller.drives(
        creature, BehaviorPerception(threats=(threat,), local_hazard=0.9), 220.0
    )
    assert drives.values[4] == 0.9
