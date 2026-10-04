from __future__ import annotations

import numpy as np

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
