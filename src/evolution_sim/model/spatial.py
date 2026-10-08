"""Deterministic uniform-grid spatial index."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

Vector = NDArray[np.float64]
Cell = tuple[int, int]


class SpatialHash:
    def __init__(self, cell_size: float) -> None:
        if not math.isfinite(cell_size) or cell_size <= 0:
            raise ValueError("cell_size must be finite and positive")
        self.cell_size = float(cell_size)
        self._cells: dict[Cell, list[int]] = defaultdict(list)
        self._positions: dict[int, tuple[float, float]] = {}

    def _cell(self, position: Vector) -> Cell:
        return (
            math.floor(float(position[0]) / self.cell_size),
            math.floor(float(position[1]) / self.cell_size),
        )

    def clear(self) -> None:
        self._cells.clear()
        self._positions.clear()

    def insert(self, entity_id: int, position: Vector) -> None:
        point = np.asarray(position, dtype=np.float64)
        if point.shape != (2,):
            raise ValueError("position must contain two finite values")
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("position must contain two finite values")
        if entity_id in self._positions:
            raise ValueError(f"Entity {entity_id} already exists in spatial index")
        self._positions[entity_id] = (x, y)
        self._cells[self._cell(point)].append(entity_id)

    def rebuild(self, positions: Mapping[int, Vector]) -> None:
        self.clear()
        ids = sorted(positions)
        if not ids:
            return
        points = np.asarray([positions[key] for key in ids], dtype=np.float64)
        if points.shape != (len(ids), 2) or not np.isfinite(points).all():
            raise ValueError("positions must contain two finite values per entity")
        # One finite reduction for the cloud, immutable scalar copies for queries.
        # Stable IDs and arithmetic/order match the individual insertion path.
        for entity_id, point in zip(ids, points.tolist(), strict=True):
            x, y = point
            self._positions[entity_id] = (x, y)
            self._cells[(math.floor(x / self.cell_size),
                         math.floor(y / self.cell_size))].append(entity_id)

    def query_radius(self, position: Vector, radius: float) -> list[int]:
        center = (
            position
            if isinstance(position, np.ndarray)
            else np.asarray(position, dtype=np.float64)
        )
        if center.shape != (2,):
            raise ValueError("position must contain two finite values")
        if np.iscomplexobj(center) and not np.isfinite(center).all():
            raise ValueError("position must contain two finite values")
        center_x, center_y = float(center[0]), float(center[1])
        if not math.isfinite(center_x) or not math.isfinite(center_y):
            raise ValueError("position must contain two finite values")
        if not math.isfinite(radius) or radius < 0:
            raise ValueError("radius must be finite and non-negative")
        if not self._positions:
            return []
        minimum_x = math.floor((center_x - radius) / self.cell_size)
        maximum_x = math.floor((center_x + radius) / self.cell_size)
        minimum_y = math.floor((center_y - radius) / self.cell_size)
        maximum_y = math.floor((center_y + radius) / self.cell_size)
        radius_sq = radius * radius
        result: list[int] = []
        for x in range(minimum_x, maximum_x + 1):
            for y in range(minimum_y, maximum_y + 1):
                for entity_id in self._cells.get((x, y), ()):
                    candidate = self._positions[entity_id]
                    dx = center_x - candidate[0]
                    dy = center_y - candidate[1]
                    if dx * dx + dy * dy <= radius_sq:
                        result.append(entity_id)
        result.sort()
        return result
