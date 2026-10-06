from __future__ import annotations

from dataclasses import replace

import numpy as np

from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genome import Genome
from evolution_sim.model.temperament import Temperament
from evolution_sim.simulation.behavior import ActionName, BehaviorState
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


def middle_genome(config, **overrides: float) -> Genome:
    values = {
        name: (bounds.minimum + bounds.maximum) / 2 for name, bounds in config.genome.traits.items()
    }
    values.update(overrides)
    return Genome.from_mapping(values, config.genome)


def test_initial_world_has_unique_entities_and_seeded_snapshot(tiny_config) -> None:
    first = SimulationEngine(tiny_config, seed=123)
    second = SimulationEngine(tiny_config, seed=123)

    assert len(first.creatures) == 4
    assert len(first.resources) == 8
    assert first.snapshot() == second.snapshot()
    assert first.audit_invariants() == []


def test_fractional_food_spawn_accumulator_is_tick_stable(tiny_config) -> None:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=0.25),
    )
    engine = SimulationEngine(config, seed=3)

    engine.step(3)
    assert len(engine.resources) == 0
    engine.step()
    assert len(engine.resources) == 1


def test_repeat_winners_raise_fight_risk_but_keep_it_low() -> None:
    ordinary_risk = SimulationEngine._fight_risk(0.8, 0.8, True, 0.0)
    alpha_risk = SimulationEngine._fight_risk(0.8, 0.8, True, 1.0)

    assert 0.0 < ordinary_risk < 0.01
    assert ordinary_risk < alpha_risk < 0.03


def test_drought_reduces_food_spawn_without_changing_base_config(tiny_config) -> None:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=1.0),
    )
    engine = SimulationEngine(config, seed=3)
    engine.environment.schedule(EnvironmentEvent("drought", 0, 4, 0.25))

    engine.step(4)

    assert len(engine.resources) == 1
    assert engine.config.resources.spawn_rate == 1.0


def test_movement_and_metabolism_consume_energy(tiny_config) -> None:
    config = replace(
        tiny_config, initial_population=1, resources=replace(tiny_config.resources, initial_count=0)
    )
    engine = SimulationEngine(config, seed=6)
    creature = next(iter(engine.creatures.values()))
    start_energy = creature.energy
    start_position = creature.position.copy()

    engine.step()

    assert creature.energy < start_energy
    assert not np.array_equal(creature.position, start_position)


def test_food_contention_prefers_distance_then_stable_id(tiny_config) -> None:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=0.0),
    )
    engine = SimulationEngine(config, seed=8)
    genome = middle_genome(config)
    engine.creatures = {
        10: Creature(10, np.array([50.0, 50.0]), np.zeros(2), 10, 50.0, genome),
        2: Creature(2, np.array([50.0, 50.0]), np.zeros(2), 10, 50.0, genome),
    }
    engine.resources = {9: Resource(9, np.array([50.0, 50.0]), 25.0)}

    engine.step()

    assert engine.creatures[2].food_acquired == 25.0
    assert engine.creatures[10].food_acquired == 0.0
    assert engine.resources == {}


def test_eligible_nearby_pair_creates_mutated_lineage_child(tiny_config) -> None:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=0.0),
    )
    engine = SimulationEngine(config, seed=22)
    genome_a = middle_genome(config, fertility=0.55)
    genome_b = middle_genome(config, speed=3.5, fertility=0.55)
    engine.creatures = {
        1: Creature(1, np.array([80.0, 60.0]), np.zeros(2), 50, 200.0, genome_a),
        2: Creature(2, np.array([82.0, 60.0]), np.zeros(2), 50, 200.0, genome_b),
    }
    engine.next_creature_id = 3

    engine.step()

    assert set(engine.creatures) == {1, 2, 3}
    child = engine.creatures[3]
    assert child.parents == (1, 2)
    assert engine.lineage.parents_of(3) == (1, 2)
    assert engine.creatures[1].offspring_count == 1
    assert engine.tick_births == 1


def test_population_cap_skips_reproduction_without_corrupting_state(tiny_config) -> None:
    config = replace(tiny_config, reproduction=replace(tiny_config.reproduction, population_cap=4))
    engine = SimulationEngine(config, seed=1)
    for creature in engine.creatures.values():
        creature.age = 100
        creature.energy = 200.0
        creature.position[:] = [50.0, 50.0]

    engine.step()

    assert len(engine.creatures) <= 4
    assert engine.reproduction_skipped_at_cap > 0
    assert engine.audit_invariants() == []


def test_extinction_is_terminal_but_safe_and_snapshot_remains_available(tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=1)
    engine.creatures.clear()

    engine.step(5)

    assert engine.extinct
    assert engine.tick == 5
    assert engine.snapshot().creatures == ()
    assert engine.audit_invariants() == []


def test_maximum_age_death_is_counted_and_removed(tiny_config) -> None:
    config = replace(tiny_config, initial_population=1, maximum_age=2)
    engine = SimulationEngine(config, seed=7)
    creature_id = next(iter(engine.creatures))
    engine.creatures[creature_id].age = 2

    engine.step()

    assert creature_id not in engine.creatures
    assert engine.tick_deaths == 1
    assert engine.total_deaths == 1


def controlled_engine(config, seed=17):
    config = replace(
        config,
        initial_population=1,
        resources=replace(config.resources, initial_count=0, spawn_rate=0.0),
    )
    engine = SimulationEngine(config, seed=seed)
    engine.creatures = {
        1: Creature(
            1,
            np.array([80.0, 60.0]),
            np.zeros(2),
            300,
            200.0,
            middle_genome(config),
            temperament=Temperament(),
        )
    }
    engine.next_creature_id = 2
    return engine


def test_forage_action_reaches_and_consumes_perceived_food(tiny_config):
    engine = controlled_engine(tiny_config)
    creature = engine.creatures[1]
    creature.energy = 20.0
    engine.resources = {1: Resource(1, np.array([85.0, 60.0]), 28.0)}
    engine.step()
    assert creature.behavior_state.action is ActionName.FORAGE
    assert creature.food_acquired == 28.0
    assert engine.resources == {}
    assert engine.audit_invariants() == []


def test_flee_action_increases_distance_from_stronger_aggressive_threat(tiny_config):
    engine = controlled_engine(tiny_config)
    creature = engine.creatures[1]
    threat = Creature(
        2,
        np.array([84.0, 60.0]),
        np.zeros(2),
        300,
        220.0,
        middle_genome(tiny_config, size=8.0),
        temperament=Temperament(aggression=1.0),
    )
    engine.creatures[2] = threat
    before = np.linalg.norm(creature.position - threat.position)
    engine._choose_behavior(1)
    engine._execute_behavior(1)
    assert creature.behavior_state.action is ActionName.FLEE
    assert np.linalg.norm(creature.position - threat.position) > before


def test_rest_consumes_less_energy_than_explore(tiny_config):
    engines = [controlled_engine(tiny_config) for _ in range(2)]
    for engine, action in zip(engines, (ActionName.REST, ActionName.EXPLORE), strict=True):
        engine.creatures[1].velocity[:] = [2.0, 0.0]
        engine.creatures[1].behavior_state = BehaviorState(action=action)
        engine._execute_behavior(1)
    assert engines[0].creatures[1].energy > engines[1].creatures[1].energy
    assert np.linalg.norm(engines[0].creatures[1].velocity) < np.linalg.norm(
        engines[1].creatures[1].velocity
    )


def test_patrol_from_home_samples_and_walks_bounded_waypoints(tiny_config):
    engine = controlled_engine(tiny_config, seed=37)
    creature = engine.creatures[1]
    creature.home_center[:] = creature.position
    creature.home_radius = 18.0
    creature.behavior_state = BehaviorState(
        action=ActionName.PATROL,
        target_kind="home",
        target_position=tuple(creature.position),
    )
    start = creature.position.copy()

    for _ in range(12):
        engine._choose_behavior(creature.id)
        assert creature.behavior_state.action is ActionName.PATROL
        target = np.asarray(creature.behavior_state.target_position)
        assert 0.0 < np.linalg.norm(target - creature.home_center) <= creature.home_radius
        assert np.all(target >= 0.0)
        assert target[0] <= tiny_config.world.width
        assert target[1] <= tiny_config.world.height
        engine._execute_behavior(creature.id)
        assert np.linalg.norm(creature.position - creature.home_center) <= creature.home_radius

    assert np.linalg.norm(creature.position - start) > 0.0


def test_patrol_at_world_corner_falls_back_to_feasible_inward_waypoint(tiny_config):
    engine = controlled_engine(tiny_config, seed=37)
    creature = engine.creatures[1]
    creature.position[:] = [0.0, 0.0]
    creature.home_center[:] = [0.0, 0.0]
    creature.home_radius = 18.0
    creature.behavior_state = BehaviorState(
        action=ActionName.PATROL,
        target_kind="home",
        target_position=(0.0, 0.0),
    )

    class SouthWestRng:
        def uniform(self, low, high):
            if low == 0.0 and high > 6.0:
                return 3.75
            return low + 0.95 * (high - low)

    engine.rng = SouthWestRng()
    engine._choose_behavior(creature.id)
    target = np.asarray(creature.behavior_state.target_position)
    assert 0.0 < np.linalg.norm(target - creature.home_center) <= creature.home_radius
    assert np.all(target >= 0.0)
    assert target[0] <= tiny_config.world.width
    assert target[1] <= tiny_config.world.height

    start = creature.position.copy()
    for _ in range(12):
        engine._execute_behavior(creature.id)
        assert np.all(creature.position >= 0.0)
        assert creature.position[0] <= tiny_config.world.width
        assert creature.position[1] <= tiny_config.world.height
    assert np.linalg.norm(creature.position - start) > 0.0


def test_care_transfers_bounded_energy_to_dependent_with_parent_reserve(tiny_config):
    engine = controlled_engine(tiny_config)
    child = Creature(
        2, np.array([82.0, 60.0]), np.zeros(2), 5, 10.0, middle_genome(tiny_config), parents=(1, 99)
    )
    engine.creatures[2] = child
    parent = engine.creatures[1]
    engine._choose_behavior(1)
    engine._execute_behavior(1)
    assert parent.behavior_state.action is ActionName.CARE
    assert child.energy == 10.25
    assert parent.energy >= 0.35 * tiny_config.energy.maximum
    assert parent.offspring_count == 0
    parent.energy = 0.35 * tiny_config.energy.maximum
    before = child.energy
    engine._execute_behavior(1)
    assert child.energy == before
    child.parents = (8, 99)
    parent.energy = 200.0
    engine._execute_behavior(1)
    assert child.energy == before


def test_proximity_without_mutual_mating_selection_does_not_birth(tiny_config):
    engine = controlled_engine(tiny_config)
    engine.creatures[2] = Creature(
        2, np.array([82.0, 60.0]), np.zeros(2), 300, 200.0, middle_genome(tiny_config)
    )
    engine._resolve_reproduction()
    assert len(engine.creatures) == 2
    engine._choose_behavior(1)
    engine._choose_behavior(2)
    engine.creatures[2].age = 0
    engine._resolve_reproduction()
    assert len(engine.creatures) == 2


def test_founder_and_offspring_home_radius_is_clamped_in_small_world(tiny_config):
    config = replace(tiny_config, world=replace(tiny_config.world, width=20, height=10))
    engine = SimulationEngine(config, seed=5)
    assert all(0 < creature.home_radius <= 5.0 for creature in engine.creatures.values())
    for creature in engine.creatures.values():
        creature.age = 300
        creature.energy = 220.0
        creature.position[:] = [10.0, 5.0]
        creature.temperament = Temperament(aggression=0.0)
    engine.step()
    assert engine.tick_births > 0
    assert all(0 < creature.home_radius <= 5.0 for creature in engine.creatures.values())


def test_migration_requires_sustained_outside_reward_and_resets_on_loss(tiny_config):
    engine = controlled_engine(tiny_config)
    creature = engine.creatures[1]
    creature.home_center[:] = [10.0, 60.0]
    creature.home_radius = 10.0
    creature.energy = 20.0
    engine.resources = {1: Resource(1, np.array([85.0, 60.0]), 28.0)}
    for _ in range(23):
        engine._choose_behavior(1)
    assert creature.home_migration_ticks == 23
    assert creature.home_center.tolist() == [10.0, 60.0]
    engine._choose_behavior(1)
    assert creature.home_center[0] == 10.35
    engine.resources.clear()
    engine._choose_behavior(1)
    assert creature.home_migration_ticks == 0


def test_alpha_status_alone_does_not_trigger_a_contest(tiny_config):
    engine = controlled_engine(tiny_config)
    engine.creatures[2] = Creature(
        2,
        np.array([81.0, 60.0]),
        np.zeros(2),
        300,
        220.0,
        middle_genome(tiny_config),
        temperament=Temperament(aggression=0.0),
    )
    for creature in engine.creatures.values():
        creature.alpha = True
        creature.hunger = 0.0
    rng_state = engine.rng.bit_generator.state
    for _ in range(100):
        engine._resolve_fights()
    assert engine.combat_events == []
    assert engine.rng.bit_generator.state == rng_state
