from __future__ import annotations

import cProfile

import numpy as np
import pytest

from evolution_sim.model.spatial import SpatialHash


def test_query_crosses_cell_edges_and_filters_by_true_radius() -> None:
    index = SpatialHash(cell_size=10.0)
    index.insert(10, np.array([9.5, 5.0]))
    index.insert(11, np.array([10.5, 5.0]))
    index.insert(12, np.array([18.0, 5.0]))

    assert index.query_radius(np.array([10.0, 5.0]), 1.0) == [10, 11]


def test_results_are_stable_even_when_inserted_out_of_order() -> None:
    index = SpatialHash(cell_size=20.0)
    index.insert(9, np.array([10.0, 10.0]))
    index.insert(2, np.array([12.0, 10.0]))
    index.insert(7, np.array([14.0, 10.0]))

    assert index.query_radius(np.array([10.0, 10.0]), 10.0) == [2, 7, 9]


def test_empty_and_zero_radius_queries_are_well_defined() -> None:
    index = SpatialHash(cell_size=10.0)
    assert index.query_radius(np.zeros(2), 100.0) == []
    index.insert(1, np.zeros(2))
    assert index.query_radius(np.zeros(2), 0.0) == [1]


def test_rebuild_replaces_old_positions() -> None:
    index = SpatialHash(cell_size=10.0)
    index.rebuild({1: np.array([5.0, 5.0]), 2: np.array([90.0, 90.0])})
    assert index.query_radius(np.zeros(2), 10.0) == [1]

    index.rebuild({2: np.array([2.0, 2.0])})
    assert index.query_radius(np.zeros(2), 10.0) == [2]


def test_bulk_rebuild_validates_the_cloud_once_not_per_entity():
    """Catch reintroducing N NumPy reductions into every index rebuild."""
    index = SpatialHash(10)
    points = {key: np.array([key, 0.]) for key in range(100)}
    profiler = cProfile.Profile()
    profiler.runcall(index.rebuild, points)
    reductions = sum(entry.callcount for entry in profiler.getstats()
                     if isinstance(entry.code, str) and "'all' of 'numpy.ndarray'" in entry.code)
    assert reductions <= 1
    assert index.query_radius([0., 0.], 2) == [0, 1, 2]


def test_rebuild_and_insert_copy_input_positions():
    index = SpatialHash(10)
    first, second = np.array([1., 0.]), np.array([2., 0.])
    index.rebuild({1: first})
    index.insert(2, second)
    first[:] = second[:] = 100
    assert index.query_radius([0., 0.], 3) == [1, 2]


@pytest.mark.parametrize("point", [[np.nan, 0], [0, np.inf], [1], [[1, 2]]])
def test_rebuild_rejects_invalid_points(point):
    with pytest.raises(ValueError):
        SpatialHash(10).rebuild({1: point})


def test_query_rejects_nonfinite_imaginary_coordinates():
    index = SpatialHash(10)
    with pytest.raises(ValueError):
        index.query_radius(np.array([complex(1, float("inf")), 0]), 1)
