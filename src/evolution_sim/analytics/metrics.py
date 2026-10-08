"""Descriptive statistics that observe but never drive evolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from evolution_sim.model.entities import Creature
from evolution_sim.model.genome import TRAITS, Trait


def analytical_fitness(creature: Creature) -> float:
    """Return a reporting score; the engine never reads this value."""
    return creature.offspring_count * 100.0 + creature.age * 0.01 + creature.food_acquired * 0.5


def price_decomposition(
    traits: list[float], weights: list[float], descendant_means: list[float]
) -> dict[str, float] | None:
    """Exact Price identity for a defined cohort, not a causal selection estimate.

    Weights are attributable descendant contributions. Zero-weight ancestors have
    no descendants; their descendant mean can be any finite value. An extinct or
    empty cohort has undefined evolutionary change and returns None.
    """
    z, w, descendant = (np.asarray(values, dtype=float)
                        for values in (traits, weights, descendant_means))
    if (z.ndim != 1 or w.shape != z.shape or descendant.shape != z.shape
            or not all(np.isfinite(values).all() for values in (z, w, descendant))
            or np.any(w < 0)):
        raise ValueError("Price inputs must be equal finite vectors with non-negative weights")
    if len(z) == 0 or float(np.sum(w)) == 0:
        return None
    mean_w, mean_z = float(np.mean(w)), float(np.mean(z))
    selection = float(np.mean((w - mean_w) * (z - mean_z)) / mean_w)
    transmission = float(np.sum(w * (descendant - z)) / np.sum(w))
    total = float(np.sum(w * descendant) / np.sum(w) - mean_z)
    return {"selection": selection, "transmission": transmission,
            "total_change": total, "residual": total - selection - transmission}


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
    mean_energy_ratio: float = 0.0
    mean_injury: float = 0.0
    health_pressure: float = 0.0
    temperature: float = 0.0
    rainfall: float = 0.0
    max_generation: int | None = None
    mean_generation: float | None = None
    founder_fraction: float | None = None
    juvenile_fraction: float | None = None
    mean_age: float | None = None
    plant_energy: float | None = None
    mean_water: float | None = None
    biomass_fraction: float | None = None
    grown_energy: float | None = None
    harvested_energy: float | None = None
    weather_loss: float | None = None

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
            "mean_energy_ratio": self.mean_energy_ratio,
            "mean_injury": self.mean_injury,
            "health_pressure": self.health_pressure,
            "temperature": self.temperature,
            "rainfall": self.rainfall,
            "max_generation": self.max_generation,
            "mean_generation": self.mean_generation,
            "founder_fraction": self.founder_fraction,
            "juvenile_fraction": self.juvenile_fraction,
            "mean_age": self.mean_age,
            "plant_energy": self.plant_energy,
            "mean_water": self.mean_water,
            "biomass_fraction": self.biomass_fraction,
            "grown_energy": self.grown_energy,
            "harvested_energy": self.harvested_energy,
            "weather_loss": self.weather_loss,
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
        self.birth_cohorts: list[dict[str, float | int]] = []

    def record_birth_cohort(
        self, population: dict[int, Creature], newborns: list[Creature], *, tick: int
    ) -> None:
        """Observe birth-event selection with half a descendant per parent.

        The ancestral cohort is the entire living pre-birth population. Survivors
        are not counted as offspring. This measures reproductive contributions,
        not total evolutionary change across an overlapping-generation window.
        """
        if not newborns:
            return
        ids = sorted(population)
        positions = {cid: index for index, cid in enumerate(ids)}
        weights = np.zeros(len(ids))
        descendant_sum = np.zeros((len(ids), len(TRAITS)))
        for child in newborns:
            if child.parents is None or any(p not in positions for p in child.parents):
                raise ValueError("Birth-cohort parents must belong to the source population")
            for parent in child.parents:
                index = positions[parent]
                weights[index] += 0.5
                descendant_sum[index] += 0.5 * np.asarray(child.genome.values)
        descendant_means = np.divide(descendant_sum, weights[:, None],
                                     out=np.zeros_like(descendant_sum),
                                     where=weights[:, None] > 0)
        ancestral = np.asarray([population[cid].genome.values for cid in ids])
        row: dict[str, float | int] = {
            "tick": tick, "parent_population": len(ids), "births": len(newborns)
        }
        for index, trait in enumerate(TRAITS):
            change = price_decomposition(ancestral[:, index].tolist(), weights.tolist(),
                                         descendant_means[:, index].tolist())
            if change is not None:
                row.update({f"{trait.value}_{key}": value for key, value in change.items()})
        self.birth_cohorts.append(row)
        del self.birth_cohorts[:-512]

    def restore_birth_cohorts(
        self, rows: Any, *, current_tick: int | None = None, total_births: int | None = None
    ) -> None:
        """Validate persisted observations; never silently accept malformed data."""
        if not isinstance(rows, list) or len(rows) > 512:
            raise ValueError("birth_cohorts must contain at most 512 observations")
        restored = []
        previous_tick = -1
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("birth_cohorts entries must be objects")
            for key, minimum in (("tick", 0), ("parent_population", 1), ("births", 1)):
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                    raise ValueError(f"Invalid birth_cohorts.{key}")
            if (row["tick"] <= previous_tick
                    or (current_tick is not None and row["tick"] > current_tick)):
                raise ValueError("birth_cohorts ticks must increase and not exceed the saved tick")
            if 2 * row["births"] > row["parent_population"]:
                raise ValueError("birth_cohorts births exceed the available parent pairs")
            previous_tick = row["tick"]
            for trait in TRAITS:
                for suffix in ("selection", "transmission", "total_change", "residual"):
                    value = row.get(f"{trait.value}_{suffix}")
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not math.isfinite(value)):
                        raise ValueError("birth_cohorts trait observations must be finite")
                selection = row[f"{trait.value}_selection"]
                transmission = row[f"{trait.value}_transmission"]
                total = row[f"{trait.value}_total_change"]
                residual = row[f"{trait.value}_residual"]
                tolerance = 1e-10 * max(1., abs(selection), abs(transmission), abs(total))
                if (abs(residual) > tolerance
                        or abs(total - selection - transmission - residual) > tolerance):
                    raise ValueError("birth_cohorts Price identity is inconsistent")
            restored.append(dict(row))
        if total_births is not None and sum(row["births"] for row in restored) > total_births:
            raise ValueError("birth_cohorts retained births exceed the saved total")
        self.birth_cohorts = restored

    @staticmethod
    def development(engine: Any) -> dict[str, float | int]:
        """Current observations, independent of legacy historical availability."""
        creatures = list(engine.creatures.values())
        generations = [engine.lineage.generation_of(c.id) for c in creatures]
        count = max(1, len(creatures))
        return {"max_generation": max(generations, default=0),
                "mean_generation": sum(generations) / count,
                "founder_fraction": sum(g == 0 for g in generations) / count,
                "juvenile_fraction": sum(c.age < engine.config.reproduction.minimum_age
                                         for c in creatures) / count,
                "mean_age": sum(c.age for c in creatures) / count}

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
            mean_energy_ratio=sum(max(0.0, min(1.0, c.energy / engine.config.energy.maximum))
                                  for c in creatures) / max(1, len(creatures)),
            mean_injury=sum(c.injury for c in creatures) / max(1, len(creatures)),
            health_pressure=engine.environment.health_pressure,
            temperature=engine.environment.temperature,
            rainfall=engine.environment.rainfall,
            **self.development(engine),
            **({key: engine.habitat.summary()[key] for key in
                ("plant_energy", "mean_water", "biomass_fraction", "grown_energy",
                 "harvested_energy", "weather_loss")} if engine.habitat is not None else {}),
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
        minimum = np.array([engine.config.genome.traits[trait.value].minimum for trait in TRAITS])
        span = np.array(
            [
                engine.config.genome.traits[trait.value].maximum
                - engine.config.genome.traits[trait.value].minimum
                for trait in TRAITS
            ]
        )
        normalized = (np.array([c.genome.values for c in creatures]) - minimum) / span
        delta = normalized[:, None, :] - normalized[None, :, :]
        distances = np.sqrt(np.sum(delta * delta, axis=2))
        upper = distances[np.triu_indices(len(creatures), k=1)]
        return float(np.mean(upper)) if len(upper) else 0.0

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
        return [engine.creatures[key].genome[Trait(name)] for key in sorted(engine.creatures)]

    def summary(self) -> dict[str, Any]:
        if not self.samples:
            return {"samples": 0, "peak_population": 0, "final": None}
        return {
            "samples": len(self.samples),
            "peak_population": max(sample.population for sample in self.samples),
            "final": self.samples[-1].to_row(),
        }
