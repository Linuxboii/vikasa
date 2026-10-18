from __future__ import annotations

import numpy as np
import pytest

from evolution_sim.climate.sensitivity import (
    design_conditions,
    ishigami,
    latin_hypercube,
    parameters,
    saltelli,
    scale,
    sobol_indices,
)


def test_ishigami_indices_match_analytic() -> None:
    result = sobol_indices(ishigami, 3, n=2**14, seed=7, n_boot=50)
    assert result["S1"] == pytest.approx([0.3139, 0.4424, 0.0], abs=0.03)
    assert result["ST"] == pytest.approx([0.5576, 0.4424, 0.2437], abs=0.03)
    assert len(result["S1_ci"]) == 3 and len(result["S1_ci"][0]) == 2


def test_saltelli_requires_power_of_two() -> None:
    with pytest.raises(ValueError, match="power of two"):
        saltelli(100, 3, seed=0)
    a, b = saltelli(64, 3, seed=0)
    assert a.shape == b.shape == (64, 3)
    assert not np.allclose(a, b)


def test_lhs_is_stratified() -> None:
    points = latin_hypercube(40, 6, seed=3)
    assert points.shape == (40, 6)
    for column in points.T:
        assert sorted(np.floor(column * 40).astype(int).tolist()) == list(range(40))


def test_parameters_order_and_rate_bound() -> None:
    params = parameters(1.2)
    assert [p.name for p in params] == ["rate_c_per_gen", "breadth_c", "amplitude_c",
                                        "founder_sd_c", "segregation_sd_c", "capacity_scale"]
    assert params[0].low == 0.0 and params[0].high == 1.2
    with pytest.raises(ValueError):
        parameters(0.0)


def test_design_conditions_map_parameters() -> None:
    params = parameters(1.0)
    physical = scale(latin_hypercube(8, 6, seed=1), params)
    conditions = design_conditions(physical, params, seed0=500)
    assert [c.seed for c in conditions] == list(range(500, 508))
    first = conditions[0]
    assert (first.rate_c_per_gen, first.breadth_c, first.amplitude_c, first.founder_sd_c,
            first.segregation_sd_c, first.capacity_scale) == pytest.approx(tuple(physical[0]))
    assert all(c.arm == "heritable" for c in conditions)
