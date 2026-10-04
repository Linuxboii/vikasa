from __future__ import annotations

from dataclasses import replace

import numpy as np

from evolution_sim.analytics.metrics import MetricsRecorder, analytical_fitness
from evolution_sim.model.entities import Creature
from evolution_sim.model.genome import Genome
from evolution_sim.simulation.engine import SimulationEngine


def genome_at(config, fraction: float) -> Genome:
    return Genome.from_mapping(
        {
            name: bounds.minimum + fraction * (bounds.maximum - bounds.minimum)
            for name, bounds in config.genome.traits.items()
        },
        config.genome,
    )


def controlled_engine(tiny_config) -> SimulationEngine:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=0.0),
    )
    engine = SimulationEngine(config, seed=9)
    engine.creatures = {
        1: Creature(
            1,
            np.array([10.0, 10.0]),
            np.zeros(2),
            100,
            80.0,
            genome_at(config, 0.0),
            offspring_count=0,
            food_acquired=10.0,
        ),
        2: Creature(
            2,
            np.array([20.0, 20.0]),
            np.zeros(2),
            300,
            120.0,
            genome_at(config, 1.0),
            offspring_count=4,
            food_acquired=50.0,
        ),
    }
    engine.tick = 50
    engine.tick_births = 2
    engine.tick_deaths = 1
    engine.total_births = 12
    engine.total_deaths = 8
    return engine


def test_record_captures_counts_and_hand_checked_trait_moments(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    recorder = MetricsRecorder()

    sample = recorder.record(engine)

    speed_bounds = engine.config.genome.traits["speed"]
    expected_mean = (speed_bounds.minimum + speed_bounds.maximum) / 2
    expected_variance = ((speed_bounds.maximum - speed_bounds.minimum) ** 2) / 4
    assert sample.population == 2
    assert sample.food == 0
    assert sample.births == 2
    assert sample.deaths == 1
    assert sample.trait_mean["speed"] == expected_mean
    assert sample.trait_median["speed"] == expected_mean
    assert sample.trait_variance["speed"] == expected_variance
    assert sample.trait_std["speed"] == expected_variance**0.5


def test_diversity_and_correlations_explain_population_structure(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    sample = MetricsRecorder().record(engine)

    assert sample.diversity > 0
    assert sample.trait_offspring_correlation["speed"] == 1.0
    assert sample.mean_fitness > 0


def test_single_creature_correlation_and_diversity_have_safe_fallback(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    engine.creatures = {1: engine.creatures[1]}

    sample = MetricsRecorder().record(engine)

    assert sample.diversity == 0.0
    assert sample.trait_offspring_correlation["size"] is None


def test_analytical_fitness_does_not_mutate_simulation(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    before = engine.snapshot()
    creature = engine.creatures[2]

    score = analytical_fitness(creature)

    assert score == 4 * 100.0 + 300 * 0.01 + 50.0 * 0.5
    assert engine.snapshot() == before


def test_rows_flatten_trait_metrics_for_csv(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    recorder = MetricsRecorder()
    recorder.record(engine)

    row = recorder.rows()[0]

    assert row["tick"] == 50
    assert row["population"] == 2
    assert row["speed_mean"] == 2.25
    assert row["speed_offspring_correlation"] == 1.0


def test_moving_average_uses_available_tail(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    recorder = MetricsRecorder()
    for population in (2, 4, 8):
        engine.creatures = {
            key: engine.creatures.get(1) or next(iter(engine.creatures.values()))
            for key in range(population)
        }
        recorder.record(engine)

    assert recorder.moving_average("population", window=2) == [2.0, 3.0, 6.0]


def test_trait_distribution_returns_current_values(tiny_config) -> None:
    engine = controlled_engine(tiny_config)
    recorder = MetricsRecorder()

    values = recorder.trait_distribution(engine, "fertility")

    bounds = engine.config.genome.traits["fertility"]
    assert values == [bounds.minimum, bounds.maximum]
