from __future__ import annotations

from dataclasses import replace

import numpy as np

from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genome import Genome
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
