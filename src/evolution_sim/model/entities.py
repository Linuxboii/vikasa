"""Mutable world entities with strict state invariants."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from evolution_sim.model.genome import Genome
from evolution_sim.model.temperament import Temperament

Vector = NDArray[np.float64]


def _vector(value: Vector, name: str) -> Vector:
    result = np.asarray(value, dtype=np.float64).copy()
    if result.shape != (2,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must contain two finite numbers")
    return result


@dataclass(slots=True)
class Creature:
    id: int
    position: Vector
    velocity: Vector
    age: int
    energy: float
    genome: Genome
    parents: tuple[int, int] | None = None
    offspring_count: int = 0
    food_acquired: float = 0.0
    birth_tick: int = 0
    last_reproduction_tick: int = -1_000_000_000
    wander_angle: float = 0.0
    alive: bool = True
    trail: list[tuple[float, float]] = field(default_factory=list, repr=False)
    temperament: Temperament = field(default_factory=Temperament)
    hunger: float = 0.0
    satisfaction_vector: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    satisfaction: float = 0.0
    fights_won: int = 0
    fights_lost: int = 0
    fight_wins_tick: int = 0
    alpha: bool = False
    injury: float = 0.0
    starvation_ticks: int = 0
    death_cause: str | None = None
    belief_id: int | None = None
    ritual_ticks: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.id, int) or self.id < 0:
            raise ValueError("id must be a non-negative integer")
        self.position = _vector(self.position, "position")
        self.velocity = _vector(self.velocity, "velocity")
        if not isinstance(self.age, int) or self.age < 0:
            raise ValueError("age must be a non-negative integer")
        if not math.isfinite(self.energy):
            raise ValueError("energy must be finite")
        if not math.isfinite(self.hunger) or not 0.0 <= self.hunger <= 1.0:
            raise ValueError("hunger must be between zero and one")
        if not math.isfinite(self.satisfaction) or not 0.0 <= self.satisfaction <= 1.0:
            raise ValueError("satisfaction must be between zero and one")
        if not math.isfinite(self.injury) or not 0.0 <= self.injury <= 1.0:
            raise ValueError("injury must be between zero and one")
        if self.parents is not None and (
            len(self.parents) != 2 or any(parent < 0 for parent in self.parents)
        ):
            raise ValueError("parents must contain two non-negative IDs")


@dataclass(slots=True)
class Resource:
    id: int
    position: Vector
    energy: float
    radius: float = 3.0

    def __post_init__(self) -> None:
        if not isinstance(self.id, int) or self.id < 0:
            raise ValueError("id must be a non-negative integer")
        self.position = _vector(self.position, "position")
        if not math.isfinite(self.energy) or self.energy <= 0:
            raise ValueError("energy must be finite and positive")
        if not math.isfinite(self.radius) or self.radius <= 0:
            raise ValueError("radius must be finite and positive")
