from __future__ import annotations

import numpy as np
import pytest

from evolution_sim.model.math2d import distance_sq, reflect_bounds, unit_vector


def test_unit_vector_normalizes_without_mutating_input() -> None:
    source = np.array([3.0, 4.0])

    result = unit_vector(source)

    assert result.tolist() == [0.6, 0.8]
    assert source.tolist() == [3.0, 4.0]


def test_zero_vector_stays_finite_and_stationary() -> None:
    result = unit_vector(np.zeros(2))
    assert result.tolist() == [0.0, 0.0]
    assert np.isfinite(result).all()


def test_squared_distance_is_hand_calculated() -> None:
    assert distance_sq(np.array([2.0, 3.0]), np.array([5.0, 7.0])) == 25.0


def test_collision_boundary_clamps_position_and_reflects_velocity() -> None:
    position, velocity = reflect_bounds(
        np.array([-3.0, 107.0]), np.array([-2.0, 5.0]), width=100.0, height=100.0
    )

    assert position.tolist() == [0.0, 100.0]
    assert velocity.tolist() == [2.0, -5.0]


def test_in_bounds_motion_is_unchanged() -> None:
    position, velocity = reflect_bounds(
        np.array([10.0, 20.0]), np.array([1.0, -2.0]), width=100.0, height=100.0
    )

    assert position.tolist() == [10.0, 20.0]
    assert velocity.tolist() == [1.0, -2.0]


@pytest.mark.parametrize("point", [0.0, [], [1.0], [1.0, 2.0, 3.0], [[1.0, 2.0]], [[1.0], [2.0]]])
def test_squared_distance_rejects_non_two_dimensional_points(point):
    with pytest.raises(ValueError, match="two coordinates"):
        distance_sq(point, np.zeros(2))
    with pytest.raises(ValueError, match="two coordinates"):
        distance_sq(np.zeros(2), point)


def test_squared_distance_scalar_path_matches_numpy_reference_without_mutation():
    rng = np.random.default_rng(902)
    for _ in range(100):
        first = rng.uniform(-1_000.0, 1_000.0, 2)
        second = rng.uniform(-1_000.0, 1_000.0, 2)
        original_first, original_second = first.copy(), second.copy()
        delta = first - second
        assert distance_sq(first, second) == pytest.approx(float(np.dot(delta, delta)), rel=1e-15)
        assert np.array_equal(first, original_first)
        assert np.array_equal(second, original_second)


@pytest.mark.parametrize(
    "first,second,expected",
    [
        ([0, 0], [0, 0], 0.0),
        ((-2.0, -3.0), (1.0, 1.0), 25.0),
        ((1e-150, 0.0), (0.0, 0.0), 1e-300),
    ],
)
def test_squared_distance_supports_numeric_point_inputs_and_small_values(first, second, expected):
    assert distance_sq(first, second) == expected


def test_squared_distance_preserves_non_finite_propagation():
    assert np.isnan(distance_sq(np.array([np.nan, 0.0]), np.zeros(2)))
    assert np.isinf(distance_sq(np.array([np.inf, 0.0]), np.zeros(2)))
