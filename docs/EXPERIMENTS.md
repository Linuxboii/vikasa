# Experiments

Use scenario JSON as the protocol. Keep configuration, ticks and treatment fixed across seed replicates; vary only the named condition. Example result folders and charts are illustrative individual runs, not statistical findings. Commands below use the installed `vikasa` entry point (`.venv\Scripts\vikasa.exe` on Windows; `.venv/bin/vikasa` on macOS/Linux).

## Reproducibility control

Repeat one scenario with exactly the same seed and tick count, writing to separate output folders:

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\baseline.json --output exports\repro-a --seed 2026 --ticks 900
.\.venv\Scripts\vikasa.exe run --scenario experiments\baseline.json --output exports\repro-b --seed 2026 --ticks 900
```

Compare canonical summary data, not PNG metadata. Equal configuration, seed, schedule, software and numerical platform should produce the same simulation summary. Then use distinct seeds for inference; one seed demonstrates reproducibility, not robustness.

## Low-food survival and foraging

The bundled scarcity scenario schedules a sustained drought. Compare with baseline using matched ticks and an explicit seed. Observe starvation deaths, foraging drive/action, food acquisition, population, and trait distributions. Trait shifts alone do not prove adaptation; check that variants reproduce and persist across generations.

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\baseline.json --output exports\food-control --seed 2202 --ticks 7000
.\.venv\Scripts\vikasa.exe run --scenario experiments\scarcity.json --output exports\food-scarcity --seed 2202 --ticks 7000
```

`scarcity.json` fixes drought start at tick 1800 for 4200 ticks at food intensity 0.22. Treatments share a seed, though the changed ecology naturally changes subsequent random-call histories.

## Hazard avoidance

The environmental-shift scenario combines a resource crash, heat stress, and a later abundance period. The Godot client can schedule visible pressure interactively through World tools; the CLI version below is reproducible.

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\environmental_shift.json --output exports\hazard-shift --seed 4404 --ticks 8000
```

Inspect danger-avoidance drives, flee decisions/reasons, injury, movement costs, survival and recovery by phase. Hazard avoidance uses coarse world/local pressure; the engine does not simulate a detailed weather field or terrain refuges.

## Dependent care and mate readiness

Run a sufficiently long baseline to allow descendants. When young are alive, within configured age/radius, and parent-linked, inspect offspring-care drive, care action, energy transfers, parental reserves, survival, and subsequent mate readiness. Care is opportunity-limited and competes with self-maintenance; reproduction remains gated by age, threshold energy, cooldown and mutual target selection.

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\baseline.json --output exports\care-mating --seed 5150 --ticks 7000
```

The baseline is not a controlled care-ablation experiment: do not interpret its single output as a causal estimate. To test causality, prepare matched scenario/config variants that change only care parameters (`behavior.dependent_age_ticks`, `care_radius`, or `care_energy_rate`) and use the same replicate seed set.

## Home-range scarcity and migration

Use scarcity to observe patrol and foraging beyond home range. Migration only occurs when an individual remains outside its range while foraging and the best locally perceived outside food reward exceeds inside reward by the configured migration margin for 24 consecutive qualifying ticks; then its home center shifts 0.5% toward its current position. Inspect home center/radius, migration counters and survival rather than assuming every animal disperses.

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\scarcity.json --output exports\range-scarcity --seed 6161 --ticks 7000
```

This is a local heuristic. It does not implement landscape corridors, kin structure, map suitability, group migration or realistic territory defense.

## Mutation and selection

Compare the bundled low/high mutation protocols. They use the same default seed value but distinct treatments; batch gives each replicate a reproducible offset seed.

```powershell
.\.venv\Scripts\vikasa.exe batch --scenario experiments\mutation_low.json --output exports\mutation-low --replicates 5 --ticks 6000
.\.venv\Scripts\vikasa.exe batch --scenario experiments\mutation_high.json --output exports\mutation-high --replicates 5 --ticks 6000
```

Compare normalized diversity, trait distributions, variance, extinction, births/deaths and invariant errors. Higher mutation can raise variance or disrupt successful combinations; the model does not promise that it improves adaptation.

## Reporting and checks

For predeclared multi-condition studies, use the [controlled experiment laboratory](CONTROLLED_EXPERIMENTS.md).
The `contrast` command supplies fixed-horizon seed blocks, retained failures and
extinctions, paired effect estimates and an offline viewer. Its published weather
preview shows actual population differences; larger protocols and sensitivity
studies still require execution rather than inference from a demonstration.

1. Validate a config before launching custom experiments: `vikasa validate --config config/showcase.json`.
2. Record scenario/config contents, package version, seed list, ticks, event schedule and output hash.
3. Check `invariant_errors` is empty; report extinction and sample timing.
4. Use replicated distributions and matched treatment seeds; do not over-read one screenshot or one run.
5. Distinguish model outputs from claims about real organisms. See the [scientific model](SCIENTIFIC_MODEL.md) for assumptions and the [mathematics reference](MATHEMATICS.md) for equations.
