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
                         "traits": list(creature.genome.values)} for creature in creatures],
        "geometry": trait_geometry(cloud, [bound.minimum for bound in bounds],
                                   [bound.maximum for bound in bounds]),
        "caveat": "Living-population descriptive covariance, not additive genetic G or "
                  "heritability. PCA axes are snapshot-local; tied axes are not identifiable. "
                  "Survivorship and environment can change this distribution.",
    }
