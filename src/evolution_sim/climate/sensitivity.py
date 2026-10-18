"""Experimental design and variance-based (Sobol) global sensitivity analysis."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc

from evolution_sim.climate.protocol import RescueCondition


@dataclass(frozen=True)
class Parameter:
    name: str
    low: float
    high: float
    unit: str
    description: str


def parameters(rate_high: float) -> tuple[Parameter, ...]:
    """The six surrogate inputs, in the fixed column order used everywhere."""
    if not math.isfinite(rate_high) or rate_high <= 0:
        raise ValueError("rate_high must be finite and positive")
    return (
        Parameter("rate_c_per_gen", 0.0, rate_high, "°C/generation", "Warming rate"),
        Parameter("breadth_c", 2.0, 8.0, "°C", "Thermal tolerance breadth (cold side)"),
        Parameter("amplitude_c", 0.5, 8.0, "°C", "Seasonal temperature amplitude"),
        Parameter("founder_sd_c", 0.25, 2.0, "°C", "Standing variation in thermal optimum"),
        Parameter("segregation_sd_c", 0.0, 1.0, "°C", "Heritable variation among offspring"),
        Parameter("capacity_scale", 0.5, 1.5, "multiplier", "Habitat carrying capacity"),
    )


def latin_hypercube(n: int, d: int, seed: int) -> np.ndarray:
    return qmc.LatinHypercube(d=d, seed=np.random.default_rng(seed)).random(n)


def scale(unit: np.ndarray, params: tuple[Parameter, ...]) -> np.ndarray:
    low = np.array([p.low for p in params])
    high = np.array([p.high for p in params])
    return low + np.asarray(unit) * (high - low)


def unscale(physical: np.ndarray, params: tuple[Parameter, ...]) -> np.ndarray:
    low = np.array([p.low for p in params])
    high = np.array([p.high for p in params])
    return (np.asarray(physical, dtype=float) - low) / (high - low)


def design_conditions(points: np.ndarray, params: tuple[Parameter, ...], *,
                      arm: str = "heritable", seed0: int) -> list[RescueCondition]:
    names = [p.name for p in params]
    return [RescueCondition(arm=arm, seed=seed0 + index,
                            **{name: float(value) for name, value in zip(names, row,
                                                                         strict=True)})
            for index, row in enumerate(np.asarray(points))]


def saltelli(n: int, d: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    if n < 2 or n & (n - 1):
        raise ValueError("Saltelli base sample size must be a power of two")
    sample = qmc.Sobol(d=2 * d, scramble=True, seed=np.random.default_rng(seed)).random_base2(
        int(math.log2(n)))
    return sample[:, :d], sample[:, d:]


def _jansen(fa: np.ndarray, fb: np.ndarray, fab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    variance = np.var(np.concatenate([fa, fb]))
    if variance == 0:
        zeros = np.zeros(fab.shape[0])
        return zeros, zeros
    first = (variance - 0.5 * np.mean((fb[None, :] - fab) ** 2, axis=1)) / variance
    total = 0.5 * np.mean((fa[None, :] - fab) ** 2, axis=1) / variance
    return first, total


def sobol_indices(f: Callable[[np.ndarray], np.ndarray], d: int, *, n: int = 4096,
                  seed: int = 0, n_boot: int = 200) -> dict[str, list]:
    """First- and total-order indices (Jansen 1999 / Saltelli 2010) on the unit cube."""
    a, b = saltelli(n, d, seed)
    fa, fb = np.asarray(f(a), dtype=float), np.asarray(f(b), dtype=float)
    fab = np.empty((d, n))
    for i in range(d):
        mixed = a.copy()
        mixed[:, i] = b[:, i]
        fab[i] = np.asarray(f(mixed), dtype=float)
    first, total = _jansen(fa, fb, fab)
    rng = np.random.default_rng(seed + 1)
    boot_first, boot_total = [], []
    for _ in range(n_boot):
        index = rng.integers(0, n, n)
        s1, st = _jansen(fa[index], fb[index], fab[:, index])
        boot_first.append(s1)
        boot_total.append(st)

    def ci(samples: list[np.ndarray]) -> list[list[float]]:
        if not samples:
            return [[float("nan"), float("nan")]] * d
        stacked = np.array(samples)
        return [[float(np.percentile(stacked[:, i], 2.5)),
                 float(np.percentile(stacked[:, i], 97.5))] for i in range(d)]

    return {"S1": first.tolist(), "ST": total.tolist(), "S1_ci": ci(boot_first),
            "ST_ci": ci(boot_total), "n": n, "evaluations": n * (d + 2)}


def ishigami(unit: np.ndarray, a: float = 7.0, b: float = 0.1) -> np.ndarray:
    x = -math.pi + 2 * math.pi * np.asarray(unit)
    return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * x[:, 2] ** 4 * np.sin(x[:, 0])
