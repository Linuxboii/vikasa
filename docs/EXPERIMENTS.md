# Experiments

## Method

Treat scenario JSON as the preregistered protocol: keep the base configuration, seed set, tick count, and metrics interval fixed; vary only the intended treatment. Use `batch` for replicate seeds. Generated `summary.json` and CSV files are the primary evidence; UI screenshots are explanatory figures.

## Baseline

Hypothesis: under stable food supply, population and trait means approach a dynamic equilibrium rather than a predetermined optimum.

```powershell
.\.venv\Scripts\python.exe main.py batch --scenario experiments/baseline.json --output exports/baseline --replicates 5
```

Inspect population stability, vital events, diversity, and whether means drift without a directional environmental change.

## Scarcity

Hypothesis: sustained food reduction changes survival/reproduction trade-offs and lowers population size. Candidate responses include altered metabolic efficiency, size, speed, or perception; the model does not promise which direction wins.

```powershell
.\.venv\Scripts\python.exe main.py batch --scenario experiments/scarcity.json --output exports/scarcity --replicates 5
```

Compare pre-pressure and post-pressure windows. Do not infer adaptation from population decline alone; require trait evidence and reproduction across generations.

## Mutation comparison

Hypothesis: higher mutation raises variation but can destabilize well-adapted combinations. Both treatments use seed 3303 by default.

```powershell
.\.venv\Scripts\python.exe main.py batch --scenario experiments/mutation_low.json --output exports/mutation-low --replicates 5
.\.venv\Scripts\python.exe main.py batch --scenario experiments/mutation_high.json --output exports/mutation-high --replicates 5
```

Compare diversity, extinction frequency, population variance, and final trait distributions. The included single 900-tick examples ended at diversity 0.8850 and 0.8955 respectively; that difference is descriptive, not a conclusion.

## Environmental shift

Hypothesis: a stable population responds to a resource crash and heat stress, then recovers under abundance with a changed trait distribution.

```powershell
.\.venv\Scripts\python.exe main.py run --scenario experiments/environmental_shift.json --output exports/environmental-shift
```

Use `events.json` to place vertical markers at each phase. Compare means/distributions before drought, at maximum pressure, and after recovery.

## Recommended analysis

1. Verify `invariant_errors` is empty in every summary.
2. Check extinction and peak population before comparing traits.
3. Plot replicate median and interval for population and trait means.
4. Compare normalized diversity because raw trait units differ.
5. Treat correlations as exploratory; survival and ancestry create dependence.
6. Report seed sets, configuration hashes, tick counts, and package version.

## Bundled examples

`examples/results/` contains compact 900-tick packages for all five scenario files. Each includes machine-readable state plus four charts. The scarcity and environmental-shift examples use compressed event schedules so the whole pressure/recovery story fits the reference window; the reusable scenario files retain longer presentation schedules.

