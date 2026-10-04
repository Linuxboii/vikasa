"""Crossover and mutation operations with explicit random generators."""

from __future__ import annotations

import numpy as np

from evolution_sim.config import GenomeConfig
from evolution_sim.model.genome import TRAITS, Genome


def crossover(
    first: Genome,
    second: Genome,
    mode: str,
    rng: np.random.Generator,
) -> Genome:
    a = first.as_array()
    b = second.as_array()
    if mode == "uniform":
        values = np.where(rng.random(len(TRAITS)) < 0.5, a, b)
    elif mode == "arithmetic":
        alpha = rng.random(len(TRAITS))
        values = alpha * a + (1.0 - alpha) * b
    else:
        raise ValueError(f"Unsupported crossover mode: {mode}")
    return Genome(tuple(float(value) for value in values))  # type: ignore[arg-type]


def mutate(genome: Genome, config: GenomeConfig, rng: np.random.Generator) -> Genome:
    values = genome.as_array()
    mask = rng.random(len(TRAITS)) < config.mutation_probability
    spans = np.array(
        [
            config.traits[trait.value].maximum - config.traits[trait.value].minimum
            for trait in TRAITS
        ]
    )
    noise = rng.normal(0.0, config.mutation_sigma, len(TRAITS)) * spans
    values[mask] += noise[mask]
    return Genome.clamped(values, config)
