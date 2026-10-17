"""Crossover and mutation operations with explicit random generators."""

from __future__ import annotations

import numpy as np

from evolution_sim.config import DiploidArchitecture, GenomeConfig
from evolution_sim.model.genome import TRAITS, Genome


def crossover(
    first: Genome,
    second: Genome,
    mode: str,
    rng: np.random.Generator,
    *, config: GenomeConfig | None = None,
) -> Genome:
    if config is not None and config.architecture is not None:
        return polygenic_genome((gamete(first, config.architecture, rng),
                                 gamete(second, config.architecture, rng)), config)
    if first.haplotypes is not None or second.haplotypes is not None:
        raise ValueError("Diploid crossover requires its configured architecture")
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
    if config.architecture is not None:
        if genome.haplotypes is None:
            raise ValueError("Diploid mutation requires phased haplotypes")
        alleles = np.array(genome.haplotypes, dtype=int)
        mask = rng.random(alleles.shape) < config.architecture.allele_mutation_probability
        alleles[mask] = 1 - alleles[mask]
        return polygenic_genome(tuple(tuple(int(v) for v in row) for row in alleles), config)
    if genome.haplotypes is not None:
        raise ValueError("Diploid mutation requires its configured architecture")
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


def polygenic_genome(haplotypes, config: GenomeConfig) -> Genome:
    architecture = config.architecture
    if architecture is None:
        raise ValueError("A diploid architecture is required")
    # Validate before NumPy conversion so booleans/floats cannot become alleles.
    Genome((0.,) * 6, haplotypes)
    if len(haplotypes[0]) != len(architecture.dominance):
        raise ValueError("Haplotype length differs from configured loci")
    first, second = np.array(haplotypes, dtype=float)
    dosage = (first + second) / 2 + np.array(architecture.dominance) * abs(first - second) / 2
    weights = np.array(architecture.effects)
    weights = weights / np.sum(abs(weights), axis=1)[:, None]
    normalized = .5 + weights @ (dosage - .5)
    normalized = np.clip(normalized, 0, 1)
    values = tuple(float(config.traits[t.value].minimum + normalized[i] * (
        config.traits[t.value].maximum - config.traits[t.value].minimum))
        for i, t in enumerate(TRAITS))
    return Genome(values, haplotypes)


def gamete(genome: Genome, architecture: DiploidArchitecture, rng) -> tuple[int, ...]:
    if genome.haplotypes is None or len(genome.haplotypes[0]) != len(architecture.dominance):
        raise ValueError("Meiosis requires phased haplotypes matching the architecture")
    homolog = int(rng.integers(0, 2))
    switches = rng.random(len(architecture.recombination)) < np.array(architecture.recombination)
    result = [genome.haplotypes[homolog][0]]
    for i, switch in enumerate(switches, start=1):
        homolog ^= int(switch)
        result.append(genome.haplotypes[homolog][i])
    return tuple(result)
