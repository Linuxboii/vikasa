# Scientific model

## Scope

Vikasa is an explanatory artificial-life model for exploring variation, resource pressure, behavior, inheritance and survival. It is not calibrated to a real species or a validated ecological forecast. Each tick is an abstract step with no fixed conversion to seconds, days, or generations.

## Organism and inheritance

The ordered body genome is `[size, speed, perception, metabolism, reproduction_threshold, fertility]`; each value is bounded by configuration. Founder values are sampled uniformly. Mating uses the configured arithmetic or uniform crossover, followed by independent per-gene mutation, `Normal(0, sigma × gene span)` when the Bernoulli mutation trial succeeds, then clamping to configured bounds.

Aggression, resilience, and sociability are separate inherited behavioral traits rather than extra body-gene coordinates. Their offspring values combine parental values with seeded Gaussian variation and are clamped to `[0, 1]`. Larger/faster creatures incur higher costs; perception expands sensing but does not guarantee access; metabolism changes basal cost; fertility shortens cooldown but does not guarantee a mate or child.

## Tick and action arbitration

The engine updates seasonal and scheduled environment pressures, regenerates resources, constructs spatial indexes, forms local perceptions, decides/executes actions, resolves fights, resolves food contention, resolves paired reproduction, applies deaths, advances the tick, then updates culture, satisfaction, and sampled metrics.

Six normalized drives are recalculated from current reserves, injury, nearby opportunities, dependents, threats, hazards, home-range displacement and temperament: survival, foraging, mating, offspring care, danger avoidance, territory. They feed eight candidate actions: explore, forage, rest, seek mate, care, flee, patrol, and challenge. Each action's utility is a bounded drive-affinity reward minus travel, exposure, and conflict costs. Unavailable actions are excluded. Danger at or above threshold preempts with flight; critical survival/injury pressure preempts with foraging/rest. Otherwise hysteresis preserves a current action when close to the best score, and seeded softmax breaks near ties. Selection is reproducible for a fixed engine state and RNG stream.

## Energy, food, and mortality

Weather now erodes existing food under drought, heat, storm, flood and wildfire, removing patches below 1 energy unit. Exposure adds `0.018 × health_pressure × (1 − 0.75 × resilience) × (1 + 0.6 × hunger)` injury per tick. Injury ≥0.98 during active health pressure is labeled environmental exposure, otherwise fight injuries; attribution is approximate when causes overlap. Food consumption uses the patch's remaining energy.

Food supplies a configured energy amount and can be consumed only once; competing organisms resolve access by squared distance then stable ID. Basal and movement expenditure depend on traits and current environment/weather costs. Hunger rises as energy falls. Energy at or below zero increments a starvation counter; positive energy reduces the counter by one each tick. Death occurs after 12 accumulated starvation ticks, at configured maximum age, or at severe fight injury. Thus starvation is delayed and potentially reversible, not a single-tick deletion.

Reproduction requires both partners to meet age, energy threshold and cooldown requirements, be in mate range, mutually select each other, and remain under the population cap. Each parent invests half the configured offspring energy. Children inherit body genome and behavioral temperament; parentage and birth ticks remain in lineage records after deaths.

## Home range, care and migration

Each creature has a center and radius for a small home range. Patrol actions choose a persistent waypoint near the range edge. Parents can care for living offspring younger than the configured dependent age and within care radius; care transfers limited energy while protecting a parent reserve. If an animal remains outside its range while foraging and perceived outside food reward exceeds inside reward by the configured migration margin, its center shifts toward its position by 0.5% after 24 consecutive qualifying ticks. The rule is a small local-resource response, not a realistic dispersal model.

## Conflict and satisfaction

Close encounters only roll for fights under hunger pressure or an explicit challenge, and flee suppresses the encounter. Aggression modulates a low baseline probability; size, energy, and resilience affect winning. Winners gain alpha status; both participants pay energy, the loser gains injury, and a weakened/injured loser has a bounded nonzero fatal chance. There is no permanent rank hierarchy: alpha is a retained victory marker, and challengers must still meet behavioral opportunity/risk conditions.

The four satisfaction components are energy security, saturating offspring history, saturating food acquired, and saturating fight wins. Their current weighted scalar is `0.34 energy + 0.18 offspring + 0.22 food + 0.26 fights`. The fight-wins component modestly lifts utility for eligible repeat challenges and raises the still-low encounter chance for active challengers; winning gives alpha status. Satisfaction is not a global evolutionary fitness function or a measure of subjective welfare.

## Environment and shared traditions

The showcase uses 64 founders, an 180-animal cap and seeded age-dependent mortality with a 12,000-tick hard ceiling. The earlier 1,100-tick cutoff produced a founder die-off and is preserved in `config/extinction-control.json` for comparison. Drought intensity is a food-growth multiplier below 1, reducing rainfall and increasing metabolic cost. Other hazard intensities increase pressure; heat/cold alter temperature and storms increase rainfall. Sustained hazards can injure and kill within a 160-tick experiment. Coefficients are illustrative; wildfire represents whole-biome exposure rather than a moving fire front, and disease is pressure rather than explicit contagion.

## Age structure and quantitative evolutionary observations

Optional `demography.mode="gompertz"` applies a per-tick piecewise-constant hazard
`mu(a)=background_hazard*exp(senescence_rate*max(0,a-senescence_age))`, with probability
`1-exp(-mu(a))`. A seeded uniform draw decides mortality after injury/starvation
checks. The hard age ceiling remains. Missing demography settings retain the fixed
model and consume no extra mortality draws. The Gompertz form is an illustrative
age schedule, not an empirically fitted lifespan for these invented organisms.

Living generation is maximum ancestral depth, not a discrete temporal cohort.
An animal is generation zero if it has no recorded parents; otherwise its depth
is one plus the maximum parent depth. Ancestry remains after deaths. Mean living
depth, founder fraction, juvenile fraction and mean age expose actual renewal.

Each birth event observes all pre-birth living animals. Each offspring contributes
half a descendant weight to each parent. Six-trait Price terms separate the shift
in reproductive contributions from offspring-parent trait differences. These
include mating opportunity and transmission effects; the identity alone does not
identify causal selection or prove adaptation. Survival between birth events is
not included. The GUI labels this scope and retains at most 180 recent cohorts;
checkpoints/exports retain at most 512. See the mathematical derivation and
[research status](RESEARCH_STATUS.md) for the full upgrade's remaining scope.

Seasons advance every 96 ticks, changing temperature, rainfall, food productivity and metabolic demand. Scheduled drought/abundance alter food supply; heat/cold change metabolism and health pressure; storms affect movement and pressure; flood/wildfire alter food and pressure; disease adds health pressure. These values are deliberately coarse. There is no fluid simulation, terrain-dependent ecology, explicit contagion graph, or detailed resource-food web.

Repeated shared cues (season turns, drought, heat, storms, or victories) can accumulate observations. With sufficient repeated signals and exposed living population, a seeded chance can found a named tradition; low-probability contact spreads affiliation, and gatherings can record rituals. Names/practices come from a small fixed vocabulary. This demonstrates rule-based cultural transmission only; it does not model language, agency, theology, symbolic reasoning, or human religion. A tradition may not emerge in a particular run.

## Determinism and evidence

Above 40 creatures, intent decisions are staggered by `(tick + creature_id) % 6` after the initial tick. Movement and vital processes still advance each tick. Combat opportunities are evaluated every four ticks. These schedules are deterministic and apply to GUI and headless runs equally. The changed coefficients/schedules change trajectories relative to older software versions even for the same seed.

One NumPy PCG64 generator owns stochastic outcomes. Stable IDs order updates and ties; rendering reads snapshots only. Checkpoint version 3 stores RNG state and fractional resource-spawn remainder and can continue bit-for-bit on the same software/numerical platform. Loader migrations from versions 1 and 2 are in-memory. See [architecture and compatibility](ARCHITECTURE.md#persistence-and-reproducibility).

Population and trait changes alone do not prove adaptation. Compare replicated, matched-seed treatments and inspect actual offspring inheritance and survival. Report config, version, seed set, tick count, event timing, extinction, invariant errors and distributions. For a compact experiment recipe, see [EXPERIMENTS.md](EXPERIMENTS.md).
