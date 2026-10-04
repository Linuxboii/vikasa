"""Descriptive statistics that observe but never drive evolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np

from evolution_sim.model.entities import Creature
from evolution_sim.model.genome import TRAITS, Trait


def analytical_fitness(creature: Creature) -> float:
    """Return a reporting score; the engine never reads this value."""
    return (
        creature.offspring_count * 100.0
        + creature.age * 0.01
        + creature.food_acquired * 0.5
    )


@dataclass(frozen=True, slots=True)
class MetricSample:
    tick: int
    population: int
    food: int
    births: int
    deaths: int
    total_births: int
    total_deaths: int
    diversity: float
    mean_fitness: float
    trait_mean: dict[str, float]
    trait_median: dict[str, float]
    trait_variance: dict[str, float]
    trait_std: dict[str, float]
    trait_offspring_correlation: dict[str, float | None]
    food_multiplier: float
    metabolic_multiplier: float

    def to_row(self) -> dict[str, float | int | None]:
        row: dict[str, float | int | None] = {
            "tick": self.tick,
            "population": self.population,
            "food": self.food,
            "births": self.births,
            "deaths": self.deaths,
            "total_births": self.total_births,
            "total_deaths": self.total_deaths,
            "diversity": self.diversity,
            "mean_fitness": self.mean_fitness,
            "food_multiplier": self.food_multiplier,
            "metabolic_multiplier": self.metabolic_multiplier,
        }
        for trait in (item.value for item in TRAITS):
            row[f"{trait}_mean"] = self.trait_mean[trait]
            row[f"{trait}_median"] = self.trait_median[trait]
            row[f"{trait}_variance"] = self.trait_variance[trait]
            row[f"{trait}_std"] = self.trait_std[trait]
            row[f"{trait}_offspring_correlation"] = self.trait_offspring_correlation[trait]
        return row


class MetricsRecorder:
    def __init__(self) -> None:
        self.samples: list[MetricSample] = []

    def record(self, engine: Any) -> MetricSample:
        creatures = [engine.creatures[key] for key in sorted(engine.creatures)]
        matrix = (
            np.array([creature.genome.values for creature in creatures], dtype=float)
            if creatures
            else np.empty((0, len(TRAITS)), dtype=float)
        )
        offspring = np.array([creature.offspring_count for creature in creatures], dtype=float)
        means: dict[str, float] = {}
        medians: dict[str, float] = {}
        variances: dict[str, float] = {}
        standard_deviations: dict[str, float] = {}
        correlations: dict[str, float | None] = {}
        for index, trait in enumerate(TRAITS):
            values = matrix[:, index] if len(matrix) else np.array([], dtype=float)
            name = trait.value
            means[name] = float(np.mean(values)) if len(values) else 0.0
            medians[name] = float(np.median(values)) if len(values) else 0.0
            variances[name] = float(np.var(values)) if len(values) else 0.0
            standard_deviations[name] = float(np.std(values)) if len(values) else 0.0
            if len(values) < 2 or np.var(values) == 0 or np.var(offspring) == 0:
                correlations[name] = None
            else:
                correlations[name] = round(float(np.corrcoef(values, offspring)[0, 1]), 12)
        sample = MetricSample(
            tick=engine.tick,
            population=len(creatures),
            food=len(engine.resources),
            births=engine.tick_births,
            deaths=engine.tick_deaths,
            total_births=engine.total_births,
            total_deaths=engine.total_deaths,
            diversity=self._diversity(engine, creatures),
            mean_fitness=(
                float(np.mean([analytical_fitness(creature) for creature in creatures]))
                if creatures
                else 0.0
            ),
            trait_mean=means,
            trait_median=medians,
            trait_variance=variances,
            trait_std=standard_deviations,
            trait_offspring_correlation=correlations,
            food_multiplier=engine.environment.food_multiplier,
            metabolic_multiplier=engine.environment.metabolic_multiplier,
        )
        self.samples.append(sample)
        return sample

    @staticmethod
    def _diversity(engine: Any, creatures: list[Creature]) -> float:
        if len(creatures) < 2:
            return 0.0
        maximum = engine.config.metrics.diversity_sample
        if len(creatures) > maximum:
            indexes = np.linspace(0, len(creatures) - 1, maximum, dtype=int)
            creatures = [creatures[index] for index in indexes]
        minimum = np.array(
            [engine.config.genome.traits[trait.value].minimum for trait in TRAITS]
        )
        span = np.array(
            [
                engine.config.genome.traits[trait.value].maximum
                - engine.config.genome.traits[trait.value].minimum
                for trait in TRAITS
            ]
        )
        normalized = [(creature.genome.as_array() - minimum) / span for creature in creatures]
        distances = [float(np.linalg.norm(a - b)) for a, b in combinations(normalized, 2)]
        return float(np.mean(distances)) if distances else 0.0

    def rows(self) -> list[dict[str, float | int | None]]:
        return [sample.to_row() for sample in self.samples]

    def moving_average(self, field: str, *, window: int) -> list[float]:
        if window <= 0:
            raise ValueError("window must be positive")
        values: list[float] = []
        for sample in self.samples:
            value = getattr(sample, field, None)
            if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{field} is not a numeric metric")
            values.append(float(value))
        return [
            float(np.mean(values[max(0, index - window + 1) : index + 1]))
            for index in range(len(values))
        ]

    @staticmethod
    def trait_distribution(engine: Any, trait: str | Trait) -> list[float]:
        name = trait.value if isinstance(trait, Trait) else trait
        if name not in {item.value for item in TRAITS}:
            raise ValueError(f"Unknown trait: {name}")
        return [
            engine.creatures[key].genome[Trait(name)] for key in sorted(engine.creatures)
        ]

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"samples": 0, "peak_population": 0, "final": None}
        return {
            "samples": len(self.samples),
            "peak_population": max(sample.population for sample in self.samples),
            "final": self.samples[-1].to_row(),
        }

