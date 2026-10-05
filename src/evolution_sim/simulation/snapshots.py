"""Immutable presentation boundary for simulation state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreatureSnapshot:
    id: int
    position: tuple[float, float]
    velocity: tuple[float, float]
    age: int
    energy: float
    genome: tuple[float, float, float, float, float, float]
    parents: tuple[int, int] | None
    offspring_count: int
    food_acquired: float
    birth_tick: int
    hunger: float = 0.0
    satisfaction_vector: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    satisfaction: float = 0.0
    fights_won: int = 0
    fights_lost: int = 0
    alpha: bool = False
    injury: float = 0.0
    temperament: tuple[float, float, float] = (0.25, 0.5, 0.5)
    belief_id: int | None = None


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    id: int
    position: tuple[float, float]
    energy: float


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    tick: int
    seed: int
    creatures: tuple[CreatureSnapshot, ...]
    resources: tuple[ResourceSnapshot, ...]
    births: int
    deaths: int
    total_births: int
    total_deaths: int
    food_multiplier: float
    metabolic_multiplier: float
    extinct: bool
    active_fights: tuple[dict[str, float | int], ...] = ()
