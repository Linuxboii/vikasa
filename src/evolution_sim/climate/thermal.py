"""Heritable thermal tolerance: performance curve, inheritance and summaries."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

from evolution_sim.config import ClimateConfig

if TYPE_CHECKING:
    from evolution_sim.simulation.engine import SimulationEngine

OPTIMUM_BOUNDS = (-20.0, 60.0)
STRESS_INJURY_THRESHOLD = 0.3


def thermal_stress(temperature_c: float, optimum_c: float, breadth_c: float,
                   warm_side_ratio: float) -> float:
    """1 - asymmetric Gaussian performance; the warm side falls off faster."""
    mismatch = temperature_c - optimum_c
    width = breadth_c * warm_side_ratio if mismatch > 0 else breadth_c
    return 1.0 - math.exp(-(mismatch * mismatch) / (2.0 * width * width))


def _clamp(value: float) -> float:
    return min(OPTIMUM_BOUNDS[1], max(OPTIMUM_BOUNDS[0], value))


def founder_optimum(config: ClimateConfig, rng: np.random.Generator) -> float:
    return _clamp(float(rng.normal(config.resolved_founder_mean_c, config.founder_sd_c)))


def inherit_optimum(config: ClimateConfig, first: float, second: float,
                    rng: np.random.Generator) -> float:
    """Infinitesimal-model inheritance, or a zero-heritability control draw."""
    if config.inheritance == "none":
        return founder_optimum(config, rng)
    segregation = float(rng.normal(0.0, config.segregation_sd_c))
    mutation = float(rng.normal(0.0, config.mutation_sd_c))
    return _clamp((first + second) / 2.0 + segregation + mutation)


def population_summary(engine: SimulationEngine) -> dict[str, Any]:
    climate = engine.climate
    if climate is None:
        raise ValueError("Population thermal summary requires climate forcing")
    # Observed at the current tick so it matches the environment readout.
    tick = max(0, engine.environment.current_tick)
    optima = [item.thermal_optimum for item in engine.creatures.values()]
    stress = [item.thermal_stress for item in engine.creatures.values()]
    annual = climate.annual_temperature_c(tick)
    mean = float(np.mean(optima)) if optima else None
    return {
        "temperature_c": engine.environment.temperature_c,
        "annual_temperature_c": annual,
        "mean_optimum_c": mean,
        "sd_optimum_c": float(np.std(optima)) if optima else None,
        "lag_c": None if mean is None else annual - mean,
        "mean_stress": float(np.mean(stress)) if stress else None,
        "population": len(optima),
    }
