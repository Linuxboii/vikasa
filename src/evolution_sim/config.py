"""Validated, serializable configuration for the simulation."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar


class ConfigError(ValueError):
    """Raised when a configuration value violates the public contract."""


TRAIT_NAMES = (
    "size",
    "speed",
    "perception",
    "metabolism",
    "reproduction_threshold",
    "fertility",
)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be an object")
    return value


def _keys(data: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        name = f"{path}.{unknown[0]}" if path else unknown[0]
        raise ConfigError(f"{name} is not a supported field")
    missing = sorted(allowed - set(data))
    if missing:
        name = f"{path}.{missing[0]}" if path else missing[0]
        raise ConfigError(f"{name} is required")


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ConfigError(f"{path} must be a finite number")
    if minimum is not None and result < minimum:
        raise ConfigError(f"{path} must be at least {minimum:g}")
    return result


def _integer(value: Any, path: str, *, minimum: int = 1) -> int:
    result = _number(value, path, minimum=float(minimum))
    if not result.is_integer():
        raise ConfigError(f"{path} must be an integer")
    return int(result)


@dataclass(frozen=True, slots=True)
class GeneBounds:
    minimum: float
    maximum: float

    @classmethod
    def parse(cls, value: Any, path: str) -> GeneBounds:
        if not isinstance(value, list) or len(value) != 2:
            raise ConfigError(f"{path} must be [minimum, maximum]")
        minimum = _number(value[0], f"{path}[0]")
        maximum = _number(value[1], f"{path}[1]")
        if minimum >= maximum:
            raise ConfigError(f"{path} minimum must be less than maximum")
        return cls(minimum, maximum)


@dataclass(frozen=True, slots=True)
class WorldConfig:
    width: int
    height: int
    boundary: str


@dataclass(frozen=True, slots=True)
class GenomeConfig:
    traits: dict[str, GeneBounds]
    mutation_probability: float
    mutation_sigma: float
    crossover: str


@dataclass(frozen=True, slots=True)
class EnergyConfig:
    initial: float
    basal_cost: float
    movement_cost: float
    maximum: float


@dataclass(frozen=True, slots=True)
class ReproductionConfig:
    minimum_age: int
    cooldown: int
    mate_radius: float
    offspring_energy: float
    population_cap: int


@dataclass(frozen=True, slots=True)
class ResourceConfig:
    initial_count: int
    spawn_rate: float
    maximum_count: int
    energy_value: float


@dataclass(frozen=True, slots=True)
class MetricsConfig:
    sample_interval: int
    diversity_sample: int


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    world: WorldConfig
    genome: GenomeConfig
    energy: EnergyConfig
    reproduction: ReproductionConfig
    resources: ResourceConfig
    metrics: MetricsConfig
    initial_population: int
    maximum_age: int
    wander_change_probability: float

    ROOT_KEYS: ClassVar[set[str]] = {
        "world",
        "genome",
        "energy",
        "reproduction",
        "resources",
        "metrics",
        "initial_population",
        "maximum_age",
        "wander_change_probability",
    }

    @classmethod
    def from_json(cls, path: str | Path) -> SimulationConfig:
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"Could not read configuration {source}: {exc}") from exc
        return cls.from_dict(_mapping(data, "config"))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SimulationConfig:
        data = _mapping(raw, "config")
        _keys(data, cls.ROOT_KEYS, "")

        world_data = _mapping(data["world"], "world")
        _keys(world_data, {"width", "height", "boundary"}, "world")
        boundary = world_data["boundary"]
        if boundary not in {"collision", "wrap"}:
            raise ConfigError("world.boundary must be 'collision' or 'wrap'")
        world = WorldConfig(
            _integer(world_data["width"], "world.width", minimum=64),
            _integer(world_data["height"], "world.height", minimum=64),
            boundary,
        )

        genome_data = _mapping(data["genome"], "genome")
        _keys(
            genome_data,
            {"traits", "mutation_probability", "mutation_sigma", "crossover"},
            "genome",
        )
        traits_data = _mapping(genome_data["traits"], "genome.traits")
        _keys(traits_data, set(TRAIT_NAMES), "genome.traits")
        traits = {
            name: GeneBounds.parse(traits_data[name], f"genome.traits.{name}")
            for name in TRAIT_NAMES
        }
        mutation_probability = _number(
            genome_data["mutation_probability"], "genome.mutation_probability", minimum=0
        )
        if mutation_probability > 1:
            raise ConfigError("genome.mutation_probability must not exceed 1")
        mutation_sigma = _number(
            genome_data["mutation_sigma"], "genome.mutation_sigma", minimum=0
        )
        crossover = genome_data["crossover"]
        if crossover not in {"uniform", "arithmetic"}:
            raise ConfigError("genome.crossover must be 'uniform' or 'arithmetic'")
        genome = GenomeConfig(traits, mutation_probability, mutation_sigma, crossover)

        energy_data = _mapping(data["energy"], "energy")
        _keys(energy_data, {"initial", "basal_cost", "movement_cost", "maximum"}, "energy")
        energy = EnergyConfig(
            _number(energy_data["initial"], "energy.initial", minimum=0.001),
            _number(energy_data["basal_cost"], "energy.basal_cost", minimum=0),
            _number(energy_data["movement_cost"], "energy.movement_cost", minimum=0),
            _number(energy_data["maximum"], "energy.maximum", minimum=0.001),
        )
        if energy.initial > energy.maximum:
            raise ConfigError("energy.initial must not exceed energy.maximum")

        reproduction_data = _mapping(data["reproduction"], "reproduction")
        _keys(
            reproduction_data,
            {"minimum_age", "cooldown", "mate_radius", "offspring_energy", "population_cap"},
            "reproduction",
        )
        reproduction = ReproductionConfig(
            _integer(reproduction_data["minimum_age"], "reproduction.minimum_age", minimum=0),
            _integer(reproduction_data["cooldown"], "reproduction.cooldown", minimum=0),
            _number(reproduction_data["mate_radius"], "reproduction.mate_radius", minimum=0),
            _number(
                reproduction_data["offspring_energy"],
                "reproduction.offspring_energy",
                minimum=0.001,
            ),
            _integer(reproduction_data["population_cap"], "reproduction.population_cap"),
        )

        resource_data = _mapping(data["resources"], "resources")
        _keys(
            resource_data,
            {"initial_count", "spawn_rate", "maximum_count", "energy_value"},
            "resources",
        )
        resources = ResourceConfig(
            _integer(resource_data["initial_count"], "resources.initial_count", minimum=0),
            _number(resource_data["spawn_rate"], "resources.spawn_rate", minimum=0),
            _integer(resource_data["maximum_count"], "resources.maximum_count", minimum=0),
            _number(resource_data["energy_value"], "resources.energy_value", minimum=0.001),
        )
        if resources.initial_count > resources.maximum_count:
            raise ConfigError("resources.initial_count must not exceed resources.maximum_count")

        metrics_data = _mapping(data["metrics"], "metrics")
        _keys(metrics_data, {"sample_interval", "diversity_sample"}, "metrics")
        metrics = MetricsConfig(
            _integer(metrics_data["sample_interval"], "metrics.sample_interval"),
            _integer(metrics_data["diversity_sample"], "metrics.diversity_sample", minimum=2),
        )

        initial_population = _integer(data["initial_population"], "initial_population")
        if initial_population > reproduction.population_cap:
            raise ConfigError("initial_population must not exceed reproduction.population_cap")
        wander = _number(
            data["wander_change_probability"], "wander_change_probability", minimum=0
        )
        if wander > 1:
            raise ConfigError("wander_change_probability must not exceed 1")

        return cls(
            world=world,
            genome=genome,
            energy=energy,
            reproduction=reproduction,
            resources=resources,
            metrics=metrics,
            initial_population=initial_population,
            maximum_age=_integer(data["maximum_age"], "maximum_age"),
            wander_change_probability=wander,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["genome"]["traits"] = {
            name: [bounds.minimum, bounds.maximum] for name, bounds in self.genome.traits.items()
        }
        return data

