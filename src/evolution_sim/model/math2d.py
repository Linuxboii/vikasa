"""Small, side-effect-free vector operations used by the simulation."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]


def unit_vector(vector: Vector) -> Vector:
    source = np.asarray(vector, dtype=np.float64)
    magnitude = float(np.linalg.norm(source))
    if magnitude == 0.0:
        return np.zeros(2, dtype=np.float64)
    return source / magnitude


def distance_sq(first: Vector, second: Vector) -> float:
    delta = np.asarray(first, dtype=np.float64) - np.asarray(second, dtype=np.float64)
    return float(np.dot(delta, delta))


def reflect_bounds(
    position: Vector,
    velocity: Vector,
    *,
    width: float,
    height: float,
) -> tuple[Vector, Vector]:
    next_position = np.asarray(position, dtype=np.float64).copy()
    next_velocity = np.asarray(velocity, dtype=np.float64).copy()
    limits = (float(width), float(height))
    for axis, limit in enumerate(limits):
        if next_position[axis] < 0.0:
            next_position[axis] = 0.0
            next_velocity[axis] = abs(next_velocity[axis])
        elif next_position[axis] > limit:
            next_position[axis] = limit
            next_velocity[axis] = -abs(next_velocity[axis])
    return next_position, next_velocity
