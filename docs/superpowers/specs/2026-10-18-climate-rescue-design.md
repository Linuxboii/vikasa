# Vikasa Climate Rescue — design

Status: accepted (the project owner handed every open decision to the builder;
decisions below marked *builder's call* were made on their behalf).
Date: 2026-10-18.

## 1. Intent

A college project that answers a real question:

> **Can a population evolve fast enough to survive a warming climate, and how
> fast is too fast?**

This is called *evolutionary rescue* (Gomulkiewicz & Holt 1995; Bell & Gonzalez
2009). Theory (Lynch & Lande 1993; Bürger & Lynch 1995) predicts a **critical
rate of environmental change**. Below it, adaptation keeps up. Above it, the
population falls behind its optimum and goes extinct. Vikasa already simulates
individuals with inherited traits, energy budgets, mating and death. This
project adds heritable thermal tolerance and real climate forcing, then measures
that critical rate. Three analytic layers sit on top:

1. **Real-data climate twin**: observed monthly temperature for real Indian
   regions (NASA POWER, MERRA-2 reanalysis) plus IPCC AR6 warming pathways
   (SSP1-2.6 … SSP5-8.5).
2. **Global sensitivity analysis**: Sobol indices showing which biological and
   climatic factors decide survival.
3. **Machine-learning surrogate**: a Gaussian-process emulator trained on
   simulations. It gives instant survival predictions, uncertainty, and makes the
   Sobol analysis affordable.

Order of priority for every trade-off: **real-world usability first, complexity
second** (owner's instruction).

### Who uses it and how

- **Student or examiner:** runs one command and gets an offline HTML report that
  answers the question with graphs, uncertainty and caveats.
- **Ecology learner or researcher:** picks a region (any latitude/longitude), a
  species generation time and a thermal tolerance breadth, and gets: survival
  probability per SSP scenario, the critical warming rate, and which factors
  matter most.
- **Presenter:** runs the Godot 3D biome with a warming scenario. The HUD shows
  live °C, the population's mean thermal optimum and the adaptation lag.

## 2. Goals

- G1. Heritable, individual-level thermal tolerance that affects energy,
  injury, fertility and death. Inactive unless a config enables `climate`.
- G2. Climate forcing in °C from a monthly climatology plus an anomaly pathway.
  Usable from real fetched data, bundled offline data, or synthetic cycles.
- G3. A reproducible rescue protocol: burn-in, then warming at a set rate in °C
  per generation, then hold. Each rate runs in an *evolving* arm and a
  *non-heritable control* arm, across many seeds, in parallel and resumably.
- G4. Statistical answers: survival vs rate curves, critical rate with bootstrap
  CI, rescue gain (evolving − control) with CI, adaptation lag vs rate,
  rescue-signature (decline-then-recovery) frequency.
- G5. Sobol first-order and total-order indices from an in-house Saltelli/Jansen
  estimator, verified on the Ishigami benchmark.
- G6. A GP surrogate for final population ratio and survival, validated on held-out
  runs, used for Sobol and instant assessments.
- G7. Regional assessment: region + generation time + tolerance breadth → per-SSP
  warming rate per generation, surrogate survival estimate and direct-simulation
  survival estimate with Wilson CI, and a plain-language verdict.
- G8. An offline single-file HTML report, plus JSON/CSV evidence with a SHA-256
  manifest.
- G9. A Godot demo config and HUD readout. Documentation in ODD format
  (Grimm et al. 2006/2020).

## 3. Non-goals

- Predicting a named real species. Biology stays generic and is labelled as such.
  Only the climate forcing is real data.
- Phenotypic plasticity, behavioural thermoregulation, migration to cooler
  areas, food-web effects of warming, and humidity or rainfall effects on
  tolerance.
- Downscaled regional climate models. Regional warming = AR6 global-mean
  pathway × a user-set regional factor (default 1.0, documented).
- Rewriting the engine for speed. Throughput comes from a lean rescue config and
  process parallelism.

## 4. Anti-goals (failure even if it "works")

- Presenting simulation output as a forecast for a real species.
- Changing any existing behaviour: non-climate configs must keep their exact
  deterministic trajectories and every existing test must pass.
- Results that cannot be regenerated from the committed code, config and data.
- A report that needs internet or a server to open.
- Unlabelled assumptions, or numbers in the report that have no traceable source.

## 5. Model

### 5.1 Climate forcing (`climate` config section, optional)

- `ticks_per_year` (int ≥ 4). Year fraction φ = (tick mod ticks_per_year)/ticks_per_year.
- `monthly_c`: 12 monthly mean temperatures (°C), a climatology.
  T_season(φ) = periodic linear interpolation between month centres.
- `anomaly_c`: list of `[year, ΔT]` knots, years counted from simulation start
  (year = tick / ticks_per_year). Linear between knots, held constant outside.
- T(tick) = T_season(φ) + ΔT(year).
- Season label = `("spring","summer","autumn","winter")[floor(4φ)]`. When
  climate is enabled this replaces the fixed 96-tick season cycle. Seasonal
  food/metabolic multipliers use the same index.
- Engine-normalised temperature (used by visuals and habitat) =
  clamp(0.6 + (T − annual_mean)/20, 0, 1) (*builder's call*). Rescue configs
  disable the plant-water `ecology` layer, so temperature acts only through
  thermal tolerance. This keeps one causal pathway, as the non-goals require.

### 5.2 Thermal tolerance

Each creature carries `thermal_optimum` θ (°C). Mismatch d = T − θ.
Asymmetric Gaussian performance (thermal performance curves are steeper on the
warm side; Huey & Kingsolver 1989):

- ω = `tolerance_breadth_c` if d < 0 else `tolerance_breadth_c × warm_side_ratio`.
- performance P = exp(−d² / (2ω²)); stress s = 1 − P ∈ [0, 1).

Effects per tick (only when climate enabled):

- Basal energy cost × (1 + `stress_metabolic_gain` × s).
- Injury += `stress_injury_rate` × max(0, s − 0.3)/0.7. Normal recovery applies
  only when s ≤ 0.3 and there is no other health pressure.
- Not reproduction-eligible while s > `fertility_stress_limit` (heat-induced
  sterility; Walsh et al. 2019).
- Injury death while s > 0.3 gets cause `"thermal stress"`.

### 5.3 Inheritance of θ (`inheritance` field)

- `"heritable"`: child θ = (θ₁+θ₂)/2 + N(0, `segregation_sd_c`) + N(0, `mutation_sd_c`).
  This is the infinitesimal model of quantitative genetics.
- `"none"` (control): child θ ~ N(`founder_mean_c`, `founder_sd_c`). Same
  phenotypic spread, zero heritability.
- Founders: θ ~ N(`founder_mean_c`, `founder_sd_c`). `founder_mean_c` defaults
  to the annual mean of `monthly_c`.
- Clamp θ to [−20, 60] °C as a numerical safety bound, checked by the invariant audit.
- New random draws happen **only** when climate is enabled, after all existing
  draws in the same routine, so non-climate RNG streams are unchanged.

### 5.4 Persistence and transport

- Checkpoints: write `thermal_optimum` when climate is enabled. Read it with
  default 0.0. The checkpoint version number is unchanged; a climate config
  with a missing field is an error.
- Environment `to_dict` gains `temperature_c`; `from_dict` defaults it.
- Bridge explanation document: `environment.temperature_c` plus a `climate` block
  (`mean_optimum_c`, `sd_optimum_c`, `lag_c`, `mean_stress`) when enabled.
  The binary frame format is unchanged.
- Invariant audit: θ finite and within bounds when enabled; θ must be 0 when disabled.

## 6. Rescue protocol

- **Rescue config** `config/climate-rescue.json` (*builder's call*): a lean
  world tuned for throughput and short generations. Tuning acceptance criteria:
  the rate-0 evolving arm survives the full protocol in ≥ 90 % of pilot seeds;
  generation interval G ≤ 400 ticks; ≥ 100 ticks/s per process.
- **Generation interval G**: measured, not assumed. It is the slope of mean
  living generation depth vs tick, between burn-in end and protocol end, at
  rate 0. The value is stored with its seeds in `calibration.json`.
- **Abstract time**: in the sweep and sensitivity design, 1 generation =
  1 year, so `ticks_per_year = G` (*builder's call*). Assessment rescales to
  the user's generation time.
- **Phases** (in generations): burn-in 8 (ΔT = 0), warming 20 at rate r °C/gen,
  hold 8 at the final ΔT.
- **Outcomes per replicate**: survived (population > 0 at end), extinction
  generation, N_pre (mean over the last burn-in generation), N_min, N_final,
  ratio = N_final/N_pre, evolved shift (mean θ end − mean θ start of warming),
  lag (mean over the last 5 warming generations of ΔT_annual − (mean θ − θ₀)),
  rescue signature (N_min < 0.5 N_pre and N_final ≥ 0.8 N_pre), death causes,
  and a trajectory sampled every G/4 ticks.
- **Sweep**: rate grid × {heritable, none} × seeds (default 12). The grid is
  bracketed by a pilot so the evolving arm spans survival ≥ 0.9 down to ≤ 0.1.
  Process-parallel; each finished replicate is appended to `results.jsonl` and
  skipped on resume. Results are keyed by (arm, rate, seed).

## 7. Analysis

- Survival vs rate per arm: unpenalised logistic regression; critical rate
  k_c = rate at P = 0.5. 95 % CI by bootstrap (2,000 resamples of seeds within
  each rate). Wilson CI per cell.
- Rescue gain = k_c(heritable) − k_c(none), paired bootstrap CI.
- Lag vs rate: linear fit and Pearson r over subcritical rates (evolving arm).
- Sensitivity design: Latin hypercube over 6 inputs (*builder's call*):
  warming rate (°C/gen), tolerance breadth (°C), seasonal amplitude (°C,
  sinusoidal cycle), founder SD (°C), segregation SD (°C), carrying capacity
  (population cap with resource spawn scaled proportionally). One seed per point;
  stochasticity is absorbed by the GP noise kernel.
- Surrogate: scikit-learn GP regressor (Matern ν=2.5 + WhiteKernel, inputs scaled
  to [0,1]) on ratio, and a GP classifier on survival. Validation: 5-fold CV R²
  and AUC, plus a 20 % held-out test set. The model is saved with its metadata.
- Sobol: Saltelli sampling (scrambled Sobol sequence) with Jansen first- and
  total-order estimators. Bootstrap CI. Applied to the surrogate's predicted
  survival probability and ratio. Estimator verified on Ishigami.

## 8. Real-world assessment

- `climate fetch`: NASA POWER monthly T2M for any lat/lon, 1981–last full year.
  Output: monthly climatology for 1991–2020, observed linear trend (°C/decade,
  OLS ± SE), the raw series, and provenance (URL, retrieval time, SHA-256).
- Bundled offline datasets (*builder's call*): Western Ghats (Agumbe 13.52 N,
  75.09 E; amphibian hotspot), Delhi NCR (28.61 N, 77.21 E), Sundarbans
  (21.95 N, 88.90 E).
- SSP pathways: IPCC AR6 WG1 Table 4.5 median warming for 2081–2100 relative to
  1995–2014 (SSP1-2.6 0.9 °C, SSP2-4.5 1.8 °C, SSP3-7.0 2.8 °C, SSP5-8.5 3.5 °C),
  with likely ranges kept. Linear from 2005 (period midpoint) to 2090, extended
  linearly. Multiplied by `--regional-factor`.
- `climate assess`: given region, generation years g, breadth ω and SSPs, for
  each SSP computes:
  - the 2025–2100 rate (°C/yr) and rate per generation (× g);
  - the sweep-curve probability (if a sweep exists);
  - the surrogate probability ± uncertainty (if a model exists);
  - a direct-simulation probability with Wilson CI (N seeds, real monthly
    cycle, ticks_per_year = G/g);
  - a verdict: likely persists (P ≥ 0.8), at risk (0.2–0.8), likely lost (< 0.2).
  The direct simulation is authoritative; disagreement with the surrogate is
  reported, not hidden.

### 8.1 Resolved builder questions (*builder's calls*, owner delegated)

- **Assess time span.** Direct simulation follows the real calendar. Burn-in
  is 8 generations at the 2025 anomaly. Warming then runs from 2025 to 2100,
  which is 75/g generations, **capped at 60 generations**. If the cap applies,
  only the first 60·g years are simulated and the report states this. Hold is
  8 generations. G is re-measured for the user's region and ω with 2 rate-0
  calibration seeds before the assessment runs. Sweep and surrogate numbers
  appear beside the direct answer, labelled *reference (fixed 20-generation
  protocol)*.
- **Reference sweep climate.** One sweep: Western Ghats climatology,
  ω = 4 °C. The report shows the sweep probability for a region only when that
  region's seasonal amplitude and the user's ω are each within ±25 % of the
  sweep's; otherwise it says "outside sweep domain". The surrogate, whose inputs
  include amplitude and ω, is the cross-region generaliser.
- **Compute profiles.**
  - `quick` (tests/smoke): 3 rates × 2 arms × 3 seeds, 24 LHS points, 3 assess seeds.
  - `full` (committed evidence): bracketed grid of 9 rates × 2 arms × 12 seeds,
    256 LHS training points + 64 held-out points, 12 assess seeds per SSP, 2,000
    bootstrap resamples.
  - `vikasa climate pipeline --profile quick|full` runs everything end to end
    and resumably. `vikasa climate report` only renders from existing results.
- **Baselines and observed trend.** The 1991–2020 climatology and the AR6
  1995–2014 reference period have nearly the same centre (2005.5 vs 2004.5).
  They are treated as equal, documented as a < 0.05 °C approximation. The SSP
  anomaly at 2025 (target × 20/85) is applied from the start of burn-in. The
  observed local OLS trend is shown beside each SSP's implied 2025–2050 rate as a
  plausibility check. It does not change the regional factor.

## 9. Deliverables

- Package `evolution_sim.climate` (forcing, thermal, data, protocol, analysis,
  sensitivity, surrogate, assess, report) plus CLI group `vikasa climate …`
  (`fetch`, `calibrate`, `sweep`, `sensitivity`, `assess`, `report`).
- Configs: `config/climate-rescue.json`, `config/climate-demo.json`.
- Data: `data/climate/*.json`.
- Docs: `docs/CLIMATE_RESCUE.md` (ODD protocol, method, results, limitations,
  references), plus a README section.
- Committed evidence: `docs/results/climate-rescue-2026-10-18/` (report HTML,
  summary JSON, figures).
- Tests for every module.

## 10. Left to the builder

Internal module layout, chart styling, rescue-config numbers (within the §6
acceptance criteria), the rate grid (within the §6 bracketing rule), worker
count, and the HUD layout.
