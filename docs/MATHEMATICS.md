# Mathematics of Vikasa

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
