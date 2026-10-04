"""Deterministic uniform-grid spatial index."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from evolution_sim.model.math2d import distance_sq

Vector = NDArray[np.float64]
Cell = tuple[int, int]


class SpatialHash:
    def __init__(self, cell_size: float) -> None:
        if not math.isfinite(cell_size) or cell_size <= 0:
            raise ValueError("cell_size must be finite and positive")
        self.cell_size = float(cell_size)
        self._cells: dict[Cell, list[int]] = defaultdict(list)
        self._positions: dict[int, Vector] = {}

    def _cell(self, position: Vector) -> Cell:
        return (
            math.floor(float(position[0]) / self.cell_size),
            math.floor(float(position[1]) / self.cell_size),
        )

    def clear(self) -> None:
        self._cells.clear()
        self._positions.clear()

    def insert(self, entity_id: int, position: Vector) -> None:
        point = np.asarray(position, dtype=np.float64).copy()
        if point.shape != (2,) or not np.isfinite(point).all():
            raise ValueError("position must contain two finite values")
        if entity_id in self._positions:
            raise ValueError(f"Entity {entity_id} already exists in spatial index")
        self._positions[entity_id] = point
        self._cells[self._cell(point)].append(entity_id)

    def rebuild(self, positions: Mapping[int, Vector]) -> None:
        self.clear()
        for entity_id in sorted(positions):
            self.insert(entity_id, positions[entity_id])

    def query_radius(self, position: Vector, radius: float) -> list[int]:
        center = np.asarray(position, dtype=np.float64)
        if center.shape != (2,) or not np.isfinite(center).all():
            raise ValueError("position must contain two finite values")
        if not math.isfinite(radius) or radius < 0:
            raise ValueError("radius must be finite and non-negative")
        if not self._positions:
            return []
        minimum = self._cell(center - radius)
        maximum = self._cell(center + radius)
        radius_sq = radius * radius
        result: list[int] = []
        for x in range(minimum[0], maximum[0] + 1):
            for y in range(minimum[1], maximum[1] + 1):
                for entity_id in self._cells.get((x, y), ()):
                    if distance_sq(center, self._positions[entity_id]) <= radius_sq:
                        result.append(entity_id)
        return sorted(result)
