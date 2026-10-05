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


def test_legacy_configuration_gets_round_trippable_behavior_defaults() -> None:
    config = SimulationConfig.from_dict(minimal_config())
    assert config.behavior.hysteresis_margin >= 0
    assert SimulationConfig.from_dict(config.to_dict()) == config


def test_legacy_configuration_with_small_energy_cap_loads() -> None:
    data = minimal_config()
    data["energy"]["initial"] = data["energy"]["maximum"] = 0.01
    config = SimulationConfig.from_dict(data)
    assert config.behavior.care_energy_rate == 0.01


def test_behavior_defaults_are_explicit_in_serialized_configuration() -> None:
    config = SimulationConfig.from_dict(minimal_config())
    assert config.to_dict()["behavior"] == {
        "hysteresis_margin": 0.08,
        "softmax_temperature": 0.08,
        "dependent_age_ticks": 240,
        "care_radius": 24.0,
        "care_energy_rate": 0.25,
        "danger_preempt_threshold": 0.75,
        "territory_migration_margin": 0.15,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("hysteresis_margin", -0.1),
        ("hysteresis_margin", 1.1),
        ("softmax_temperature", 0),
        ("softmax_temperature", 1.1),
        ("dependent_age_ticks", -1),
        ("dependent_age_ticks", 1.5),
        ("care_radius", -1),
        ("care_radius", 800),
        ("care_energy_rate", -1),
        ("care_energy_rate", 221),
        ("danger_preempt_threshold", -0.1),
        ("danger_preempt_threshold", 1.1),
        ("territory_migration_margin", -0.1),
        ("territory_migration_margin", 1.1),
        ("care_radius", math.inf),
        ("hysteresis_margin", math.nan),
    ],
)
def test_behavior_configuration_rejects_invalid_settings(field: str, value: float) -> None:
    data = minimal_config()
    data["behavior"] = {field: value}
    with pytest.raises(ConfigError, match=rf"behavior\.{field}"):
        SimulationConfig.from_dict(data)


def test_behavior_configuration_rejects_unknown_fields() -> None:
    data = minimal_config()
    data["behavior"] = {"telepathy": True}
    with pytest.raises(ConfigError, match=r"behavior\.telepathy"):
        SimulationConfig.from_dict(data)
