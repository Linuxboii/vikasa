from __future__ import annotations

import math
from pathlib import Path

import pytest

from evolution_sim.config import ConfigError, SimulationConfig

ROOT = Path(__file__).resolve().parents[1]


def minimal_config() -> dict:
    return {
        "world": {"width": 1200, "height": 760, "boundary": "collision"},
        "genome": {
            "traits": {
                "size": [2.5, 8.0],
                "speed": [0.5, 4.0],
                "perception": [25.0, 150.0],
                "metabolism": [0.65, 1.5],
                "reproduction_threshold": [70.0, 150.0],
                "fertility": [0.15, 0.55],
            },
            "mutation_probability": 0.08,
            "mutation_sigma": 0.06,
            "crossover": "arithmetic",
        },
        "energy": {
            "initial": 95.0,
            "basal_cost": 0.025,
            "movement_cost": 0.018,
            "maximum": 220.0,
        },
        "reproduction": {
            "minimum_age": 240,
            "cooldown": 160,
            "mate_radius": 55.0,
            "offspring_energy": 34.0,
            "population_cap": 800,
        },
        "resources": {
            "initial_count": 220,
            "spawn_rate": 0.35,
            "maximum_count": 500,
            "energy_value": 28.0,
        },
        "metrics": {"sample_interval": 20, "diversity_sample": 128},
        "initial_population": 100,
        "maximum_age": 9000,
        "wander_change_probability": 0.025,
    }


def test_default_configuration_loads_and_round_trips() -> None:
    config = SimulationConfig.from_json(ROOT / "config" / "default.json")

    assert config.world.width == 1200
    assert config.initial_population == 100
    assert config.genome.traits["size"].minimum == 2.5
    assert SimulationConfig.from_dict(config.to_dict()) == config


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("world.width", 0),
        ("resources.spawn_rate", -0.1),
        ("genome.mutation_probability", 1.1),
        ("energy.initial", math.inf),
        ("reproduction.mate_radius", math.nan),
    ],
)
def test_invalid_numbers_report_the_exact_field(path: str, value: float) -> None:
    data = minimal_config()
    target = data
    parts = path.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value

    with pytest.raises(ConfigError, match=path.replace(".", r"\.")):
        SimulationConfig.from_dict(data)


def test_inverted_trait_bounds_are_rejected() -> None:
    data = minimal_config()
    data["genome"]["traits"]["speed"] = [5.0, 1.0]

    with pytest.raises(ConfigError, match=r"genome\.traits\.speed"):
        SimulationConfig.from_dict(data)


def test_unknown_fields_are_rejected_instead_of_silently_ignored() -> None:
    data = minimal_config()
    data["world"]["teleport"] = True

    with pytest.raises(ConfigError, match=r"world\.teleport"):
        SimulationConfig.from_dict(data)
