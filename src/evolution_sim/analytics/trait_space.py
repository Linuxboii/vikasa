"""Snapshot geometry of inherited traits; never consulted by the engine."""

from __future__ import annotations

import numpy as np


def trait_geometry(points, minima, maxima) -> dict:
    """Sample covariance/PCA after scaling each trait by its configured span.

    Eigenvectors are columns, scores retain input row order. Tied axes have no
    unique orientation; even unique axes are local to this snapshot.
    """
    cloud = np.asarray(points, dtype=float)
    lower, upper = np.asarray(minima, dtype=float), np.asarray(maxima, dtype=float)
    if (cloud.ndim != 2 or cloud.shape[1] != 6 or lower.shape != (6,)
            or upper.shape != (6,) or not np.isfinite(cloud).all()
            or not np.isfinite(lower).all() or not np.isfinite(upper).all()
            or np.any(upper <= lower) or np.any(cloud < lower)
            or np.any(cloud > upper)):
        raise ValueError("Expected a finite bounded n-by-6 cloud and six increasing bounds")
    with np.errstate(over="ignore"):
        spans = upper - lower
    if not np.isfinite(spans).all():
        raise ValueError("Trait spans must be finite")
    normalized = (cloud - lower) / spans
    edges = np.linspace(0, 1, 13)
    result = {
        "population": len(cloud),
        "normalized_mean": normalized.mean(axis=0).tolist() if len(cloud) else None,
        "histogram_edges": edges.tolist(),
        "histograms": [np.histogram(normalized[:, i], bins=edges)[0].tolist()
                       for i in range(6)],
        "covariance": None, "correlation": None, "eigenvalues": None,
        "loadings": None, "scores": None, "explained_fraction": None,
        "effective_dimension": None, "degenerate_axes": False,
    }
    if len(cloud) < 2:
        return result
    # A reference offset preserves exact zero in constant decimal columns.
    offsets = normalized - normalized[0]
    centered = offsets - offsets.mean(axis=0)
    covariance = centered.T @ centered / (len(cloud) - 1)
    eigenvalues, vectors = np.linalg.eigh(covariance)
    eigenvalues, vectors = np.maximum(eigenvalues[::-1], 0), vectors[:, ::-1]
    for i in range(6):
        if vectors[np.argmax(np.abs(vectors[:, i])), i] < 0:
            vectors[:, i] *= -1
    variance = np.diag(covariance)
    deviations = np.sqrt(variance)
    correlation = [[float(np.clip(covariance[i, j] / deviations[i] / deviations[j],
                                  -1, 1)) if variance[i] > 0 and variance[j] > 0 else None
                    for j in range(6)] for i in range(6)]
    total = float(eigenvalues.sum())
    fractions = eigenvalues / total if total > 0 else None
    positive = eigenvalues[eigenvalues > total * 1e-12]
    result.update(
        covariance=covariance.tolist(), correlation=correlation,
        eigenvalues=eigenvalues.tolist(), loadings=vectors.tolist(),
        scores=(centered @ vectors).tolist(),
        explained_fraction=fractions.tolist() if fractions is not None else None,
        effective_dimension=float(1 / (fractions @ fractions)) if fractions is not None else None,
        degenerate_axes=bool(any(np.isclose(positive[i], positive[i + 1], rtol=1e-8, atol=0)
                                 for i in range(len(positive) - 1))),
    )
    return result


def engine_trait_space(engine) -> dict:
    """Join geometry to stable creature identities without consuming any RNG."""
    from evolution_sim.model.genome import TRAITS

    creatures = [engine.creatures[key] for key in sorted(engine.creatures)]
    bounds = [engine.config.genome.traits[trait.value] for trait in TRAITS]
    cloud = np.array([creature.genome.values for creature in creatures]).reshape(-1, 6)
    return {
        "version": 1, "seed": engine.seed, "tick": engine.tick,
        "traits": [trait.value for trait in TRAITS],
        "minima": [bound.minimum for bound in bounds],
        "maxima": [bound.maximum for bound in bounds],
        "individuals": [{"id": creature.id,
                         "generation": engine.lineage.generation_of(creature.id),
                         "birth_tick": creature.birth_tick,
                         "haplotypes": creature.genome.haplotypes,
                         "traits": list(creature.genome.values)} for creature in creatures],
        "population_genetics": (population_genetics(
            [c.genome.haplotypes for c in creatures],
            loci=len(engine.config.genome.architecture.dominance))
            if engine.config.genome.architecture is not None else None),
        "geometry": trait_geometry(cloud, [bound.minimum for bound in bounds],
                                   [bound.maximum for bound in bounds]),
        "caveat": "Living-population descriptive covariance, not additive genetic G or "
                  "heritability. PCA axes are snapshot-local; tied axes are not identifiable. "
                  "Survivorship and environment can change this distribution.",
    }


def population_genetics(haplotypes, *, loci=None) -> dict:
    """Phased binary-locus frequencies and descriptive linkage disequilibrium."""
    cloud = np.asarray(haplotypes)
    if cloud.size == 0 and loci is not None:
        cloud = np.empty((0, 2, loci), dtype=int)
    if (cloud.ndim != 3 or cloud.shape[1] != 2 or not 2 <= cloud.shape[2] <= 64
            or cloud.dtype.kind not in "iu" or np.any((cloud != 0) & (cloud != 1))):
        raise ValueError("Expected n-by-2-by-loci phased binary alleles")
    count, _, loci = cloud.shape
    result = {"individuals": count, "loci": loci, "allele_frequency": None,
              "observed_heterozygosity": None, "expected_heterozygosity": None,
              "linkage_d": None, "linkage_r_squared": None}
    if count == 0:
        return result
    chromosomes = cloud.reshape(-1, loci).astype(float)
    frequency = chromosomes.mean(axis=0)
    centered = chromosomes - frequency
    linkage = centered.T @ centered / len(chromosomes)
    variance = frequency * (1 - frequency)
    r_squared = [[float(np.clip(linkage[i, j]**2 / variance[i] / variance[j], 0, 1))
                  if variance[i] > 0 and variance[j] > 0 else None
                  for j in range(loci)] for i in range(loci)]
    result.update(allele_frequency=frequency.tolist(),
                  observed_heterozygosity=(cloud[:, 0] != cloud[:, 1]).mean(axis=0).tolist(),
                  expected_heterozygosity=(2 * variance).tolist(),
                  linkage_d=linkage.tolist(), linkage_r_squared=r_squared)
    return result
