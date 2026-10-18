"""Validated, serializable configuration for the simulation."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
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


def _keys(
    data: dict[str, Any], allowed: set[str], path: str, *, optional: set[str] | None = None
) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        name = f"{path}.{unknown[0]}" if path else unknown[0]
        raise ConfigError(f"{name} is not a supported field")
    missing = sorted(allowed - set(data) - (optional or set()))
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
class DiploidArchitecture:
    """One linked chromosome, binary alleles, and bounded quantitative effects."""

    effects: tuple[tuple[float, ...], ...]
    dominance: tuple[float, ...]
    recombination: tuple[float, ...]
    founder_frequency: tuple[float, ...]
    allele_mutation_probability: float

    def __post_init__(self):
        if not isinstance(self.effects, (list, tuple)) or len(self.effects) != 6:
            raise ConfigError("genome.architecture.effects must have six rows")
        if not isinstance(self.effects[0], (list, tuple)):
            raise ConfigError("genome.architecture.effects rows must be vectors")
        loci = len(self.effects[0])
        if not 2 <= loci <= 64:
            raise ConfigError("genome.architecture must have 2 to 64 loci")
        rows = []
        for row in self.effects:
            if not isinstance(row, (list, tuple)) or len(row) != loci:
                raise ConfigError("genome.architecture.effects rows must have equal length")
            values = tuple(_number(v, "genome.architecture.effects") for v in row)
            if max(abs(v) for v in values) > 1e6 or sum(abs(v) for v in values) == 0:
                raise ConfigError("effect rows need nonzero mass and weights at most 1e6")
            rows.append(values)
        object.__setattr__(self, "effects", tuple(rows))
        for name, count, lower, upper in (
            ("dominance", loci, -1, 1), ("recombination", loci - 1, 0, .5),
            ("founder_frequency", loci, 0, 1),
        ):
            raw = getattr(self, name)
            if not isinstance(raw, (list, tuple)) or len(raw) != count:
                raise ConfigError(f"genome.architecture.{name} must have {count} entries")
            values = tuple(_number(v, f"genome.architecture.{name}") for v in raw)
            if any(not lower <= v <= upper for v in values):
                raise ConfigError(f"genome.architecture.{name} outside [{lower}, {upper}]")
            object.__setattr__(self, name, values)
        probability = _number(self.allele_mutation_probability,
                              "genome.architecture.allele_mutation_probability", minimum=0)
        if probability > 1:
            raise ConfigError("allele_mutation_probability must not exceed 1")

    @classmethod
    def from_dict(cls, raw):
        data = _mapping(raw, "genome.architecture")
        _keys(data, {"effects", "dominance", "recombination", "founder_frequency",
                     "allele_mutation_probability"}, "genome.architecture")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class GenomeConfig:
    traits: dict[str, GeneBounds]
    mutation_probability: float
    mutation_sigma: float
    crossover: str
    architecture: DiploidArchitecture | None = None


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
class BehaviorConfig:
    hysteresis_margin: float = 0.08
    softmax_temperature: float = 0.08
    dependent_age_ticks: int = 240
    care_radius: float = 24.0
    care_energy_rate: float = 0.25
    danger_preempt_threshold: float = 0.75
    territory_migration_margin: float = 0.15

    def __post_init__(self) -> None:
        for name in ("hysteresis_margin", "danger_preempt_threshold", "territory_migration_margin"):
            value = _number(getattr(self, name), f"behavior.{name}", minimum=0)
            if value > 1:
                raise ConfigError(f"behavior.{name} must not exceed 1")
        temperature = _number(
            self.softmax_temperature, "behavior.softmax_temperature", minimum=0.001
        )
        if temperature > 1:
            raise ConfigError("behavior.softmax_temperature must not exceed 1")
        age = _integer(self.dependent_age_ticks, "behavior.dependent_age_ticks", minimum=0)
        if age > 1_000_000:
            raise ConfigError("behavior.dependent_age_ticks must not exceed 1000000")
        for name, maximum in (("care_radius", 1_000_000), ("care_energy_rate", 1_000_000)):
            value = _number(getattr(self, name), f"behavior.{name}", minimum=0)
            if value > maximum:
                raise ConfigError(f"behavior.{name} must not exceed {maximum}")


@dataclass(frozen=True, slots=True)
class DemographyConfig:
    """Optional age-structured mortality; legacy files retain their original model."""

    mode: str = "fixed"
    background_hazard: float = 0.00002
    senescence_age: int = 1800
    senescence_rate: float = 0.002

    def __post_init__(self) -> None:
        if self.mode not in {"fixed", "gompertz"}:
            raise ConfigError("demography.mode must be 'fixed' or 'gompertz'")
        for name in ("background_hazard", "senescence_rate"):
            _number(getattr(self, name), f"demography.{name}", minimum=0)
        _integer(self.senescence_age, "demography.senescence_age", minimum=0)


@dataclass(frozen=True, slots=True)
class EcologyConfig:
    """Bounded dimensionless plant-water dynamics; disabled for legacy models."""

    enabled: bool = False
    columns: int = 24
    rows: int = 16
    capacity: float = 100.0
    initial_fraction: float = 0.65
    growth_rate: float = 0.006
    rainfall_rate: float = 0.004
    evaporation_rate: float = 0.002
    water_diffusion: float = 0.06
    biomass_diffusion: float = 0.008
    water_half_saturation: float = 0.25
    transpiration_rate: float = 0.03

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("ecology.enabled must be boolean")
        for name in ("columns", "rows"):
            value = _integer(getattr(self, name), f"ecology.{name}")
            if value > 64:
                raise ConfigError(f"ecology.{name} must not exceed 64")
            object.__setattr__(self, name, value)
        if _number(self.capacity, "ecology.capacity", minimum=0.001) > 1_000_000:
            raise ConfigError("ecology.capacity must not exceed 1000000 energy units per cell")
        for name in ("initial_fraction", "growth_rate", "rainfall_rate", "evaporation_rate",
                     "water_half_saturation", "transpiration_rate"):
            if _number(getattr(self, name), f"ecology.{name}", minimum=0) > 1:
                raise ConfigError(f"ecology.{name} must not exceed 1")
        for name in ("water_diffusion", "biomass_diffusion"):
            if _number(getattr(self, name), f"ecology.{name}", minimum=0) > 0.25:
                raise ConfigError(f"ecology.{name} exceeds the explicit diffusion stability limit")


def _bounded(value: Any, path: str, lower: float, upper: float, *,
             exclusive_lower: bool = False) -> float:
    result = _number(value, path)
    if result < lower or result > upper or (exclusive_lower and result == lower):
        bound = f"({lower:g}" if exclusive_lower else f"[{lower:g}"
        raise ConfigError(f"{path} must be in {bound}, {upper:g}]")
    return result


@dataclass(frozen=True, slots=True)
class ClimateConfig:
    """Optional °C climate forcing and heritable thermal tolerance; off for legacy files."""

    enabled: bool = False
    ticks_per_year: int = 384
    monthly_c: tuple[float, ...] = (25.0,) * 12
    anomaly_c: tuple[tuple[float, float], ...] = ()
    tolerance_breadth_c: float = 4.0
    warm_side_ratio: float = 0.6
    stress_metabolic_gain: float = 1.5
    stress_injury_rate: float = 0.02
    fertility_stress_limit: float = 0.7
    inheritance: str = "heritable"
    founder_mean_c: float | None = None
    founder_sd_c: float = 1.0
    segregation_sd_c: float = 0.4
    mutation_sd_c: float = 0.1

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("climate.enabled must be boolean")
        ticks = _integer(self.ticks_per_year, "climate.ticks_per_year", minimum=4)
        if ticks > 1_000_000:
            raise ConfigError("climate.ticks_per_year must not exceed 1000000")
        object.__setattr__(self, "ticks_per_year", ticks)
        if not isinstance(self.monthly_c, (list, tuple)) or len(self.monthly_c) != 12:
            raise ConfigError("climate.monthly_c must contain 12 monthly temperatures")
        object.__setattr__(self, "monthly_c", tuple(
            _bounded(value, "climate.monthly_c", -60, 60) for value in self.monthly_c))
        if not isinstance(self.anomaly_c, (list, tuple)):
            raise ConfigError("climate.anomaly_c must be a list of [year, anomaly] knots")
        knots = []
        for knot in self.anomaly_c:
            if not isinstance(knot, (list, tuple)) or len(knot) != 2:
                raise ConfigError("climate.anomaly_c knots must be [year, anomaly]")
            year = _bounded(knot[0], "climate.anomaly_c", 0, 1e9)
            if knots and year <= knots[-1][0]:
                raise ConfigError("climate.anomaly_c years must be strictly increasing")
            knots.append((year, _bounded(knot[1], "climate.anomaly_c", -30, 30)))
        object.__setattr__(self, "anomaly_c", tuple(knots))
        for name, lower, upper, exclusive in (
            ("tolerance_breadth_c", 0.1, 50, False), ("warm_side_ratio", 0.05, 1, False),
            ("stress_metabolic_gain", 0, 20, False), ("stress_injury_rate", 0, 1, False),
            ("fertility_stress_limit", 0, 1, False), ("founder_sd_c", 0, 20, False),
            ("segregation_sd_c", 0, 20, False), ("mutation_sd_c", 0, 20, False),
        ):
            object.__setattr__(self, name, _bounded(getattr(self, name), f"climate.{name}",
                                                    lower, upper, exclusive_lower=exclusive))
        if self.inheritance not in {"heritable", "none"}:
            raise ConfigError("climate.inheritance must be 'heritable' or 'none'")
        if self.founder_mean_c is not None:
            object.__setattr__(self, "founder_mean_c", _bounded(
                self.founder_mean_c, "climate.founder_mean_c", -20, 60))

    @property
    def annual_mean_c(self) -> float:
        return sum(self.monthly_c) / 12.0

    @property
    def resolved_founder_mean_c(self) -> float:
        return self.annual_mean_c if self.founder_mean_c is None else self.founder_mean_c


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
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    demography: DemographyConfig = field(default_factory=DemographyConfig)
    ecology: EcologyConfig = field(default_factory=EcologyConfig)
    climate: ClimateConfig = field(default_factory=ClimateConfig)

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
        "behavior",
        "demography",
        "ecology",
        "climate",
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
        _keys(data, cls.ROOT_KEYS, "",
              optional={"behavior", "demography", "ecology", "climate"})

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
            {"traits", "mutation_probability", "mutation_sigma", "crossover", "architecture"},
            "genome",
            optional={"architecture"},
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
        mutation_sigma = _number(genome_data["mutation_sigma"], "genome.mutation_sigma", minimum=0)
        crossover = genome_data["crossover"]
        if crossover not in {"uniform", "arithmetic"}:
            raise ConfigError("genome.crossover must be 'uniform' or 'arithmetic'")
        architecture = (DiploidArchitecture.from_dict(genome_data["architecture"])
                        if genome_data.get("architecture") is not None else None)
        genome = GenomeConfig(traits, mutation_probability, mutation_sigma, crossover, architecture)

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
        wander = _number(data["wander_change_probability"], "wander_change_probability", minimum=0)
        if wander > 1:
            raise ConfigError("wander_change_probability must not exceed 1")

        behavior_data = _mapping(data.get("behavior", {}), "behavior")
        behavior_keys = set(BehaviorConfig.__dataclass_fields__)
        _keys(behavior_data, behavior_keys, "behavior", optional=behavior_keys)
        behavior_values = dict(behavior_data)
        behavior_values.setdefault("care_energy_rate", min(0.25, energy.maximum))
        behavior = BehaviorConfig(**behavior_values)
        if behavior.care_radius > min(world.width, world.height) / 2:
            raise ConfigError(
                "behavior.care_radius must not exceed half the smaller world dimension"
            )
        if behavior.care_energy_rate > energy.maximum:
            raise ConfigError("behavior.care_energy_rate must not exceed energy.maximum")

        demography_data = _mapping(data.get("demography", {}), "demography")
        demography_keys = set(DemographyConfig.__dataclass_fields__)
        _keys(demography_data, demography_keys, "demography", optional=demography_keys)
        demography = DemographyConfig(**demography_data)
        ecology_data = _mapping(data.get("ecology", {}), "ecology")
        ecology_keys = set(EcologyConfig.__dataclass_fields__)
        _keys(ecology_data, ecology_keys, "ecology", optional=ecology_keys)
        ecology = EcologyConfig(**ecology_data)
        climate_data = _mapping(data.get("climate", {}), "climate")
        climate_keys = set(ClimateConfig.__dataclass_fields__)
        _keys(climate_data, climate_keys, "climate", optional=climate_keys)
        climate = ClimateConfig(**climate_data)

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
            behavior=behavior,
            demography=demography,
            ecology=ecology,
            climate=climate,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.genome.architecture is None:
            data["genome"].pop("architecture")
        if self.climate.enabled:
            data["climate"]["monthly_c"] = list(self.climate.monthly_c)
            data["climate"]["anomaly_c"] = [list(knot) for knot in self.climate.anomaly_c]
        else:
            # Legacy configs keep byte-identical serialization and hashes.
            data.pop("climate")
        data["genome"]["traits"] = {
            name: [bounds.minimum, bounds.maximum] for name, bounds in self.genome.traits.items()
        }
        return data
