# Vikasa Climate Rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add heritable thermal tolerance and real climate forcing to Vikasa, then measure the critical warming rate for evolutionary rescue. Add sensitivity analysis, a GP surrogate, regional SSP assessments and an offline HTML report.

**Architecture:** A new package `evolution_sim.climate` holds pure modules (forcing, thermal, data, protocol, analysis, sensitivity, surrogate, assess, figures, report, cli). The engine gets small branches guarded by `config.climate.enabled`, so legacy RNG streams stay bit-identical. Experiments run as independent process-parallel replicates appended to resumable JSONL files. Analysis reads only those files.

**Tech Stack:** Python 3.12, NumPy, pandas, matplotlib (existing); SciPy ≥ 1.14 (`stats.qmc`, `stats`) and scikit-learn ≥ 1.5 (GP models, metrics; brings joblib), both added as dependencies; pytest, ruff; Godot 4 GDScript for one HUD readout.

**Spec:** `docs/superpowers/specs/2026-10-18-climate-rescue-design.md` (read it; §8.1 holds the resolved builder questions).

## Global Constraints

- Python commands use `.venv/Scripts/python.exe`. Tests: `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <path>`.
- Non-climate configs stay bit-identical: `tests/climate/test_climate_legacy_determinism.py` must pass after every task.
- The full existing suite (`-m "not slow"`, 401 tests at baseline) stays green.
- `SimulationConfig.to_dict()` omits the `climate` key when climate is disabled. This keeps legacy config hashes and checkpoints byte-identical.
- New random draws happen only when climate is enabled, and after all existing draws in the same routine.
- Test files live in `tests/climate/` and are named `test_climate_*.py` (pytest rootdir import mode needs unique basenames).
- Ruff clean: `.venv/Scripts/python.exe -m ruff check src tests`.
- Every JSON artifact is written with `allow_nan=False`, `sort_keys=True`, UTF-8, `\n` newlines. Non-finite values become `null`.
- No network in tests. The network is used only by `climate fetch` and by the one-time bundling step in Task 5.
- Biology is generic. Every report and doc page carries the sentence: "Climate forcing is observed data; the organism is a generic model, not a calibrated real species."
- Commit after each task, with the attribution line `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **Extinction mid-protocol** (population 0 before warming ends): outcomes must still serialize, with lag/shift `null`, `extinction_generation` set and no crash. Test in Task 6.
2. **Perfect separation in survival data** (all seeds survive below a rate, all die above it): the logistic fit must still return a finite critical rate, and bootstrap samples with no variation are counted in `undefined_fraction`, not crashed on. Test in Task 7.
3. **Interrupted sweep, then rerun**: completed keys are skipped, and a partially written last JSONL line is ignored and recomputed. Test in Task 6.
4. **NASA POWER fill values (−999) and month-13 annual keys**: these are excluded from the climatology and trend; fewer than 20 valid years for any month is a clear `ValueError`. Test in Task 5.
5. **Assessment inputs outside the surrogate or sweep domain** (e.g. Delhi amplitude, ω = 12 °C): the report shows "outside domain" instead of an extrapolated number. Test in Task 10.

---

## File Structure

```
src/evolution_sim/config.py                 MODIFY  ClimateConfig + parse/serialize
src/evolution_sim/model/entities.py         MODIFY  Creature.thermal_optimum, thermal_stress
src/evolution_sim/simulation/environment.py MODIFY  EnvironmentState.climate, temperature_c
src/evolution_sim/simulation/engine.py      MODIFY  guarded thermal branches
src/evolution_sim/io/checkpoints.py         MODIFY  persist thermal fields, reattach forcing
src/evolution_sim/bridge.py                 MODIFY  environment.temperature_c + climate block
src/evolution_sim/cli.py                    MODIFY  delegate `climate` subcommand
src/evolution_sim/climate/__init__.py       CREATE
src/evolution_sim/climate/forcing.py        CREATE  ClimateForcing
src/evolution_sim/climate/thermal.py        CREATE  stress, inheritance, population summary
src/evolution_sim/climate/data.py           CREATE  NASA POWER, RegionClimate, SSP pathways
src/evolution_sim/climate/data/*.json       CREATE  bundled regions (3)
src/evolution_sim/climate/protocol.py       CREATE  phases, config builder, replicate, calibration, task runner
src/evolution_sim/climate/analysis.py       CREATE  Wilson, logistic, critical rate, gain, lag, criteria
src/evolution_sim/climate/sensitivity.py    CREATE  parameters, LHS, Saltelli/Jansen Sobol, Ishigami
src/evolution_sim/climate/surrogate.py      CREATE  GP surrogate + validation + persistence
src/evolution_sim/climate/assess.py         CREATE  regional SSP assessment
src/evolution_sim/climate/figures.py        CREATE  matplotlib PNG bytes
src/evolution_sim/climate/report.py         CREATE  offline HTML + manifest
src/evolution_sim/climate/cli.py            CREATE  argparse group + pipeline profiles
config/climate-rescue.json                  CREATE  lean tuned rescue world
config/climate-demo.json                    CREATE  Godot demo (visible warming)
godot/scripts/HUD.gd                        MODIFY  °C / optimum / lag readout
pyproject.toml                              MODIFY  scipy, scikit-learn, package data
docs/CLIMATE_RESCUE.md                      CREATE  ODD protocol, method, results, limits, refs
README.md                                   MODIFY  climate section + commands
docs/results/climate-rescue-2026-10-18/     CREATE  committed full-profile evidence
tests/climate/test_climate_*.py             CREATE  one per module
```

---

### Task 1: Climate configuration

**Files:**
- Modify: `src/evolution_sim/config.py`
- Modify: `pyproject.toml` (dependencies `scipy>=1.14`, `scikit-learn>=1.5`; include `src/evolution_sim/climate/data/*.json` in the wheel; version `2.1.0`)
- Test: `tests/climate/test_climate_config.py`

**Interfaces:**
- Produces: `ClimateConfig` frozen dataclass with these fields and defaults:
  - `enabled: bool = False`
  - `ticks_per_year: int = 384` (4 to 1,000,000)
  - `monthly_c: tuple[float, ...] = (25.0,)*12` (exactly 12 values, each in [−60, 60])
  - `anomaly_c: tuple[tuple[float, float], ...] = ()` (years strictly increasing and ≥ 0; ΔT in [−30, 30])
  - `tolerance_breadth_c: float = 4.0` (0.1 to 50)
  - `warm_side_ratio: float = 0.6` (0.05 to 1)
  - `stress_metabolic_gain: float = 1.5` (0 to 20)
  - `stress_injury_rate: float = 0.02` (0 to 1)
  - `fertility_stress_limit: float = 0.7` (0 to 1)
  - `inheritance: str = "heritable"` (`"heritable"` or `"none"`)
  - `founder_mean_c: float | None = None` (in [−20, 60] when set)
  - `founder_sd_c: float = 1.0` (0 to 20)
  - `segregation_sd_c: float = 0.4` (0 to 20)
  - `mutation_sd_c: float = 0.1` (0 to 20)

  Property `annual_mean_c -> float` (mean of `monthly_c`). Property `resolved_founder_mean_c -> float`.
- `SimulationConfig.climate: ClimateConfig = field(default_factory=ClimateConfig)`; `"climate"` is in `ROOT_KEYS` and optional. `to_dict()` drops `climate` when `enabled` is False and emits `anomaly_c` as a list of 2-lists.
- Errors are `ConfigError` with the message prefix `climate.<field>`.

- [ ] **Step 1: Write failing tests**

```python
def test_climate_absent_means_disabled_and_not_serialized(): ...
    # SimulationConfig.from_json("config/default.json").climate.enabled is False
    # "climate" not in cfg.to_dict()
def test_climate_round_trip_preserves_all_fields(): ...
    # enabled config -> to_dict -> from_dict equality; anomaly_c lists
def test_climate_annual_mean_and_founder_default(): ...
    # monthly_c = range(12) -> annual_mean_c == 5.5 == resolved_founder_mean_c
@pytest.mark.parametrize("patch,fragment", [
    ({"monthly_c": [20.0]*11}, "climate.monthly_c"),
    ({"anomaly_c": [[5, 1.0], [5, 2.0]]}, "climate.anomaly_c"),
    ({"tolerance_breadth_c": 0}, "climate.tolerance_breadth_c"),
    ({"inheritance": "lamarck"}, "climate.inheritance"),
    ({"unknown": 1}, "climate.unknown"),
])
def test_climate_rejects_invalid(patch, fragment): ...  # pytest.raises(ConfigError, match=fragment)
```

- [ ] **Step 2: Run** `pytest tests/climate/test_climate_config.py`. Expected: FAIL (`climate` not a supported field).
- [ ] **Step 3: Implement `ClimateConfig`.** Validate in `__post_init__`, following the pattern of `EcologyConfig`. Parse in `from_dict` like `ecology`, with lists converted to tuples. Edit `pyproject.toml`.
- [ ] **Step 4: Run** the new tests plus `tests/test_config.py` and the legacy fingerprint test. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(climate): optional climate configuration section`.

### Task 2: Climate forcing and environment integration

**Files:**
- Create: `src/evolution_sim/climate/__init__.py`, `src/evolution_sim/climate/forcing.py`
- Modify: `src/evolution_sim/simulation/environment.py`
- Test: `tests/climate/test_climate_forcing.py`

**Interfaces:**
- Produces `ClimateForcing(config: ClimateConfig)` with:
  - `year(tick: int) -> float` = tick / ticks_per_year
  - `phase(tick) -> float` in [0, 1)
  - `seasonal_c(phase: float) -> float`: periodic linear interpolation with month m centred at phase (m + 0.5)/12
  - `anomaly_c(year: float) -> float`: linear between knots, constant outside, 0.0 when there are no knots
  - `temperature_c(tick) -> float` = seasonal_c + anomaly_c
  - `annual_temperature_c(tick) -> float` = annual_mean_c + anomaly_c(year)
  - `season_index(tick) -> int` = floor(4·phase)
  - `normalized(temperature_c: float, tick: int) -> float` = clamp(0.6 + (T − annual_mean_c)/20, 0, 1)
- `EnvironmentState.__init__(self, climate: ClimateForcing | None = None)`; new attribute `temperature_c: float | None`. In `update(tick)`, when `climate` is set, the season index comes from `climate.season_index(tick)`, `temperature_c = climate.temperature_c(tick)` and `temperature = climate.normalized(...)`. Rainfall and seasonal multiplier tables are indexed by the same season index. Events then apply as today. `to_dict` adds `"temperature_c"` only when it is not None. `from_dict` reads it with a None default; the caller reattaches the forcing.

- [ ] **Step 1: Write failing tests**

```python
def test_seasonal_interpolation_hits_month_centres():  # phase (m+.5)/12 -> monthly_c[m] (abs 1e-12)
def test_seasonal_wraps_december_to_january():          # phase 0.0 -> mean(dec, jan)
def test_anomaly_linear_and_clamped():                  # knots [(0,0),(10,2)]: year 5 -> 1.0, year 20 -> 2.0, year -1 -> 0.0
def test_environment_uses_forcing_season_and_temperature():
    # ticks_per_year=40: tick 0 -> "spring", tick 10 -> "summer"; temperature_c matches forcing
def test_environment_without_forcing_unchanged():       # to_dict() has no "temperature_c" key
```

- [ ] **Step 2: Run.** Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `forcing.py` and the `EnvironmentState` changes.**
- [ ] **Step 4: Run** the new tests, `tests/simulation/test_environment.py` and the legacy fingerprint test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): monthly climatology + anomaly forcing in °C`.

### Task 3: Heritable thermal tolerance in the engine

**Files:**
- Create: `src/evolution_sim/climate/thermal.py`
- Modify: `src/evolution_sim/model/entities.py`, `src/evolution_sim/simulation/engine.py`
- Test: `tests/climate/test_climate_thermal.py`, `tests/climate/test_climate_engine.py`

**Interfaces:**
- `thermal.py`:
  - `OPTIMUM_BOUNDS = (-20.0, 60.0)`; `STRESS_INJURY_THRESHOLD = 0.3`
  - `thermal_stress(temperature_c: float, optimum_c: float, breadth_c: float, warm_side_ratio: float) -> float`: the asymmetric Gaussian from spec §5.2. Warm side applies when T > θ.
  - `founder_optimum(cfg: ClimateConfig, rng) -> float`: clamp(N(resolved_founder_mean_c, founder_sd_c))
  - `inherit_optimum(cfg, first: float, second: float, rng) -> float`: heritable → clamp(midparent + N(0, seg) + N(0, mut)), always 2 normal draws; none → founder_optimum
  - `population_summary(engine) -> dict` with keys `temperature_c, annual_temperature_c, mean_optimum_c, sd_optimum_c, lag_c, mean_stress, population`. Values are None when there are no creatures. `lag_c = annual_temperature_c − mean_optimum_c`.
- `Creature` gains `thermal_optimum: float = 0.0` and `thermal_stress: float = 0.0`. Both must be finite; stress must be in [0, 1].
- Engine (every branch under `if self.climate is not None`):
  - `self.climate = ClimateForcing(config.climate) if config.climate.enabled else None`, passed to `EnvironmentState(self.climate)`.
  - Founders: after the existing `Creature(...)` construction, set `thermal_optimum = founder_optimum(...)`.
  - Newborns: after the `Creature(...)` construction in `_resolve_reproduction`, set `thermal_optimum = inherit_optimum(...)`.
  - `_execute_behavior`: compute `s` before the basal cost and store `creature.thermal_stress = s`. Multiply basal by `(1 + gain·s)`. Injury: when `s > 0.3`, add `rate·(s−0.3)/0.7`. The recovery branch runs only when `health_pressure == 0` and `s ≤ 0.3`.
  - `_eligible`: also requires `thermal_stress ≤ fertility_stress_limit`.
  - `_resolve_deaths`: an injury death with `thermal_stress > 0.3` gets cause `"thermal stress"`.
  - `audit_invariants`: θ must be finite and within bounds when enabled; θ must equal 0.0 when disabled.

- [ ] **Step 1: Write failing unit tests (`test_climate_thermal.py`)**

```python
def test_stress_zero_at_optimum():                     # thermal_stress(25, 25, 4, .6) == 0.0
def test_stress_asymmetric_warm_side_steeper():        # stress(27,25,4,.6) > stress(23,25,4,.6)
def test_stress_value():                               # stress(29,25,4,1.0) == 1-exp(-0.5) (abs 1e-12)
def test_none_inheritance_ignores_parents():           # mean of 4000 draws ≈ founder mean (abs .1) even with parents at +10
def test_heritable_inheritance_tracks_midparent():     # mean ≈ midparent (abs .05), sd ≈ hypot(seg, mut) (rel .1)
def test_inherit_clamps_to_bounds():                   # parents at 60 -> result ≤ 60
```

- [ ] **Step 2: Write failing engine tests (`test_climate_engine.py`)** using a fixture `climate_config(**climate_overrides)` built from `config/default.json` with world 240×160, population 20, cap 60, ecology disabled and the climate section enabled.

```python
def test_founders_carry_optimum_near_founder_mean():
def test_climate_run_is_deterministic():               # two engines, same seed, 300 ticks: identical (θ list, positions, rng state)
def test_extreme_heat_kills_by_thermal_stress():       # anomaly +15 °C from tick 0, breadth 2 -> extinct ≤ 3000 ticks, "thermal stress" in death_causes
def test_stress_blocks_reproduction_eligibility():     # creature with thermal_stress 0.9 -> engine._eligible False
def test_children_inherit_under_heritable_arm():       # after births, child θ within 6 sd of parents' midpoint
def test_audit_flags_out_of_bounds_optimum():          # set θ=99 -> audit lists it
```

- [ ] **Step 3: Run both files.** Expected: FAIL.
- [ ] **Step 4: Implement `thermal.py`, the entity fields and the engine branches.**
- [ ] **Step 5: Run** the new tests, the legacy fingerprint test and `tests/simulation`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(climate): heritable thermal tolerance with stress, sterility and thermal deaths`.

### Task 4: Checkpoints and bridge

**Files:**
- Modify: `src/evolution_sim/io/checkpoints.py`, `src/evolution_sim/bridge.py`
- Test: `tests/climate/test_climate_persistence.py`

**Interfaces:**
- `_creature_to_dict` emits `thermal_optimum` and `thermal_stress` only when `engine.config.climate.enabled` (pass a flag in). `_restore_creature` reads them with a 0.0 default. In `load_checkpoint`, a climate-enabled config whose creature lacks `thermal_optimum` raises `CheckpointError("Missing thermal_optimum for climate-enabled checkpoint")`. After `EnvironmentState.from_dict`, set `engine.environment.climate = engine.climate`.
- The bridge explanation document's `environment` gains `"temperature_c"` (when not None). The top level gains `"climate": population_summary(engine)` when enabled, else `None`.

- [ ] **Step 1: Write failing tests**

```python
def test_climate_checkpoint_round_trip_continues_identically(tmp_path):
    # run 200 ticks, save, load; step both 200 more -> identical θ lists and rng state
def test_legacy_checkpoint_has_no_thermal_keys(tmp_path):
def test_climate_checkpoint_missing_optimum_rejected(tmp_path):
def test_bridge_document_includes_climate_block():   # build the doc from the bridge state class used in tests/test_bridge_stream.py
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the new tests, `tests/io`, `tests/test_bridge_stream.py` and the legacy fingerprint test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): persist thermal state; expose climate in bridge`.

### Task 5: Real climate data and SSP pathways

**Files:**
- Create: `src/evolution_sim/climate/data.py`, `src/evolution_sim/climate/data/{western-ghats,delhi-ncr,sundarbans}.json`
- Test: `tests/climate/test_climate_data.py`, fixture `tests/climate/fixtures/power_sample.json` (a synthetic POWER-shaped payload for 1985–2020 with known monthly values, one −999 and month-13 keys)

**Interfaces:**
- `POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M&community=AG&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON"`
- `fetch_power_monthly(lat, lon, start, end, *, opener=urllib.request.urlopen, timeout=60) -> tuple[bytes, str]` returns (raw bytes, url). Raises `RuntimeError` on HTTP or JSON failure, with the URL in the message.
- `@dataclass(frozen=True) RegionClimate` fields:
  - `key, name, latitude, longitude`
  - `monthly_c: tuple[float, ...]` (12 values, 1991–2020 climatology)
  - `annual_mean_c`, `seasonal_amplitude_c` = (max − min)/2
  - `trend_c_per_decade`, `trend_se_c_per_decade` (OLS on annual means of complete years)
  - `first_year, last_year`
  - `series: tuple[tuple[int, int, float], ...]`
  - `provenance: dict` (`source`, `url`, `retrieved_utc`, `sha256`, `parameter`, `dataset: "NASA POWER MERRA-2 T2M monthly"`)
- `region_from_power(key, name, lat, lon, raw: bytes, url, retrieved_utc) -> RegionClimate`. Excludes month 13 and values ≤ −900. Raises `ValueError("climatology needs ≥20 valid years for month M")`.
- `save_region(region, path)`, `load_region(path) -> RegionClimate`
- `BUNDLED_REGIONS = {"western-ghats": ("Western Ghats (Agumbe)", 13.52, 75.09), "delhi-ncr": ("Delhi NCR", 28.61, 77.21), "sundarbans": ("Sundarbans", 21.95, 88.90)}`
- `resolve_region(spec: str) -> RegionClimate` (a bundled key, or a path to a region JSON)
- `SSP_WARMING = {"SSP1-2.6": (0.9, 0.5, 1.5), "SSP2-4.5": (1.8, 1.2, 2.6), "SSP3-7.0": (2.8, 2.0, 3.7), "SSP5-8.5": (3.5, 2.4, 4.8)}`, documented as °C for 2081–2100 vs 1995–2014, AR6 WG1 Table 4.5 (median, very likely range)
- `ssp_anomaly_c(ssp, year, regional_factor=1.0, bound="median") -> float` = target·factor·(year − 2005)/85, floored at 0 before 2005
- `ssp_rate_c_per_year(ssp, regional_factor=1.0, bound="median") -> float`

- [ ] **Step 1: Write failing tests**

```python
def test_parse_fixture_excludes_fill_and_annual_keys():   # climatology equals the known means
def test_trend_recovers_known_slope():                    # fixture built with +0.3 °C/decade -> 0.3 (abs 1e-9)
def test_insufficient_years_raises():
def test_region_json_round_trip(tmp_path):
def test_bundled_regions_load_and_are_plausible():        # each: 15 < annual_mean < 35, 12 months, sha256 64 hex
def test_ssp_values_and_rate():                           # ssp_anomaly_c("SSP2-4.5", 2090) == 1.8; rate == 1.8/85
def test_fetch_uses_opener_and_wraps_errors():            # fake opener raising -> RuntimeError containing url
```

- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement `data.py`.**
- [ ] **Step 4: Check the SSP numbers against IPCC AR6 WG1 Chapter 4 Table 4.5 by web search. If a value differs, correct the constant and the test, and note the source in the docstring.**
- [ ] **Step 5: Generate the bundled files once (network):** for each bundled key, call `fetch_power_monthly(lat, lon, 1981, <last full calendar year>)`, then `region_from_power`, then `save_region` into `src/evolution_sim/climate/data/<key>.json`.
- [ ] **Step 6: Run** the tests. Expected: PASS.
- [ ] **Step 7: Commit** `feat(climate): NASA POWER regions, bundled Indian datasets, AR6 SSP pathways`.

### Task 6: Rescue config, calibration, replicate runner and parallel task engine

**Files:**
- Create: `src/evolution_sim/climate/protocol.py`, `config/climate-rescue.json`
- Test: `tests/climate/test_climate_protocol.py`

**Interfaces:**
- `@dataclass(frozen=True) RescuePhases(burn_in: float = 8, warming: float = 20, hold: float = 8)`, in generations.
- `@dataclass(frozen=True) RescueCondition` fields:
  - `arm: str` (`"heritable"` or `"none"`)
  - `rate_c_per_gen: float`
  - `seed: int`
  - `breadth_c: float | None = None`, `amplitude_c: float | None = None`
  - `founder_sd_c: float | None = None`, `segregation_sd_c: float | None = None`
  - `capacity_scale: float = 1.0`
  - `key() -> str` = canonical JSON of the fields (sorted keys)
- `build_config(base: dict, condition: RescueCondition, generation_ticks: int, phases: RescuePhases, *, ticks_per_year: int | None = None, anomaly_knots: list[tuple[float, float]] | None = None, founder_mean_c: float | None = None) -> SimulationConfig`
  - Default ticks_per_year = generation_ticks.
  - Default knots: `[(0,0),(b,0),(b+w, rate·w)]`, in years where 1 year = 1 generation.
  - `amplitude_c` replaces `monthly_c` with `annual_mean + A·sin(2π(m+0.5)/12)`.
  - `capacity_scale` multiplies `reproduction.population_cap`, `resources.spawn_rate`, `resources.maximum_count` and `resources.initial_count` (ints rounded, ≥ 1). `initial_population` becomes min(itself, cap).
- `run_replicate(config: SimulationConfig, seed: int, generation_ticks: int, phases: RescuePhases) -> dict`. Returns:
  - `status: "ok"`
  - `survived`, `extinction_generation` (float or null)
  - `n_pre`, `n_min`, `n_final`, `ratio`
  - `theta0`, `evolved_shift_c`, `lag_c` (null if extinct before the window)
  - `rescue_signature`, `death_causes`, `invariant_errors` (audited every generation_ticks)
  - `ticks`, `elapsed_seconds`
  - `trajectory` (rows every max(1, G//4) ticks: `tick, generation, population, annual_temperature_c, anomaly_c, mean_optimum_c, sd_optimum_c, mean_stress`)
  - Definitions follow spec §6. `ratio = n_final/n_pre` (0 when extinct). `lag_c` = mean over warming generations [b+w−5, b+w) of `anomaly − (mean_optimum − theta0)`.
- `calibrate_generation_ticks(base: dict, seeds: list[int], *, provisional_ticks_per_year: int = 300, burn_in_ticks: int = 1500, measure_ticks: int = 6000, breadth_c=None, monthly_c=None) -> dict` with keys `generation_ticks` (int), `slopes`, `seeds`, `ticks_per_second`. Mean generation depth is sampled every 100 ticks, OLS slope per seed, G = round(1/mean slope).
- `run_tasks(tasks: list[dict], results_path: Path, *, workers: int, progress: Callable[[dict], None] | None = None) -> list[dict]`.
  - Each task is `{"key", "config": <config dict>, "seed", "generation_ticks", "phases": {b,w,h}, "meta": {...}}`.
  - Resumable: existing valid JSON lines are loaded and skipped; an unparsable trailing line is dropped and its task rerun.
  - Output rows are appended and flushed as each finishes: `{"key", "meta", **outcome}`, or `{"key", "meta", "status": "error", "error": str}`.
  - Uses `ProcessPoolExecutor` when workers > 1, otherwise in-process. Returns rows sorted by key.
- `sweep_tasks(base: dict, *, rates, arms=("heritable","none"), seeds, generation_ticks, phases) -> list[dict]`

- [ ] **Step 1: Tune `config/climate-rescue.json`.** Start from `config/showcase.json`: world 480×320, ecology off, Gompertz kept. Scale population and resources down and lower minimum_age, cooldown and senescence age. Climate is enabled with the Western Ghats `monthly_c` (from Task 5), ω = 4, inheritance heritable. Iterate with `calibrate_generation_ticks` (3 seeds) and a rate-0 `run_replicate` (4 seeds) until the spec §6 acceptance criteria hold: G ≤ 400, ≥ 100 ticks/s per process, rate-0 survival ≥ 90 % (4/4 in the pilot). Record the final pilot numbers in the config's sibling `config/climate-rescue.README.md`.
- [ ] **Step 2: Write failing tests** (they use the rescue config with phases (1, 2, 1) and G from a fast fixture value of 120 for speed)

```python
def test_build_config_knots_and_capacity_scaling():
def test_amplitude_override_builds_sinusoid():
def test_replicate_outcome_schema_and_determinism():          # same inputs -> identical dict except elapsed_seconds
def test_extinct_replicate_serializes_with_nulls():            # rate 30 °C/gen -> survived False, lag_c None, json.dumps(allow_nan=False) ok
def test_run_tasks_resumes_and_drops_partial_line(tmp_path):   # 3 tasks; truncate the file mid-line after 2; rerun -> 3 rows, 2 were not recomputed
def test_run_tasks_parallel_matches_serial(tmp_path):          # workers=2 vs 1 -> identical rows (minus elapsed_seconds)
def test_calibration_returns_positive_generation_ticks():
```

- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement `protocol.py`.** `_execute(task)` is a top-level function so it can be pickled. Rows exclude `elapsed_seconds` when compared.
- [ ] **Step 5: Run** the tests. Expected: PASS.
- [ ] **Step 6: Commit** `feat(climate): tuned rescue world, generation calibration, resumable parallel replicates`.

### Task 7: Sweep analysis and scientific criteria

**Files:**
- Create: `src/evolution_sim/climate/analysis.py`
- Test: `tests/climate/test_climate_analysis.py`

**Interfaces:**
- `wilson_interval(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]`
- `fit_logistic(rates: ndarray, survived: ndarray) -> tuple[float, float]`. Uses scikit-learn `LogisticRegression(C=10.0)` on rate/max_rate; returns (b0, b1) in original units. A single-class input raises `ValueError`.
- `critical_rate(rows, arm, *, n_boot=2000, seed=0) -> dict` with keys:
  - `estimate`, `ci95` (`[lo, hi]` or null)
  - `undefined_fraction`
  - `curve: [{rate, n, survived, p, wilson_lo, wilson_hi}]`
  - `logistic: {b0, b1}`

  Bootstrap resamples seeds within each rate. A resample with one class, or with a critical rate outside [0, 2·max_rate], counts as undefined.
- `rescue_gain(rows, *, n_boot=2000, seed=0) -> dict`: `{estimate, ci95, undefined_fraction}`, a paired bootstrap that uses the same seed indices for both arms.
- `lag_regression(rows, *, arm="heritable", below_rate: float) -> dict`: `{slope, intercept, pearson_r, n}`, over surviving rows with non-null lag at rate < below_rate. r is null if n < 3.
- `signature_frequency(rows, arm="heritable") -> list[{rate, fraction}]`
- `summarize_sweep(rows, *, n_boot, seed) -> dict` with keys `critical_rate` (per arm), `rescue_gain`, `lag`, `signature`, `shift` (per arm per rate: mean evolved_shift_c of survivors) and `criteria`.
- `sweep_criteria(summary) -> list[dict]` with keys `id, statement, value, threshold, passed` for these criteria:
  - C1: rate-0 heritable survival ≥ 0.9
  - C2: Spearman ρ(rate, heritable survival) ≤ −0.8
  - C3: rescue gain CI lower bound > 0
  - C4: at rates ≤ k_c/2, mean heritable shift ≥ 0.5 × total warming, and ≥ 2 × the control shift
  - C5: lag pearson_r ≥ 0.8
  - C6: zero invariant errors and zero error rows

- [ ] **Step 1: Write failing tests on synthetic rows** (a generator `fake_rows(kc_heritable=0.4, kc_none=0.15, seeds=12)` with deterministic survival = rate < kc, plus a noisy variant):

```python
def test_wilson_matches_known_value():                # k=9,n=12 -> (0.4677, 0.9111) abs 1e-3
def test_critical_rate_recovers_threshold():          # estimate within 0.06 of 0.4; ci95 contains 0.4
def test_perfect_separation_is_finite():              # deterministic rows -> finite estimate, undefined_fraction in [0,1]
def test_rescue_gain_positive():                      # ci95[0] > 0
def test_lag_regression_linear():                     # lag = 2*rate exactly -> slope 2, r 1
def test_criteria_report_pass_and_fail():             # flip data -> C3 fails
def test_summary_is_json_serializable():              # json.dumps(allow_nan=False)
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): critical-rate statistics, rescue gain and success criteria`.

### Task 8: Sobol sensitivity engine

**Files:**
- Create: `src/evolution_sim/climate/sensitivity.py`
- Test: `tests/climate/test_climate_sensitivity.py`

**Interfaces:**
- `@dataclass(frozen=True) Parameter(name, low, high, unit, description)`
- `PARAMETERS: tuple[Parameter, ...]`, in this order:
  - `rate_c_per_gen`: [0.0, R], where R = 1.5 × the heritable critical-rate estimate from the sweep, rounded up to 0.05. Passed in through `parameters(rate_high)`.
  - `breadth_c` [2, 8], `amplitude_c` [0.5, 8], `founder_sd_c` [0.25, 2], `segregation_sd_c` [0, 1], `capacity_scale` [0.5, 1.5]
- `parameters(rate_high: float) -> tuple[Parameter, ...]`
- `latin_hypercube(n: int, d: int, seed: int) -> ndarray` (scipy `qmc.LatinHypercube`)
- `scale(unit: ndarray, params) -> ndarray`
- `design_conditions(points: ndarray, params, *, arm="heritable", seed0: int) -> list[RescueCondition]` (seed = seed0 + row index)
- `saltelli(n: int, d: int, seed: int) -> tuple[ndarray, ndarray]` (scrambled `qmc.Sobol(2d)`, `random_base2(log2 n)`; n must be a power of 2, else ValueError)
- `sobol_indices(f: Callable[[ndarray], ndarray], d: int, *, n: int = 4096, seed: int = 0, n_boot: int = 200) -> dict` with keys `S1, ST, S1_ci, ST_ci` (lists, length d). f takes unit-cube points.
  - Jansen estimators, with V = var(concat(fA, fB)):
  - S1_i = (V − ½·mean((fB − fABi)²)) / V
  - ST_i = ½·mean((fA − fABi)²) / V
- `ishigami(unit: ndarray, a=7.0, b=0.1) -> ndarray` (maps [0,1] to [−π, π])

- [ ] **Step 1: Write failing tests**

```python
def test_ishigami_indices_match_analytic():   # n=2**14: S1≈(0.3139,0.4424,0.0), ST≈(0.5576,0.4424,0.2437) abs 0.03
def test_saltelli_requires_power_of_two():
def test_lhs_is_stratified():                 # each column: exactly one point per 1/n bin
def test_design_conditions_map_parameters():  # values equal scaled design; seeds unique
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): Saltelli/Jansen Sobol indices verified on Ishigami`.

### Task 9: Gaussian-process surrogate

**Files:**
- Create: `src/evolution_sim/climate/surrogate.py`
- Test: `tests/climate/test_climate_surrogate.py`

**Interfaces:**
- `class Surrogate` with:
  - `__init__(self, params: tuple[Parameter, ...], seed: int = 0)`
  - `fit(self, X: ndarray, ratio: ndarray, survived: ndarray) -> Surrogate`. Takes physical units; scales X to the unit cube by params. GPR kernel: `ConstantKernel(1.0)*Matern(length_scale=[0.3]*d, nu=2.5)+WhiteKernel(0.01)`, `normalize_y=True`, `n_restarts_optimizer=3`. The target `ratio` is clipped to [0, 2]. GPC kernel: `ConstantKernel(1.0)*Matern(length_scale=[0.3]*d, nu=2.5)`. If survived is single-class, the classifier is replaced by that constant probability and `self.degenerate_classifier = True`.
  - `predict(self, X) -> dict` with keys `ratio_mean, ratio_sd, survival_probability` (ndarrays)
  - `in_domain(self, X) -> ndarray[bool]`
  - `save(self, directory: Path) -> None`, writing `model.joblib` and `model.json` (params, n, kernels, sklearn version, seed)
  - `Surrogate.load(directory) -> Surrogate`
- `cross_validate(params, X, ratio, survived, *, folds=5, seed=0) -> dict` with keys `r2_folds, r2_mean, auc_folds, auc_mean`. AUC is null for single-class folds.
- `holdout_metrics(model, X, ratio, survived) -> dict` with keys `r2, auc, accuracy, brier, n`

- [ ] **Step 1: Write failing tests** on a synthetic function: `ratio = clip(1 − 1.2·rate + 0.1·breadth/8 + noise, 0, 2)`, `survived = ratio > 0.2`, 120 points.

```python
def test_surrogate_fits_synthetic_signal():          # holdout r2 ≥ 0.8, auc ≥ 0.9
def test_survival_probability_decreases_with_rate():
def test_save_load_round_trip(tmp_path):             # identical predictions (abs 1e-12)
def test_single_class_is_degenerate_not_crash():
def test_in_domain_flags_outside_points():
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): Gaussian-process surrogate with CV, hold-out metrics and persistence`.

### Task 10: Regional SSP assessment

**Files:**
- Create: `src/evolution_sim/climate/assess.py`
- Test: `tests/climate/test_climate_assess.py`

**Interfaces:**
- `@dataclass(frozen=True) AssessmentRequest` fields:
  - `region: RegionClimate`, `generation_years: float` (0.05 to 50)
  - `breadth_c: float`, `ssps: tuple[str, ...]`
  - `regional_factor: float = 1.0`, `seeds: tuple[int, ...] = tuple(range(12))`
  - `start_year: int = 2025`, `end_year: int = 2100`
  - `max_warming_generations: float = 60`
  - `founder_sd_c: float | None = None`, `segregation_sd_c: float | None = None`
- `verdict(p: float) -> str`: "likely persists" if p ≥ 0.8, "at risk" if p ≥ 0.2, else "likely lost"
- `plan_ssp(request, ssp, generation_ticks) -> dict` with keys:
  - `rate_c_per_year`, `rate_c_per_generation`, `start_anomaly_c`
  - `span_years` = min(end−start, max_warming_generations·g), `truncated: bool`
  - `ticks_per_year` = max(4, round(G/g))
  - `knots` (years: (0, a0), (8g, a0), (8g+span, a0+rate·span))
  - `phases` (b = 8, w = span/g, h = 8)
  - `founder_mean_c` = annual_mean + a0
- `assess(request, base: dict, *, results_dir: Path, workers: int, sweep_summary: dict | None = None, sweep_domain: dict | None = None, surrogate: Surrogate | None = None) -> dict` with keys `request`, `calibration`, `ssps: [{ssp, plan, direct: {survived, n, p, wilson}, verdict, sweep: {p} | {"status": "outside sweep domain"} | null, surrogate: {p, ratio_mean, ratio_sd} | {"status": "outside surrogate domain"} | null, observed_trend_c_per_decade}]` and `caveats`. It writes `assessment.json` and `results.jsonl` into results_dir.
- `sweep_domain` = `{"amplitude_c", "breadth_c"}` of the reference sweep. "In domain" means within ±25 % (spec §8.1).

- [ ] **Step 1: Write failing tests** (a fake region with a small amplitude; 2 seeds, a small G of 80 injected through a `calibration_override` keyword for speed)

```python
def test_plan_ssp_math():                       # g=2, SSP2-4.5: rate/yr=1.8/85, per gen ×2, a0=1.8*20/85, truncation when 75>60g
def test_verdict_thresholds():
def test_outside_domains_reported():            # breadth 12 vs sweep 4 -> "outside sweep domain"; surrogate in_domain False -> status
def test_assess_end_to_end_small(tmp_path):     # JSON-serializable, direct.n == len(seeds)
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement** (calls `calibrate_generation_ticks` with the region's monthly_c and the user's breadth, seeds (101, 102), unless `calibration_override` is given). **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): regional SSP survival assessment with direct simulation and domain checks`.

### Task 11: Figures and offline HTML report

**Files:**
- Create: `src/evolution_sim/climate/figures.py`, `src/evolution_sim/climate/report.py`
- Test: `tests/climate/test_climate_report.py`

**Interfaces:**
- `figures.py` (each returns PNG bytes, Agg backend, 150 dpi, colour-blind-safe palette, labelled axes with units):
  - `survival_curve(summary)`: per-arm Wilson bars + logistic curve + k_c lines
  - `trajectories(rows, rates)`: population and lag vs generation for representative heritable seeds
  - `lag_vs_rate(summary, rows)`
  - `shift_vs_rate(summary)`
  - `sobol_bars(sobol)`: S1/ST with CIs
  - `surrogate_parity(validation)`: predicted vs observed ratio on the hold-out set
  - `assessment_panel(assessment)`: per-SSP direct p with Wilson bars, plus surrogate and sweep markers
- `render_report(context: dict) -> str`. Context keys: `title, generated_utc, provenance, calibration, sweep, sensitivity, surrogate_validation, assessments (list), criteria (list)`, any of which may be missing; each section renders only when present. The report is self-contained (figures as `data:image/png;base64`, inline CSS, no external URLs). It has light and dark themes via `prefers-color-scheme` and stays readable at 360 px. Required sections, in order:
  1. Question & answer: a plain-language headline with k_c ± CI in °C/generation
  2. How to read this
  3. Method (ODD summary)
  4. Critical rate
  5. Evolution vs no evolution
  6. Adaptation lag
  7. What matters most (Sobol)
  8. Surrogate accuracy
  9. Regional assessments
  10. Success criteria table
  11. Limitations (includes the Global Constraints biology sentence)
  12. Provenance (config/source hashes, data sha256, versions)
- `write_report(out_dir: Path, context: dict, figures: dict[str, bytes]) -> dict` writes `index.html`, `summary.json` and `manifest.json` (sha256 of each), atomically through temp files and replace, and returns the manifest.

- [ ] **Step 1: Write failing tests** (a context built from the synthetic rows of Task 7 and the Task 9 synthetic surrogate)

```python
def test_report_is_self_contained():           # no "http://" / "https://" except inside provenance text; contains "data:image/png;base64,"
def test_report_sections_present_in_order():
def test_missing_sections_are_skipped():       # context without sensitivity -> no "What matters most" heading, no crash
def test_manifest_hashes_match(tmp_path):
def test_report_includes_biology_disclaimer():
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(climate): figures and self-contained HTML evidence report`.

### Task 12: CLI group and end-to-end pipeline

**Files:**
- Create: `src/evolution_sim/climate/cli.py`
- Modify: `src/evolution_sim/cli.py` (an `if argv and argv[0] == "climate"` branch delegates to `climate.cli.main(argv[1:])`; the top-level help lists `climate`)
- Test: `tests/climate/test_climate_cli.py`

**Interfaces:**
- `main(argv) -> int` with subcommands:
  - `fetch --lat --lon --name --key --output [--start 1981] [--end <last full year>]`
  - `calibrate --config --seeds N... --output`
  - `sweep --config --calibration --rates R... --seeds-count N --output-dir --workers`
  - `sensitivity --config --calibration --sweep-dir --points 256 --holdout 64 --output-dir --workers`. This writes `design.jsonl`, `holdout.jsonl`, `surrogate/`, `validation.json` and `sobol.json`. Sobol runs on the surrogate's survival probability and ratio_mean with n = 4096.
  - `assess --region KEY|PATH --generation-years --breadth --ssp ... --seeds-count --output-dir [--sweep-dir] [--sensitivity-dir] [--regional-factor] --workers`
  - `report --root DIR --output DIR`: reads `calibration.json`, `sweep/`, `sensitivity/` and `assess/*/` when present
  - `pipeline --profile quick|full --output-root DIR --workers`
- `PROFILES` constant:
  - `quick`: rates (0, 0.3, 1.2), 3 seeds, phases (2, 4, 2), LHS 24 + 8, n_boot 200, assess western-ghats SSP2-4.5 and SSP5-8.5, 3 seeds
  - `full`: bracketed rates (pilot-determined, 9 values, stored in the profile), 12 seeds, phases (8, 20, 8), LHS 256 + 64, n_boot 2000, assess all 3 regions × 4 SSPs, 12 seeds, g = 1 yr, ω = 4 °C
- `pipeline` is resumable. It runs calibrate → sweep → sensitivity → assess → report and prints a criteria table plus the report path.
- Exit codes:
  - 0: all ok
  - 2: user or config error, with a human-readable message (no traceback)
  - 3: completed but some scientific criterion failed
  - 1: invariant or error rows
- `--workers` defaults to `max(1, os.cpu_count() - 1)`.

- [ ] **Step 1: Write failing tests**

```python
def test_climate_help_lists_subcommands(capsys):
def test_bad_region_is_friendly_error(capsys):        # exit 2, "Unknown region" in stderr
def test_quick_pipeline_end_to_end(tmp_path):         # marked slow: exit in {0,3}; report index.html exists; rerun skips all tasks
def test_report_only_rerenders(tmp_path):             # uses quick output; deterministic summary.json
```

- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS, including `-m slow` for the pipeline test.
- [ ] **Step 5: Commit** `feat(climate): vikasa climate CLI and resumable pipeline profiles`.

### Task 13: Godot demo config and HUD readout

**Files:**
- Create: `config/climate-demo.json`
- Modify: `godot/scripts/HUD.gd`
- Test: `tests/climate/test_climate_demo_config.py`

**Interfaces:**
- The demo config is based on `config/showcase.json`, with climate enabled, Western Ghats climatology, `ticks_per_year` 384 and anomaly knots `[[0,0],[3,0],[23,6.0]]` (visible warming within a viewing session). It is labelled as a demonstration, not evidence.
- HUD: when `state.environment.temperature_c` exists, `weather.text` appends `· %.1f °C`. Its tooltip shows `mean_optimum_c`, `lag_c` and `mean_stress` from `state.climate`. The HUD is unchanged when they are absent.

- [ ] **Step 1: Write the failing test.** `SimulationConfig.from_json("config/climate-demo.json")` is valid and climate is enabled. A 2,000-tick headless run has no invariant errors. The bridge document has `climate.mean_optimum_c`.
- [ ] **Step 2: Implement the config and HUD.** If a Godot binary is resolvable by `bridge._godot_binary(None)`, run `godot --headless --path godot --quit-after 120` and confirm no script errors. Otherwise record that Godot was not available, and rely on the bridge test plus a GDScript review.
- [ ] **Step 3: Run** the test. Expected: PASS.
- [ ] **Step 4: Commit** `feat(climate): Godot warming demo with live °C and adaptation readout`.

### Task 14: Production evidence run

**Files:**
- Create: `docs/results/climate-rescue-2026-10-18/` (`index.html`, `summary.json`, `manifest.json`, `calibration.json`, `sweep-summary.json`, `sobol.json`, `validation.json`, `assessments.json`, `figures/*.png`)

- [ ] **Step 1: Rate-grid pilot.** Use the heritable arm only, 4 seeds, rates (0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.2, 1.6). Choose 9 rates so survival in the full grid spans ≥ 0.9 down to ≤ 0.1, with ≥ 4 rates inside the transition band. Store them in `PROFILES["full"]["rates"]` and commit.
- [ ] **Step 2: Run** `vikasa climate pipeline --profile full --output-root exports/climate/full --workers 11` in the background, resuming after any interruption until it completes.
- [ ] **Step 3: Check the criteria table.** If a criterion fails, diagnose it with `superpowers:systematic-debugging`:
  - A failure caused by a model bug: fix the bug (with a test) and rerun the affected stages.
  - A failure because the effect isn't there (a genuine scientific result): keep it, and report it as found in the report and docs. Never tune parameters after the fact to force a pass.
  - Surrogate below S9: escalate design points 256 → 512 once, then report.
- [ ] **Step 4: Copy the report package and the small JSON/figures into `docs/results/climate-rescue-2026-10-18/`** (no JSONL trajectories). Verify the manifest hashes.
- [ ] **Step 5: Commit** `docs(climate): full-profile evidence package`.

### Task 15: Documentation and final verification

**Files:**
- Create: `docs/CLIMATE_RESCUE.md`
- Modify: `README.md` (a new section after "Vikasa 2.0", covering the question, a quick start, the commands and a results headline linking to the evidence)

- [ ] **Step 1: Write `docs/CLIMATE_RESCUE.md`** in ODD structure (Purpose; Entities, state variables & scales; Process overview & scheduling; Design concepts; Initialisation; Input data; Submodels). Follow with: Experimental protocol, Results (numbers copied from `summary.json`), How to run your own region, Limitations, and References. References: Lynch & Lande 1993; Gomulkiewicz & Holt 1995; Bürger & Lynch 1995; Bell & Gonzalez 2009; Huey & Kingsolver 1989; Walsh et al. 2019; Grimm et al. 2006/2020; Saltelli et al. 2010; Jansen 1999; Rasmussen & Williams 2006; IPCC AR6 WG1 Ch. 4; NASA POWER.
- [ ] **Step 2: Run full verification.**
  - `ruff check src tests`
  - `pytest -q -m "not slow"`
  - `pytest -q -m slow tests/climate`
  - the legacy fingerprint test
  - `vikasa climate --help`
  - every subcommand `--help`
  - `tests/test_documentation.py` (README links)

  Expected: all pass, with zero ruff findings.
- [ ] **Step 3: Request a whole-branch review** (`superpowers:requesting-code-review`), apply the valid findings, and re-verify.
- [ ] **Step 4: Commit** `docs(climate): ODD protocol, results and README quick start`.

---

## Desired Final Output (deliverable standard)

The finished project is one command and one artifact:

```powershell
.\.venv\Scripts\vikasa.exe climate pipeline --profile full --output-root exports\climate\full
# -> exports\climate\full\report\index.html   (offline, single file)
```

The report must meet this standard:

| Element | Standard |
|---|---|
| Headline | One sentence: "Under this model, populations survive warming up to **k_c [CI] °C per generation**; heritable adaptation raises the tolerable rate by **gain [CI]**." |
| Every number | Has its unit, its sample size, and a CI or Wilson interval where it is an estimate |
| Every figure | Labelled axes with units, a legend, a one-line "how to read" caption |
| Regional table | Region × SSP: warming °C/yr, °C/gen, direct P [Wilson], verdict, surrogate P ± sd or "outside domain", sweep P or "outside domain", truncation note |
| Provenance | Config SHA-256, source SHA-256, data SHA-256 + retrieval date, package versions, seeds |
| Honesty | Biology disclaimer, limitations section, failed criteria shown as failed |
| Portability | Opens offline in any modern browser; no server; readable on phone and desktop; light and dark |

## Testing Standard

- Unit tests for every public function named in the Interfaces blocks, plus the 5 Review Focus tests.
- Invariants: legacy fingerprints bit-identical; climate runs deterministic per seed; serial and parallel results identical; resume idempotent.
- Numerical verification against known answers: Ishigami Sobol indices, Wilson values, a synthetic logistic threshold, synthetic GP signal, the OLS trend.
- An end-to-end `quick` pipeline test (marked slow) covering every stage and the report.
- Static: ruff clean.

## Success Criteria for the Final Project

The engineering criteria (S1–S8) must pass. The scientific criteria (C1–C6, S9–S10) are measured and reported honestly: pass or fail is shown in the report, and a failing one is explained, not hidden.

| ID | Criterion | Threshold |
|---|---|---|
| S1 | Existing suite + legacy fingerprints | all pass |
| S2 | New climate tests incl. slow pipeline | all pass |
| S3 | Determinism | same seed → identical outcome rows; serial = parallel |
| S4 | Resumability | an interrupted full pipeline completes on rerun without recomputing finished keys |
| S5 | Usability | each subcommand has `--help`; user errors exit 2 with a one-line message; README quick start reproduces the report; bundled data works offline |
| S6 | Report standard | meets every row of the deliverable standard table |
| S7 | Provenance | data files carry URL, retrieval UTC, SHA-256; SSP constants cite AR6 Table 4.5 |
| S8 | Code quality | ruff clean; whole-branch review findings resolved |
| C1 | Baseline viability | rate-0 heritable survival ≥ 0.9 |
| C2 | Monotonic risk | Spearman ρ(rate, survival) ≤ −0.8 |
| C3 | Evolution rescues | rescue-gain 95 % CI lower bound > 0 |
| C4 | Adaptive tracking | shift ≥ 0.5 × warming and ≥ 2 × control at rates ≤ k_c/2 |
| C5 | Lag ∝ rate (Lynch–Lande) | Pearson r ≥ 0.8 |
| C6 | Integrity | zero invariant errors, zero error rows |
| S9 | Surrogate accuracy | hold-out R² ≥ 0.7 (ratio) and AUC ≥ 0.85 (survival) |
| S10 | Sobol sanity | warming rate in the top 2 by total-order index for survival |
