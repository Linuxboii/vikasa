from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.model.genetics import crossover, mutate
from evolution_sim.model.genome import Genome

ROOT = Path(__file__).resolve().parents[2]
CONFIG = SimulationConfig.from_json(ROOT / "config" / "default.json")


def parent_at(fraction: float) -> Genome:
    values = {
        name: bounds.minimum + fraction * (bounds.maximum - bounds.minimum)
        for name, bounds in CONFIG.genome.traits.items()
    }
    return Genome.from_mapping(values, CONFIG.genome)


def test_uniform_crossover_selects_each_gene_from_a_parent() -> None:
    first = parent_at(0.0)
    second = parent_at(1.0)

    child = crossover(first, second, "uniform", np.random.default_rng(7))

    for index, value in enumerate(child.as_array()):
        assert value in {first.as_array()[index], second.as_array()[index]}
    assert child != first
    assert child != second


def test_arithmetic_crossover_is_seeded_and_between_parents() -> None:
    first = parent_at(0.2)
    second = parent_at(0.8)

    child_a = crossover(first, second, "arithmetic", np.random.default_rng(99))
    child_b = crossover(first, second, "arithmetic", np.random.default_rng(99))

    assert child_a == child_b
    assert np.all(child_a.as_array() >= first.as_array())
    assert np.all(child_a.as_array() <= second.as_array())


def test_mutation_disabled_returns_same_genome() -> None:
    original = parent_at(0.5)
    config = replace(CONFIG.genome, mutation_probability=0.0, mutation_sigma=1.0)

    assert mutate(original, config, np.random.default_rng(4)) == original


def test_extreme_mutation_remains_inside_every_bound() -> None:
    original = parent_at(0.5)
    config = replace(CONFIG.genome, mutation_probability=1.0, mutation_sigma=100.0)

    mutated = mutate(original, config, np.random.default_rng(5))

    assert mutated != original
    for name, value in mutated.to_mapping().items():
        bounds = config.traits[name]
        assert bounds.minimum <= value <= bounds.maximum


def test_unknown_crossover_mode_is_rejected() -> None:
    first = parent_at(0.2)
    second = parent_at(0.8)

    try:
        crossover(first, second, "splice", np.random.default_rng(1))
    except ValueError as exc:
        assert "splice" in str(exc)
    else:
        raise AssertionError("Unsupported crossover mode was accepted")
