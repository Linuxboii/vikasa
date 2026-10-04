# Scientific model

## Purpose

The simulator is an explanatory model of variation, inheritance, selection, and trade-offs. It is not a molecular, ecological, or population-genetics claim about a real species. Its value is that every major equation has an observable consequence and every stochastic decision is reproducible.

## State

An organism carries identity, 2D position/velocity, age, energy, genome, parents, birth tick, last reproduction tick, offspring count, and food acquired. A resource carries identity, position, radius, and energy value. Removed organisms remain represented in lineage edges and historical metrics.

## Genome and phenotype

The ordered genome is:

```text
[size, speed, perception, metabolism, reproduction_threshold, fertility]
```

Order is part of the checkpoint/export contract. Configuration provides a strict minimum and maximum for every gene. New founders sample each range uniformly.

Phenotype mappings in the UI—radius, hue, brightness, and fertility accents—do not feed back into the engine. The engine reads the original numeric genes.

## Movement

An organism queries food within its perception radius through a spatial hash. It steers toward the nearest candidate, breaking equal-distance ties by resource ID. With no sensed food, it follows a persistent wander heading that changes according to the configured probability and a seeded Gaussian turn.

Velocity approaches desired velocity by a fixed 0.3 steering factor and is capped by the speed gene. Collision boundaries clamp position and reflect the corresponding velocity component. The optional wrap boundary applies coordinate modulo.

## Energy

Basal and movement costs are:

```text
basal = basal_cost × (1 + size/8) ÷ metabolism × environment_multiplier
movement = movement_cost × distance × (0.5 + size/8) × (0.5 + speed/4)
```

Food increases energy up to `energy.maximum`. Contention for a resource is resolved by squared distance and then stable organism ID. A resource can be consumed once.

## Reproduction

Both parents must satisfy minimum age, their own reproduction-threshold gene, the effective cooldown, mate radius, and the population cap.

```text
effective_cooldown = round(base_cooldown × (1 - 0.5 × fertility))
```

Pairs are chosen by stable organism order and nearest eligible mate. Each parent contributes half the configured offspring energy. The child receives arithmetic or uniform crossover, then mutation, and starts near the parental midpoint. Both parent IDs and the birth tick are recorded.

## Mutation

For every child gene, a seeded Bernoulli trial decides whether mutation occurs. Applied noise is:

```text
Normal(0, mutation_sigma) × (gene_maximum - gene_minimum)
```

The result is clamped. Mutation therefore never violates the configured simulation range.

## Environment

Events are deterministic functions of tick and configuration. Drought and abundance multiply food spawn rate; heat multiplies basal cost. `redistribute` is versioned and exported but does not alter equations in v1.0.

Overlapping multipliers compose. An event is active in the half-open interval from start tick through the tick before its end.

## Statistics

At each sample interval, the recorder stores population, food, births, deaths, cumulative vital events, normalized pairwise genome diversity, analytical fitness, environmental multipliers, and mean/median/population variance/population standard deviation for every gene.

Trait/offspring Pearson correlation is recorded only when at least two values exist and both variables have non-zero variance. Otherwise it is `null`, not a fabricated zero.

For large populations, diversity uses evenly spaced organisms from stable ID order up to the configured sample size. Each genome dimension is normalized to its configured span before Euclidean distance is calculated.

## Determinism

- One NumPy `Generator(PCG64)` owns all simulation randomness.
- Stable IDs order updates and break conflicts.
- Wall-clock time never enters state.
- Checkpoints preserve RNG state and fractional food-spawn remainder.
- Rendering reads snapshots and commands but never chooses outcomes.

Equal configuration, seed, event schedule, tick count, and version produce equivalent canonical summaries on the same numerical platform.

## Interpretation limits

- One seeded run is illustrative, not statistical evidence.
- Analytical fitness is descriptive and scale-dependent.
- The ecology has one resource type and no predation.
- Genes are haploid quantitative values; there is no dominance, recombination map, or molecular DNA.
- Selection can be confounded by finite population drift and the initial random sample.
- Compare treatments with matched seeds and multiple replicates, then report distributions rather than a preferred screenshot.

