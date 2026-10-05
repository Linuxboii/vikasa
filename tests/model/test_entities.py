from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from evolution_sim.config import SimulationConfig
from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genome import random_genome

ROOT = Path(__file__).resolve().parents[2]
CONFIG = SimulationConfig.from_json(ROOT / "config" / "default.json")
GENOME = random_genome(CONFIG.genome, np.random.default_rng(1))


def test_creature_tracks_lifecycle_and_family_state() -> None:
    creature = Creature(
        id=7,
        position=np.array([10.0, 20.0]),
        velocity=np.array([1.0, 0.0]),
        age=12,
        energy=88.0,
        genome=GENOME,
        parents=(2, 5),
        birth_tick=100,
    )

    assert creature.id == 7
    assert creature.parents == (2, 5)
    assert creature.alive
    assert creature.offspring_count == 0
    assert creature.position.tolist() == [10.0, 20.0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", -1),
        ("energy", float("nan")),
        ("position", np.array([1.0, float("inf")])),
        ("velocity", np.array([1.0, 2.0, 3.0])),
    ],
)
def test_creature_rejects_corrupt_state(field: str, value: object) -> None:
    values = {
        "id": 1,
        "position": np.array([10.0, 20.0]),
        "velocity": np.zeros(2),
        "age": 0,
        "energy": 50.0,
        "genome": GENOME,
    }
    values[field] = value
    with pytest.raises(ValueError, match=field):
        Creature(**values)


def test_resource_requires_finite_positive_energy() -> None:
    resource = Resource(3, np.array([8.0, 9.0]), 25.0)
    assert resource.energy == 25.0

    with pytest.raises(ValueError, match="energy"):
        Resource(4, np.array([8.0, 9.0]), 0.0)


def test_creatures_own_home_center_and_default_behavior() -> None:
    position = np.array([10.0, 20.0])
    first = Creature(1, position, np.zeros(2), 0, 50.0, GENOME)
    second = Creature(2, position, np.zeros(2), 0, 50.0, GENOME)
    first.home_center[0] = 99.0
    assert second.home_center.tolist() == [10.0, 20.0]
    assert first.position.tolist() == position.tolist() == [10.0, 20.0]
    assert first.behavior_state.action.value == "explore"
    assert 0 < second.home_radius <= min(CONFIG.world.width, CONFIG.world.height) / 2


@pytest.mark.parametrize(
    "field,value",
    [("home_radius", -1.0), ("home_radius", float("inf")), ("home_center", [0.0, float("nan")])],
)
def test_creature_rejects_corrupt_home_range(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        Creature(1, np.zeros(2), np.zeros(2), 0, 50.0, GENOME, **{field: value})
