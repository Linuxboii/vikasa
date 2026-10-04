"""Genome representation and seeded population initialization."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from evolution_sim.config import GenomeConfig


class Trait(StrEnum):
    SIZE = "size"
    SPEED = "speed"
    PERCEPTION = "perception"
    METABOLISM = "metabolism"
    REPRODUCTION_THRESHOLD = "reproduction_threshold"
    FERTILITY = "fertility"


TRAITS = tuple(Trait)


@dataclass(frozen=True, slots=True)
class Genome:
    """A stable, immutable vector of quantitative inheritable traits."""

    values: tuple[float, float, float, float, float, float]

    def __post_init__(self) -> None:
        if len(self.values) != len(TRAITS):
            raise ValueError(f"Genome needs exactly {len(TRAITS)} traits")
        if not all(math.isfinite(value) for value in self.values):
            raise ValueError("Genome values must be finite")

    def __getitem__(self, trait: Trait) -> float:
        return self.values[TRAITS.index(trait)]

    def as_array(self) -> NDArray[np.float64]:
        return np.asarray(self.values, dtype=np.float64).copy()

    def to_mapping(self) -> dict[str, float]:
        return {trait.value: self.values[index] for index, trait in enumerate(TRAITS)}

    @classmethod
    def from_mapping(cls, raw: Mapping[str, float], config: GenomeConfig) -> Genome:
        expected = {trait.value for trait in TRAITS}
        if set(raw) != expected:
            missing = sorted(expected - set(raw))
            extra = sorted(set(raw) - expected)
            raise ValueError(f"Genome keys differ; missing={missing}, extra={extra}")
        values: list[float] = []
        for trait in TRAITS:
            value = float(raw[trait.value])
            bounds = config.traits[trait.value]
            if not math.isfinite(value) or not bounds.minimum <= value <= bounds.maximum:
                raise ValueError(
                    f"{trait.value}={value!r} outside [{bounds.minimum}, {bounds.maximum}]"
                )
            values.append(value)
        return cls(tuple(values))  # type: ignore[arg-type]

    @classmethod
    def clamped(cls, values: NDArray[np.float64], config: GenomeConfig) -> Genome:
        source = np.asarray(values, dtype=np.float64)
        if source.shape != (len(TRAITS),) or not np.isfinite(source).all():
            raise ValueError("Genome vector must contain six finite values")
        minimum = np.array([config.traits[trait.value].minimum for trait in TRAITS])
        maximum = np.array([config.traits[trait.value].maximum for trait in TRAITS])
        result = np.clip(source, minimum, maximum)
        return cls(tuple(float(value) for value in result))  # type: ignore[arg-type]


def random_genome(config: GenomeConfig, rng: np.random.Generator) -> Genome:
    minimum = np.array([config.traits[trait.value].minimum for trait in TRAITS])
    maximum = np.array([config.traits[trait.value].maximum for trait in TRAITS])
    values = rng.uniform(minimum, maximum)
    return Genome(tuple(float(value) for value in values))  # type: ignore[arg-type]

