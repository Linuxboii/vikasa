from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evolution_sim.config import SimulationConfig
from evolution_sim.model.genome import Genome, Trait, random_genome

ROOT = Path(__file__).resolve().parents[2]
CONFIG = SimulationConfig.from_json(ROOT / "config" / "default.json")


def test_trait_order_is_stable_for_storage_and_math() -> None:
    assert [trait.value for trait in Trait] == [
        "size",
        "speed",
        "perception",
        "metabolism",
        "reproduction_threshold",
        "fertility",
    ]


def test_genome_mapping_round_trip_preserves_values() -> None:
    values = {
        "size": 4.0,
        "speed": 2.0,
        "perception": 80.0,
        "metabolism": 1.1,
        "reproduction_threshold": 100.0,
        "fertility": 0.3,
    }

    genome = Genome.from_mapping(values, CONFIG.genome)

    assert genome.to_mapping() == values
    assert genome[Trait.PERCEPTION] == 80.0
    assert genome.as_array().tolist() == list(values.values())


def test_genome_rejects_out_of_bounds_value() -> None:
    values = {name: bounds.minimum for name, bounds in CONFIG.genome.traits.items()}
    values["speed"] = 99.0

    with pytest.raises(ValueError, match="speed"):
        Genome.from_mapping(values, CONFIG.genome)


def test_random_genome_uses_supplied_rng_and_stays_bounded() -> None:
    first = random_genome(CONFIG.genome, np.random.default_rng(42))
    second = random_genome(CONFIG.genome, np.random.default_rng(42))

    assert first == second
    for name, value in first.to_mapping().items():
        bounds = CONFIG.genome.traits[name]
        assert bounds.minimum <= value <= bounds.maximum


def test_genome_clamp_handles_extreme_values() -> None:
    raw = np.array([-1e9, 1e9, -1e9, 1e9, -1e9, 1e9], dtype=float)

    genome = Genome.clamped(raw, CONFIG.genome)

    expected = []
    for index, bounds in enumerate(CONFIG.genome.traits.values()):
        expected.append(bounds.minimum if index % 2 == 0 else bounds.maximum)
    assert genome.as_array().tolist() == expected


def test_config_can_be_replaced_for_genetic_experiments() -> None:
    changed = replace(CONFIG.genome, mutation_probability=0.0)
    assert changed.mutation_probability == 0.0
    assert CONFIG.genome.mutation_probability == 0.08

