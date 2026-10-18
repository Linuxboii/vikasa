from __future__ import annotations

import math

import numpy as np
import pytest

from evolution_sim.climate.thermal import (
    OPTIMUM_BOUNDS,
    founder_optimum,
    inherit_optimum,
    thermal_stress,
)
from evolution_sim.config import ClimateConfig


def config(**overrides) -> ClimateConfig:
    base = {"enabled": True, "monthly_c": (25.0,) * 12, "founder_sd_c": 1.0,
            "segregation_sd_c": 0.4, "mutation_sd_c": 0.1}
    return ClimateConfig(**{**base, **overrides})


def test_stress_zero_at_optimum() -> None:
    assert thermal_stress(25.0, 25.0, 4.0, 0.6) == 0.0


def test_stress_asymmetric_warm_side_steeper() -> None:
    assert thermal_stress(27.0, 25.0, 4.0, 0.6) > thermal_stress(23.0, 25.0, 4.0, 0.6)


def test_stress_value() -> None:
    assert thermal_stress(29.0, 25.0, 4.0, 1.0) == pytest.approx(1 - math.exp(-0.5), abs=1e-12)
    assert thermal_stress(21.0, 25.0, 4.0, 0.5) == pytest.approx(1 - math.exp(-0.5), abs=1e-12)


def test_none_inheritance_ignores_parents() -> None:
    rng = np.random.default_rng(1)
    cfg = config(inheritance="none")
    draws = [inherit_optimum(cfg, 35.0, 35.0, rng) for _ in range(4000)]
    assert np.mean(draws) == pytest.approx(25.0, abs=0.1)
    assert np.std(draws) == pytest.approx(1.0, rel=0.1)


def test_heritable_inheritance_tracks_midparent() -> None:
    rng = np.random.default_rng(2)
    draws = [inherit_optimum(config(), 26.0, 28.0, rng) for _ in range(4000)]
    assert np.mean(draws) == pytest.approx(27.0, abs=0.05)
    assert np.std(draws) == pytest.approx(math.hypot(0.4, 0.1), rel=0.1)


def test_inherit_clamps_to_bounds() -> None:
    rng = np.random.default_rng(3)
    assert all(inherit_optimum(config(), 60.0, 60.0, rng) <= OPTIMUM_BOUNDS[1]
               for _ in range(200))


def test_founder_optimum_uses_resolved_mean() -> None:
    rng = np.random.default_rng(4)
    draws = [founder_optimum(config(founder_mean_c=30.0), rng) for _ in range(3000)]
    assert np.mean(draws) == pytest.approx(30.0, abs=0.1)
