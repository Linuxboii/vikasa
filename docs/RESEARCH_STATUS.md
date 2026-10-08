# Research upgrade: evidence and open work

Vikasa is being developed into an inspectable eco-evolutionary research platform.
The goal is sustained development, mechanistic depth, reproducible experiments and
a presentation that explains the science. It is not yet a validated species model,
a PhD thesis, or evidence of a novel scientific discovery. Those claims require
empirical validation, a defined research question and independent review.

## Extinction diagnosis, 2026-10-08

The former showcase, preserved as `config/extinction-control.json`, reached zero
animals by tick 3,000 for seed 2026: only 25 births, 69 old-age deaths and 20
starvation deaths. At tick 1,500 only 11 animals remained. Founders began at similar
ages and a hard age limit removed most of them before they could be replaced.
Encounter density, neonatal reserves and resource production also constrained
replacement. This was a lifecycle imbalance, not a missing immortality switch.

The new showcase uses a 720×480 world, 64 founders, 180-animal cap, 125 founder
reserve energy, 60 newborn reserve energy, 90-unit mating radius and 0.9 resource
patches per tick before seasonal modulation. Resources still have a finite cap,
and animals still pay maintenance, locomotion and reproductive energy costs.
Each parent contributes half the newborn's initial energy. There is no immigration,
population rescue, automatic restart, or death suppression.

Mortality now uses a seeded age-dependent hazard with a 12,000-tick hard safety
ceiling. The ceiling is not the usual lifespan. Old configuration files retain
fixed-age mortality; both models remain available for controlled comparison.

## Implemented foundation

Three exploratory seeds have completed 12,000 ticks with the new showcase:

The standardized [development report](results/development-study-2026-10-08.json)
and [extinction control report](results/extinction-control-study-2026-10-08.json)
retain all replicate trajectories, configurations, source hashes and invariant
checks. Both ran against the same frozen source tree before the subsequent
observer/save-validation fixes; their hashes are historical, not the current
checkout hash. These fixes do not change the biological rules or RNG draws.

| Seed | Living animals | Actual births | Living ancestral depth | Deaths: starvation / senescence / fights |
|---|---:|---:|---:|---|
| 2026 | 123 | 799 | 23 | 560 / 142 / 38 |
| 7 | 117 | 720 | 23 | 478 / 154 / 35 |
| 41 | 114 | 717 | 20 | 477 / 158 / 32 |

These are selected exploratory seeds and a finite horizon, not a promise of
indefinite survival. Population identity holds: founders + births - deaths equals
the living count. Severe perturbations may still cause extinction. A larger
predeclared seed set and sensitivity/ablation studies remain necessary.
All three revised runs passed invariant checks; the 95% Wilson interval for
survival is [0.4385, 1.0000], reflecting substantial uncertainty with only three
selected seeds. The control interval is [0.0000, 0.5615].

- Generation depth survives the death of ancestors and checkpoint restoration.
  The GUI reports deepest/mean living generation, founder share, young share and age.
- Every actual birth event records an exact six-trait Price decomposition using
  half a descendant contribution per parent and the entire pre-birth population.
  Selection/transmission are accounting terms, not automatic proof of adaptation.
- Older saves retain unavailable historical development fields as null; graphs
  leave gaps and current development is computed from restored living entities.
  Persisted birth histories are checked for time ordering, counter consistency,
  available parent pairs and the Price identity. Irregular-event hover labels use
  actual tick distances. Study reports reject source changes during execution.
- The Evolution tab plots signed birth-cohort change, generational depth and renewal.
  Charts use real records; missing birth data is not fabricated.
- Checkpoints retain the last 512 birth cohorts, and `evolution.json` exports them.
  `creatures.csv` includes generation depth. The record limit is explicit; it is
  not a full-lifetime event archive.
- Automated tests cover the extinction regression, age-hazard behavior, repeatable
  mortality, exact Price identities, negative chart axes, lineage depth, persisted
  cohorts and exports.
- The `study` command records all selected seeds, exact extinction times, sampled
  trajectories, invariant errors, source/config hashes and a Wilson survival
  interval. It does not silently discard extinct runs. Selected seeds can bias
  the inference; the report explicitly states that limitation.

## Reproduce a development study

The preserved control configuration went extinct at ticks 2,870 (seed 2026),
2,589 (seed 7) and 2,265 (seed 41), with no rescue or restart. This is a
multi-parameter comparison, not a causal estimate for any single coefficient.

From the repository root on Windows (the 12,000-tick study can take tens of minutes on a busy machine):

```powershell
.\.venv\Scripts\python.exe -m evolution_sim.cli study --config config/showcase.json --seeds 2026 7 41 --ticks 12000 --output exports/development-study.json
.\.venv\Scripts\python.exe -m evolution_sim.cli study --config config/extinction-control.json --seeds 2026 7 41 --ticks 12000 --output exports/extinction-control-study.json
```

On macOS/Linux replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.
Keep reports alongside source/config versions. Identical seed labels across changed
models do not guarantee identical random draws after changed branching behavior.
There is no causal ablation claim for this multi-parameter showcase change.

## Full requested upgrade remains active

| Research dimension | Required end state | Current evidence / gap |
|---|---|---|
| Sustained development | Long-horizon replicated runs with genuine reproduction, generational turnover and transparent extinction risk | 6,000-tick regression passes and three 12,000-tick probes persist; larger predeclared seed-set/horizon and sensitivity analysis still needed |
| Mechanistic ecology | Spatial renewable biomass, water/nutrients, localized exposure, refuges, resource competition and explicit disease transmission | Current global weather/patch-spawn model remains simplified |
| Quantitative genetics | Inspectable inheritance, trait covariance, constrained trade-offs, plasticity and measurements distinguishing drift, selection and transmission | Six inherited scalar traits and exact birth-event decomposition; multilocus/covariance mechanisms still needed |
| Behavioral development | Energy-budget lifecycle, learned local information and defensible social/cultural transmission | Existing fixed utility behavior/care remains; learning and richer lifecycle mechanisms still needed |
| Scientific visualization | Lineage exploration, developmental life stages, ecological heatmaps, trait distributions, historical comparisons and clear controls | Generation/Price graphs implemented; deeper exploration and spatial overlays still needed |
| Experiment laboratory | Replicates, perturbation/ablation studies, sensitivity analysis, uncertainty intervals and portable evidence packages | Batch/export and replicated development reports with Wilson uncertainty implemented; ablation/sensitivity and richer workflows still needed |
| Research communication | Derived equations, assumptions, units, numerical checks, verified screenshots and reproducible results | Mathematics/model notes updated for this foundation; full upgraded system is not yet documented or validated |

Complexity must earn its place by answering a scientific question. Sustained
population alone does not prove meaningful adaptation; a moving graph alone does
not prove evolution; named rituals do not prove religion. Extreme interventions
may legitimately cause extinction. The observer must explain these distinctions.
