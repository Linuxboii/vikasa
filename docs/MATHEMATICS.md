# Mathematics of Vikasa

The optional spatial profile adds exact logistic plant growth, water-limited
transpiration, conservative finite-grid transport and audited reservoir balances.
See [Spatial Ecology](SPATIAL_ECOLOGY.md) for equations, stability bounds,
hand-derived checks, dimensionless units and limits on scientific interpretation.

This reference documents the executable model, not a biological law. Parameters are dimensionless/project-specific unless explicitly identified as ticks. The detailed caveats are in [SCIENTIFIC_MODEL.md](SCIENTIFIC_MODEL.md).

## Genome, inheritance and energy

The ordered six-gene vector is

```text
g = (size, speed, perception, metabolism, reproduction_threshold, fertility)
```

Each founder gene is uniform on its configured interval `[Lᵢ,Hᵢ]`. Arithmetic crossover draws an independent `αᵢ ~ U(0,1)` and uses `cᵢ=αᵢaᵢ+(1−αᵢ)bᵢ`; uniform crossover selects one parental allele per gene with probability 1/2. Independently per gene, a Bernoulli(`p_mutation`) draw gates `εᵢ ~ Normal(0, σ(Hᵢ−Lᵢ))`; the resulting allele is clamped to `[Lᵢ,Hᵢ]`.

Basal expenditure per tick is proportional to

```text
basal_cost × (1 + size/8) / metabolism
          × event_metabolism × seasonal_metabolism × injury_cost × health_pressure
```

Movement expenditure is proportional to

```text
movement_cost × distance × (0.5 + size/8) × (0.5 + speed/4) × weather_cost
```

Energy is clamped at the configured maximum after food gain and costs. Higher speed/size can aid access/contest strength while raising cost; greater perception expands candidate food radius but does not ensure capture. In this codebase, higher metabolism means improved basal efficiency (division by metabolism).

## Normalized drives

Let `clip(x)=min(1,max(0,x))`, `E` be current energy, `Emax` maximum energy, and `I` injury:

```text
deficit  = clip(1 − E/Emax)
survival = clip(0.65 × (1 − E/Emax) + 0.35 × I)
hunger   = max(stored_hunger, deficit)
foraging = clip(hunger × (0.5 + 0.5 × best_food_reward))   if sensed food else 0
danger   = max(local_hazard, best_threat_pressure)
```

Food reward is `clip(food_energy / max(1, 0.15×Emax)) × clip(1 − distance/perception)`. Threat pressure combines proximity, threat aggression, relative size and receiver injury, each bounded to `[0,1]`.

Mating drive is zero unless this creature and at least one perceived mate are eligible, survival is below `0.55`, and injury below `0.65`. Otherwise it is `clip((0.5+0.5E/Emax) × proximity × (0.7+0.3sociability))`, with proximity the strongest normalized mate proximity.

For each nearby dependent offspring `j`, care need is the maximum of

```text
clip(0.35 × (1 − ageⱼ/dependent_age) + 0.45 × clip(1 − energyⱼ/Emax)
     + 0.20 × max(injuryⱼ, danger)) × (0.6 + 0.4 × sociability)
```

Let `d` be distance from home center and `r` the home radius:

```text
territory = clip(0.35 + 0.65 × d/r) × (1 − 0.75×hunger) × (1 − 0.5×danger)
```

Drives are stored and displayed in fixed order: survival, foraging, mating, offspring care, danger avoidance, territory.

## Utility and arbitration

For candidate action `a`, its raw utility is the weighted affinity to the six drives, plus an action-specific reward, minus estimated cost:

```text
Uₐ = clip(Σₖ affinityₐ,ₖ × driveₖ + rewardₐ − travelₐ − exposureₐ − conflictₐ)
travel = 0.12 × clip(distance/perception) × speed/4 / metabolism
         + 0.08 × terrain_cost   (except rest)
exposure = danger × 0.05 for rest; danger × 0.25 for other actions; 0 for flee
conflict = 0.15 × danger for seek-mate
           0.30 × danger / relative-strength for challenge
           0 otherwise
```

Action affinities are implementation constants. Explore `(0.10,0.15,0,0,0,0)`, forage `(0.35,0.65,0,0,0,0)`, rest `(0.55,0,0,0,0,0)`, seek-mate `(0,0,0.65,0,0,0)`, care `(0,0,0,0.75,0,0)`, flee `(0.15,0,0,0,0.85,0)`, patrol `(0,0,0,0,0,0.65)`, challenge `(0,0,0,0,0,0.45)`. Vectors follow the drive order above. Action rewards add local food value, relief from survival pressure, dependent need, danger or territory context.

Actions are explore, forage, rest, seek mate, care, flee, patrol, and challenge. Actions without a valid opportunity are excluded. Danger at/above configured preemption threshold overrides utilities with flee. Survival pressure at/above `0.65` forces forage when possible or explore; injury at/above `0.65` forces rest. Otherwise the current action is retained if its utility is within the configured hysteresis margin of the best candidate. Remaining near-ties (within softmax temperature `τ`) use seeded probabilities

```text
P(a) = exp((Uₐ − Umax)/τ) / Σⱼ exp((Uⱼ − Umax)/τ)
```

Thus high need does not guarantee a corresponding action: opportunity, travel, danger, conflict, preemption and action persistence also matter.

## Survival, fights, reproduction, and satisfaction

Under weather pressure `H`, per-tick exposure injury is

```text
Δinjury = 0.018 × H × (1 − 0.75 × resilience) × (1 + 0.6 × hunger)
injury_next = min(1, injury + Δinjury)
```

Lethal injury remains ≥0.98; with active health pressure it is attributed to environmental exposure. With mixed causes this is an approximate attribution. Calm-weather recovery is unchanged. Existing food energy evolves as `food_energy_next = food_energy × (1 − min(0.4, decay))`; a patch below 1 energy unit is removed. Event contributions compose:

| Event (intensity `I`) | Added health pressure | Added food decay |
| --- | --- | --- |
| Drought | `0.15 × max(0, 1−I)` | `0.035 × max(0, 1−I)` |
| Heat | `0.45 × max(0, I−1)` | `0.012 × max(0, I−1)` |
| Cold | `0.25 × max(0, I−1)` | `0` |
| Storm | `0.35 × I` | `0.012 × I` |
| Flood | `0.45 × I` | `0.025 × I` |
| Wildfire | `0.8 × I` | `0.055 × I` |
| Disease | `0.4 × I` | `0` |

These are explanatory simulation coefficients. Drought intensity is food growth retained, so smaller values are harsher. Above 40 creatures, cognition is staggered across six ticks; vital processes execute every tick. Contest opportunities are sampled every four ticks, so encounter risk below is per eligible check rather than per tick.

Hunger is `clip(1−E/Emax)`. At nonpositive energy, starvation duration increases one tick; when energy is positive it decreases by one, to a floor of zero. Starvation death occurs at 12 accumulated ticks. Old age and severe injury are separate death causes.

Fight chance is low and gated by close range plus hunger pressure (at least `0.48`) or an active challenge; fleeing prevents a contest. Encounter risk is capped at `0.09` and starts with `0.004 × (0.25+pressure) × (0.3+mean_aggression)`, with a `1.5` multiplier for a challenge. For an active challenger it is multiplied by `1 + 0.75 × fights_satisfaction`, where `fights_satisfaction` is the fourth component below; ordinary maximum-pressure challenge risk therefore remains below `0.03`. Strength combines size, aggression and current energy; defense combines size and resilience. A loss causes injury and greater energy cost. Lethal risk is bounded by `0.42` and increases with low post-contest energy and injury. Victory gives alpha status and increments fight wins.

Satisfaction has four saturating components:

```text
energy   = clip(E/Emax)
offspring = 1 − exp(−offspring_count/3)
food      = 1 − exp(−food_acquired / max(1, 8×resource_energy_value))
fights    = 1 − exp(−fights_won/2)
score     = 0.34×energy + 0.18×offspring + 0.22×food + 0.26×fights
```

The fight-wins component modestly increases utility for an eligible repeat challenge and raises the low encounter risk. The scalar is an inspectable summary, not universal fitness, reproductive selection, or a selection objective.

For an eligible parent, effective mating cooldown is `max(1, round(base_cooldown × (1 − 0.5×fertility)))`. Both partners must be mutually selected, within mate radius, sufficiently old/energetic, off cooldown, and below the population cap. Each contributes half the offspring-energy amount. Three temperament traits are inherited with seeded Gaussian variation and clipping, separate from the six body genes.

## Checkpoint compatibility

Checkpoint format `vikasa` **version 3** serializes RNG state, entities, current action/drive/utility and targets, home-range/migration state, culture, event state and accumulated counters. It atomically replaces the destination after writing a flushed temporary file. **Versions 1 and 2** migrate in memory; new behavior/home fields receive migration defaults, with deterministic per-creature home-radius sampling when absent. The v3 loader strictly validates required fields and JSON integer IDs/references; loading does not rewrite the old file. An unchanged config/seed/event schedule and tick count reproduce equivalent state on the same software/numerical platform.

## Age-dependent survival

For optional Gompertz mortality, age `a` is in ticks, `mu0` is baseline hazard per
tick, `b` is inverse ticks and `a0` is the senescence onset:

```text
mu(a) = mu0 * exp(b * max(0, a-a0))
p(death in a tick | alive) = 1-exp(-mu(a))
S(A) = product over age ticks a<A of exp(-mu(a))
```

This uses a piecewise-constant per-tick hazard, not a constant probability copied
across ages. The engine computes in log space and caps hazard at 50 for numerical
safety, where survival per tick is already below 2e-22. With `mu0=0`, stochastic
senescence is disabled but starvation, injury and the hard age ceiling still apply.
The showcase uses `mu0=0.00002`, `b=0.002`, `a0=1800`; these are illustrative model
parameters. A Gompertz age schedule is a standard demographic model, not validation
for an invented species. See [mortality model research](https://pmc.ncbi.nlm.nih.gov/articles/PMC5336383/).

## Exact birth-event Price identity

For a source population of `n` living pre-birth animals, let `zi` be one trait,
`wi` its attributable offspring contribution (0.5 per child for each parent), and
`z'i` its weighted descendant mean. Nonparents have `wi=0`. Bars and covariance
use the entire source population, not only successful parents:

```text
selection    = Cov(w,z) / mean(w)
transmission = mean(w * (z'-z)) / mean(w)
total_change = sum(w*z') / sum(w) - mean(z)
residual     = total_change - selection - transmission
```

Each offspring is counted once overall despite having two parents. The identity
is exact up to floating-point rounding. Example: `z=[1,3]`, `w=[1,3]`, `z'=[2,4]`
gives selection 0.5, transmission 1.0 and total change 1.5. If total descendant
weight is zero, change is undefined, not a fabricated zero result.

For Vikasa these are birth-event observations of each inherited scalar trait;
they are not an overlapping-generation survival decomposition or an estimate of
the causal effect of a trait. Mutation, crossover and mate choice can all affect
the terms. See [Price's equation made clear](https://pmc.ncbi.nlm.nih.gov/articles/PMC7133504/)
and [the causal-analysis limitations](https://pmc.ncbi.nlm.nih.gov/articles/PMC7133506/).

## Replicate survival uncertainty

For `k` nonextinct runs out of `n` distinct seeds at a declared horizon, the study
reports `p=k/n` and a Wilson score interval, with `z=1.959963984540054`:

```text
center = (p + z²/(2n)) / (1 + z²/n)
radius = z * sqrt(p(1-p)/n + z²/(4n²)) / (1 + z²/n)
interval = [max(0,center-radius), min(1,center+radius)]
```

This avoids reporting zero uncertainty when all few runs survive or go extinct.
It assumes independent Bernoulli seed outcomes and is not a confidence statement
about a real species. Chosen demonstration seeds can bias estimates. The sampling
horizon, complete seed list, configuration and source hash must accompany results.
For the interval method and its variants, see [SciPy's statistical-method reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html).
