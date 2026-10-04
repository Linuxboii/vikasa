# Vikasa Ecosystem v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Vikasa v2 as a deterministic, visually rich ecosystem simulator with behavioral instincts, persistent species and territories, expanded environments, real-time calendar profiles, a live species leaderboard, and matching GUI/CLI capabilities.

**Architecture:** Extend the existing seeded engine with focused clock, terrain, behavior, and species modules, then make persistence, analytics, CLI, and GUI consume those shared domain services. Keep simulation decisions independent of rendering and wall-clock speed; preserve deterministic ordering and migrate schema-v1 checkpoints without overwriting them.

**Tech Stack:** Python 3.12+, NumPy 2.1+, pygame-ce 2.5+, pandas 2.2+, matplotlib 3.9+, pytest 8.3+, Hypothesis 6.112+, Ruff 0.8+

**Spec:** `docs/superpowers/specs/2026-10-04-vikasa-ecosystem-v2-design.md`

## Global Constraints

- One engine tick represents exactly two simulated days; leap years are not modeled.
- The 12 genes are `size`, `speed`, `perception`, `metabolism`, `reproduction_threshold`, `fertility`, `foraging_drive`, `survival_drive`, `shelter_drive`, `mating_drive`, `territoriality`, and `sociality`.
- All random decisions use the engine-owned seeded NumPy generator and stable-ID ordering.
- GUI and CLI invoke the same configuration, event, clock, species, checkpoint, and export services.
- Rendering state, window size, and time profile must not change simulation results.
- Checkpoint schema v2 must round-trip exactly and migrate schema v1 deterministically without overwriting its source.
- No normal tick path may introduce an all-pairs organism scan.
- Existing v1 presets and commands remain accepted through documented compatibility behavior.
- Python support remains `>=3.12`; no new runtime dependency is required.
- The standard 100-organism showcase must remain interactive on the target Windows device.

## Review Focus

- A population containing extinct and newly split species must rank only living species by default while preserving a pinned selection through rank changes; Task 10 tests this.
- A machine too slow for Deep time must report its achieved ratio and process every tick in order rather than skipping state; Task 3 tests this.
- A v1 checkpoint with a non-default RNG state must migrate reproducibly and continue without overwriting the original; Task 9 tests this.
- Concurrent hazards over the same habitat must compose bounded effects and an invalid manual event must be atomic; Task 5 tests this.
- A species split near configured distance thresholds must be stable across dictionary insertion order and save/resume boundaries; Tasks 7 and 9 test this.

---

## File Structure

### New focused modules

- `src/evolution_sim/model/behavior.py` — need signals, action utilities, hysteresis, and deterministic behavior selection.
- `src/evolution_sim/model/species.py` — species records, distance, registry, split candidates, lineage, names, colors, motifs, and territories.
- `src/evolution_sim/simulation/clock.py` — simulated calendar, seasons, time profiles, and frame-rate-independent scheduler.
- `src/evolution_sim/simulation/terrain.py` — habitat grid, shelters, local conditions, resource growth, damage, and recovery.
- `src/evolution_sim/ui/species_panel.py` — leaderboard row model, hit testing, selection, and species inspector rendering.
- `tests/model/test_behavior.py`, `tests/model/test_species.py` — behavior and species contracts.
- `tests/simulation/test_clock.py`, `tests/simulation/test_terrain.py` — calendar and habitat contracts.
- `tests/ui/test_species_panel.py`, `tests/test_cli_v2.py` — GUI/CLI parity contracts.

### Existing modules extended

- `src/evolution_sim/config.py` and `config/*.json` — strict v2 configuration and presets.
- `src/evolution_sim/model/genome.py`, `genetics.py`, `entities.py` — 12 genes, mutation provenance, behavior/home/health/species state.
- `src/evolution_sim/simulation/environment.py`, `engine.py`, `snapshots.py` — expanded hazards and ordered integration.
- `src/evolution_sim/analytics/metrics.py`, `experiments/charts.py` — species, behavior, territory, climate, and diversity series.
- `src/evolution_sim/io/checkpoints.py`, `export.py` — schema v2, migration, and causal exports.
- `src/evolution_sim/cli.py` — presets, years/time profiles, species, environment, and text leaderboard.
- `src/evolution_sim/ui/app.py`, `layout.py`, `renderer.py`, `charts.py`, `customization.py`, `widgets.py`, `theme.py` — v2 laboratory UI.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/SCIENTIFIC_MODEL.md`, `docs/DEMO_SCRIPT.md` — complete operating and model documentation.
- `pyproject.toml`, `src/evolution_sim/__init__.py` — v2.0.0 release version.

---

### Task 1: Strict v2 Configuration and Presets

**Files:**
- Modify: `src/evolution_sim/config.py`
- Modify: `config/default.json`
- Modify: `config/showcase.json`
- Create: `config/harsh_frontier.json`
- Create: `config/sheltered_abundance.json`
- Create: `config/rapid_divergence.json`
- Create: `config/deep_time.json`
- Modify: `tests/test_config.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: existing `SimulationConfig.from_dict(raw)` and strict dataclass parser pattern.
- Produces: `BehaviorConfig`, `SpeciesConfig`, `TerrainConfig`, `ClockConfig`, `EnvironmentConfig`, expanded `UiConfig`, and `SimulationConfig.from_v1_dict(raw)`.

- [ ] **Step 1: Write failing schema and compatibility tests**

```python
def test_v2_configuration_exposes_all_ecosystem_sections():
    config = SimulationConfig.from_json(CONFIG / "default.json")
    assert config.schema_version == 2
    assert config.clock.days_per_tick == 2.0
    assert config.clock.profiles["deep_time"] == 10_000.0
    assert config.species.split_distance > config.species.membership_distance
    assert set(config.terrain.habitat_weights) == {
        "grassland", "woodland", "wetland", "rocky", "exposed"
    }

def test_v1_config_gets_documented_defaults_without_losing_physical_genes(v1_config_dict):
    migrated = SimulationConfig.from_dict(v1_config_dict)
    assert migrated.genome.bounds["size"].minimum == v1_config_dict["genome"]["bounds"]["size"]["minimum"]
    assert migrated.behavior.switch_margin == pytest.approx(0.08)

@pytest.mark.parametrize("path,value", [
    ("clock.days_per_tick", 0),
    ("species.split_distance", 0.01),
    ("terrain.grid_columns", 1),
])
def test_v2_invalid_fields_name_the_exact_path(path, value):
    raw = valid_v2_dict()
    set_nested(raw, path, value)
    with pytest.raises(ConfigError, match=re.escape(path)):
        SimulationConfig.from_dict(raw)
```

- [ ] **Step 2: Run the focused tests and confirm schema types are missing**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -q`  
Expected: FAIL because the v2 sections and migration entry point do not exist.

- [ ] **Step 3: Implement immutable v2 configuration types and cross-field validation**

```python
@dataclass(frozen=True, slots=True)
class ClockConfig:
    days_per_tick: float
    profiles: dict[str, float]
    max_ticks_per_frame: int

@dataclass(frozen=True, slots=True)
class SpeciesConfig:
    founder_distance: float
    membership_distance: float
    split_distance: float
    split_min_population: int
    split_persistence_ticks: int
    cross_compatibility_ceiling: float
    founding_delta_threshold: float
    gene_weights: dict[str, float]

def _validate_species(value: SpeciesConfig) -> None:
    if value.split_distance <= value.membership_distance:
        raise ConfigError("species.split_distance must exceed species.membership_distance")
```

Add equivalent frozen types for behavior, terrain, environment, and UI; reject unknown keys; migrate absent v2 sections from constants; write all five named presets with complete values.

- [ ] **Step 4: Run configuration and documentation tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_documentation.py -q`  
Expected: PASS with all seven preset files loadable and round-trippable.

- [ ] **Step 5: Commit the configuration contract**

```powershell
git add src/evolution_sim/config.py config tests/test_config.py tests/conftest.py tests/test_documentation.py
git commit -m "feat: define Vikasa v2 ecosystem configuration"
```

### Task 2: Twelve-Gene Genome and Mutation Provenance

**Files:**
- Modify: `src/evolution_sim/model/genome.py`
- Modify: `src/evolution_sim/model/genetics.py`
- Modify: `src/evolution_sim/model/entities.py`
- Modify: `tests/model/test_genome.py`
- Modify: `tests/model/test_genetics.py`
- Modify: `tests/model/test_entities.py`

**Interfaces:**
- Consumes: `GenomeConfig`, seeded `np.random.Generator`.
- Produces: 12-value `Genome`, `MutationRecord`, and `breed_genome(parent_a, parent_b, config, rng, *, child_id, birth_tick) -> tuple[Genome, tuple[MutationRecord, ...]]`.

- [ ] **Step 1: Write failing genome, provenance, and corrupt-state tests**

```python
def test_trait_order_has_six_physical_then_six_behavioral_genes():
    assert tuple(Trait) == (
        Trait.SIZE, Trait.SPEED, Trait.PERCEPTION, Trait.METABOLISM,
        Trait.REPRODUCTION_THRESHOLD, Trait.FERTILITY,
        Trait.FORAGING_DRIVE, Trait.SURVIVAL_DRIVE, Trait.SHELTER_DRIVE,
        Trait.MATING_DRIVE, Trait.TERRITORIALITY, Trait.SOCIALITY,
    )

def test_breed_genome_records_each_actual_mutation(genome_a, genome_b, genome_config):
    child, records = breed_genome(
        genome_a, genome_b, genome_config, np.random.default_rng(44),
        child_id=9, birth_tick=70,
    )
    for record in records:
        assert child[record.gene] == pytest.approx(record.final_value)
        assert record.final_value == pytest.approx(record.inherited_value + record.mutation_delta)
        assert record.organism_id == 9
```

- [ ] **Step 2: Run focused tests and confirm trait/provenance failures**

Run: `.venv\Scripts\python.exe -m pytest tests/model/test_genome.py tests/model/test_genetics.py tests/model/test_entities.py -q`  
Expected: FAIL because behavioral traits and `MutationRecord` are absent.

- [ ] **Step 3: Implement stable gene order and provenance-producing inheritance**

```python
@dataclass(frozen=True, slots=True)
class MutationRecord:
    gene: Trait
    parent_baseline: float
    inherited_value: float
    mutation_delta: float
    final_value: float
    birth_tick: int
    organism_id: int
    parent_ids: tuple[int, int]

def breed_genome(...):
    inherited = crossover(parent_a, parent_b, config, rng)
    values = inherited.values.copy()
    records: list[MutationRecord] = []
    for trait in Trait:
        delta = _sample_mutation(trait, config, rng)
        final = float(np.clip(values[trait.index] + delta, *config.bounds[trait.value].limits))
        values[trait.index] = final
        if final != inherited[trait]:
            records.append(MutationRecord.from_values(...))
    return Genome(values), tuple(records)
```

Extend `Creature` with immutable birth mutations plus health, sex, behavior, species ID, birthplace, natal habitat, home center/radius, disease, fatigue, and facing state, each validated for finite/range-safe values.

- [ ] **Step 4: Run model tests**

Run: `.venv\Scripts\python.exe -m pytest tests/model -q`  
Expected: PASS, including seeded and bounded mutation cases.

- [ ] **Step 5: Commit the genome expansion**

```powershell
git add src/evolution_sim/model tests/model
git commit -m "feat: add behavioral genes and mutation provenance"
```

### Task 3: Calendar and Real-Time Time Profiles

**Files:**
- Create: `src/evolution_sim/simulation/clock.py`
- Create: `tests/simulation/test_clock.py`
- Modify: `src/evolution_sim/ui/app.py`
- Modify: `tests/ui/test_controls.py`

**Interfaces:**
- Consumes: `ClockConfig` and wall-clock delta supplied by the app.
- Produces: `SimulationCalendar`, `TimeProfile`, `TickScheduler.consume(real_seconds) -> int`, and achieved-rate samples.

- [ ] **Step 1: Write failing conversion, scheduler, and overload tests**

```python
def test_calendar_converts_two_days_per_tick_without_leap_years():
    calendar = SimulationCalendar(days_per_tick=2.0)
    assert calendar.at_tick(183).year == 2
    assert calendar.at_tick(183).day_of_year == 1

def test_scheduler_never_skips_ticks_when_target_exceeds_frame_budget():
    scheduler = TickScheduler(years_per_second=10_000, days_per_tick=2, max_ticks_per_frame=50)
    first = scheduler.consume(1 / 60)
    second = scheduler.consume(1 / 60)
    assert first == second == 50
    assert scheduler.backlog_ticks > 0
    assert scheduler.achieved_years_per_second < scheduler.target_years_per_second
```

- [ ] **Step 2: Run clock tests and confirm missing module failure**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_clock.py -q`  
Expected: FAIL on import of `simulation.clock`.

- [ ] **Step 3: Implement calendar, profiles, and accumulator scheduler**

```python
DEFAULT_PROFILES = {
    "naturalist": 0.25,
    "field_study": 2.0,
    "generations": 20.0,
    "century": 100.0,
    "deep_time": 10_000.0,
}

def ticks_for_elapsed(self, real_seconds: float) -> int:
    self._backlog += real_seconds * self.target_years_per_second * 365 / self.days_per_tick
    count = min(int(self._backlog), self.max_ticks_per_frame)
    self._backlog -= count
    return count
```

Pause returns zero ticks; single-step bypasses the accumulator exactly once; achieved rate uses completed ticks over a bounded real-time window.

- [ ] **Step 4: Run clock and control tests**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_clock.py tests/ui/test_controls.py -q`  
Expected: PASS and identical engine output across time profiles.

- [ ] **Step 5: Commit calendar and scheduling**

```powershell
git add src/evolution_sim/simulation/clock.py src/evolution_sim/ui/app.py tests/simulation/test_clock.py tests/ui/test_controls.py
git commit -m "feat: add simulation calendar and time profiles"
```

### Task 4: Terrain, Shelters, Natal Imprinting, and Territory Inputs

**Files:**
- Create: `src/evolution_sim/simulation/terrain.py`
- Create: `tests/simulation/test_terrain.py`
- Modify: `src/evolution_sim/model/entities.py`
- Modify: `tests/model/test_entities.py`

**Interfaces:**
- Consumes: `TerrainConfig`, seed, world dimensions, creature position/home state.
- Produces: `HabitatType`, `HabitatCell`, `Shelter`, `TerrainMap.sample(position)`, `TerrainMap.update(...)`, `imprint_home(child, parent_a, parent_b)`.

- [ ] **Step 1: Write failing deterministic map, shelter, and imprint tests**

```python
def test_terrain_generation_is_seeded_and_contains_all_habitats(terrain_config):
    first = TerrainMap.generate(terrain_config, width=800, height=600, seed=7)
    second = TerrainMap.generate(terrain_config, width=800, height=600, seed=7)
    assert first.to_dict() == second.to_dict()
    assert set(first.habitat_counts()) == set(HabitatType)

def test_newborn_home_blends_birthplace_and_parent_ranges():
    center, radius = imprint_home(
        birthplace=np.array([100.0, 80.0]),
        parent_centers=(np.array([80.0, 70.0]), np.array([120.0, 90.0])),
        parent_radii=(40.0, 60.0), inherited_range_factor=1.0,
    )
    np.testing.assert_allclose(center, [100.0, 80.0])
    assert radius == pytest.approx(50.0)
```

- [ ] **Step 2: Run terrain tests and confirm missing module failure**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_terrain.py -q`  
Expected: FAIL on import of `simulation.terrain`.

- [ ] **Step 3: Implement grid generation, sampling, shelters, damage, and recovery**

```python
class HabitatType(StrEnum):
    GRASSLAND = "grassland"
    WOODLAND = "woodland"
    WETLAND = "wetland"
    ROCKY = "rocky"
    EXPOSED = "exposed"

@dataclass(slots=True)
class Shelter:
    id: int
    position: NDArray[np.float64]
    capacity: int
    quality: float
    habitat: HabitatType
    damage: float = 0.0

    @property
    def effective_quality(self) -> float:
        return self.quality * (1.0 - self.damage)
```

Generate smoothed seeded noise without another dependency, guarantee at least one cell per configured nonzero habitat, use O(1) cell lookup, and recover food/shelter damage with bounded updates.

- [ ] **Step 4: Run terrain and entity tests**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_terrain.py tests/model/test_entities.py -q`  
Expected: PASS, including serialization and boundary-position sampling.

- [ ] **Step 5: Commit habitat foundations**

```powershell
git add src/evolution_sim/simulation/terrain.py src/evolution_sim/model/entities.py tests/simulation/test_terrain.py tests/model/test_entities.py
git commit -m "feat: add habitats shelters and natal imprinting"
```

### Task 5: Climate and Expanded Environmental Events

**Files:**
- Modify: `src/evolution_sim/simulation/environment.py`
- Modify: `tests/simulation/test_environment.py`
- Modify: `src/evolution_sim/simulation/terrain.py`
- Modify: `tests/simulation/test_terrain.py`

**Interfaces:**
- Consumes: calendar day/year, terrain, `EnvironmentConfig`, seeded RNG.
- Produces: `ClimateState`, `EventType`, regional `EnvironmentEvent`, `EnvironmentEffects`, and atomic `EnvironmentState.schedule(event)`.

- [ ] **Step 1: Write failing seasonal, overlap, habitat, and atomicity tests**

```python
@pytest.mark.parametrize("event_type", list(EventType))
def test_every_event_has_visible_bounded_effects(event_type, environment_factory):
    state = environment_factory()
    event = EnvironmentEvent.create(event_type, start_tick=10, duration_ticks=20, intensity=0.8)
    state.schedule(event)
    effects = state.effects_at(15, HabitatType.EXPOSED, np.array([10.0, 10.0]))
    assert effects.is_finite()
    assert effects != EnvironmentEffects.neutral()

def test_invalid_overlapping_event_is_atomic(environment_state):
    before = environment_state.to_dict()
    with pytest.raises(ValueError, match="duration_ticks"):
        environment_state.schedule(EnvironmentEvent(..., duration_ticks=0))
    assert environment_state.to_dict() == before
```

- [ ] **Step 2: Run environment tests and confirm unsupported event failures**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_environment.py tests/simulation/test_terrain.py -q`  
Expected: FAIL for cold snap, storm, flood, wildfire, and disease.

- [ ] **Step 3: Implement seasonal climate and bounded effect composition**

```python
class EventType(StrEnum):
    DROUGHT = "drought"
    ABUNDANCE = "abundance"
    HEAT_WAVE = "heat_wave"
    COLD_SNAP = "cold_snap"
    STORM = "storm"
    FLOOD = "flood"
    WILDFIRE = "wildfire"
    DISEASE = "disease"

def compose_effects(events, habitat, position) -> EnvironmentEffects:
    result = EnvironmentEffects.neutral()
    for event in sorted(events, key=lambda item: item.id):
        if event.affects(habitat, position):
            result = result.compose(event.effects_for(habitat))
    return result.clamped()
```

Make annual temperature/rainfall curves deterministic, model regional/habitat scope, spread disease from density/social contact, and send damage/recovery effects through `TerrainMap`.

- [ ] **Step 4: Run environment suite**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_environment.py tests/simulation/test_terrain.py -q`  
Expected: PASS for every event, overlap order, active windows, climate, and invalid input.

- [ ] **Step 5: Commit environmental systems**

```powershell
git add src/evolution_sim/simulation/environment.py src/evolution_sim/simulation/terrain.py tests/simulation/test_environment.py tests/simulation/test_terrain.py
git commit -m "feat: expand climate and environmental pressures"
```

### Task 6: Instinct Utility Model and Compatible Breeding

**Files:**
- Create: `src/evolution_sim/model/behavior.py`
- Create: `tests/model/test_behavior.py`
- Modify: `src/evolution_sim/model/entities.py`
- Modify: `src/evolution_sim/simulation/engine.py`
- Modify: `tests/simulation/test_engine.py`

**Interfaces:**
- Consumes: creature state/genome, local terrain/environment, spatial neighbors/resources, `BehaviorConfig`.
- Produces: `BehaviorState`, `NeedSignals`, `ActionUtilities`, `choose_behavior(...)`, and `mating_compatibility(a, b, species_config) -> float`.

- [ ] **Step 1: Write failing utility, hysteresis, tie, and mating tests**

```python
def test_starving_forager_prefers_food_when_safe(behavior_context):
    context = replace(behavior_context, hunger=1.0, hazard=0.0, resource_opportunity=1.0)
    decision = choose_behavior(context, previous=BehaviorState.EXPLORE, rng=np.random.default_rng(3))
    assert decision.state is BehaviorState.FORAGE

def test_switch_margin_prevents_behavior_flicker(behavior_context):
    utilities = ActionUtilities(forage=0.51, shelter=0.50)
    assert select_utility(utilities, BehaviorState.SHELTER, switch_margin=0.08) is BehaviorState.SHELTER

def test_mating_rejects_distant_incompatible_pair(creature_pair, species_config):
    a, b = creature_pair
    b.position[:] = [700.0, 500.0]
    assert mating_compatibility(a, b, species_config) == 0.0
```

- [ ] **Step 2: Run behavior and engine tests and confirm missing decisions**

Run: `.venv\Scripts\python.exe -m pytest tests/model/test_behavior.py tests/simulation/test_engine.py -q`  
Expected: FAIL because the utility model and compatibility gate are absent.

- [ ] **Step 3: Implement needs, utilities, hysteresis, actions, and mating score**

```python
class BehaviorState(StrEnum):
    FORAGE = "forage"
    SHELTER = "shelter"
    COURT = "court"
    DEFEND = "defend"
    SOCIALIZE = "socialize"
    MIGRATE = "migrate"
    EXPLORE = "explore"
    REST = "rest"

def mating_compatibility(a: Creature, b: Creature, config: SpeciesConfig) -> float:
    if not (a.ready_to_breed and b.ready_to_breed):
        return 0.0
    distance = genetic_distance(a.genome, b.genome, config.gene_weights)
    genetic = max(0.0, 1.0 - distance / config.maximum_mating_distance)
    proximity = max(0.0, 1.0 - euclidean(a.position, b.position) / courtship_radius(a, b))
    return genetic * proximity * pair_health(a, b) * habitat_affinity(a, b)
```

Use spatial-index neighborhood queries, apply action movement/energy effects in stable ID order, and make reproduction use `breed_genome` plus `imprint_home`.

- [ ] **Step 4: Run behavior, engine, and reproducibility tests**

Run: `.venv\Scripts\python.exe -m pytest tests/model/test_behavior.py tests/simulation/test_engine.py tests/simulation/test_reproducibility.py -q`  
Expected: PASS with identical outcomes for equal seed/action logs.

- [ ] **Step 5: Commit instinct-driven organisms**

```powershell
git add src/evolution_sim/model/behavior.py src/evolution_sim/model/entities.py src/evolution_sim/simulation/engine.py tests/model/test_behavior.py tests/simulation/test_engine.py tests/simulation/test_reproducibility.py
git commit -m "feat: add instinct-driven behavior and breeding"
```

### Task 7: Deterministic Species, Speciation, Lineage, and Territory

**Files:**
- Create: `src/evolution_sim/model/species.py`
- Create: `tests/model/test_species.py`
- Modify: `src/evolution_sim/simulation/engine.py`
- Modify: `src/evolution_sim/model/lineage.py`
- Modify: `tests/model/test_lineage.py`
- Modify: `tests/simulation/test_reproducibility.py`

**Interfaces:**
- Consumes: genomes, mutation records, living creatures, tick/date, terrain, `SpeciesConfig`.
- Produces: `genetic_distance`, `SpeciesRecord`, `SpeciesRegistry.assign_founders`, `assign_birth`, `update`, `leaderboard`, and `species_details`.

- [ ] **Step 1: Write failing distance, clustering, split, and insertion-order tests**

```python
def test_normalized_genetic_distance_is_symmetric_and_zero_for_self(genome_a, genome_b, weights):
    assert genetic_distance(genome_a, genome_a, weights) == 0.0
    assert genetic_distance(genome_a, genome_b, weights) == pytest.approx(
        genetic_distance(genome_b, genome_a, weights)
    )

def test_split_requires_population_distance_persistence_and_isolation(registry, divergent_family):
    for tick in range(registry.config.split_persistence_ticks):
        registry.update(divergent_family, tick=tick, calendar=calendar_at(tick))
    descendant = registry.record_for(divergent_family[0].species_id)
    assert descendant.parent_species_id == divergent_family[0].ancestral_species_id
    assert descendant.founding_mutations

def test_species_ids_ignore_input_dictionary_order(registry_factory, creatures):
    forward = registry_factory().assign_founders(creatures)
    reverse = registry_factory().assign_founders(list(reversed(creatures)))
    assert forward.identity_map() == reverse.identity_map()
```

- [ ] **Step 2: Run species tests and confirm missing registry failure**

Run: `.venv\Scripts\python.exe -m pytest tests/model/test_species.py -q`  
Expected: FAIL on import of `model.species`.

- [ ] **Step 3: Implement records, assignment, persistent split candidates, and territory**

```python
@dataclass(slots=True)
class SpeciesRecord:
    id: int
    name: str
    parent_species_id: int | None
    founding_tick: int
    founder_ids: tuple[int, ...]
    centroid: Genome
    founder_centroid: Genome
    color: tuple[int, int, int]
    motif: SpeciesMotif
    founding_mutations: tuple[SpeciesMutation, ...]
    population: int = 0
    extinct_tick: int | None = None

def leaderboard(self, *, include_extinct: bool = False) -> tuple[SpeciesSummary, ...]:
    records = (r for r in self.records.values() if include_extinct or r.population > 0)
    return tuple(sorted(map(SpeciesSummary.from_record, records), key=lambda r: (-r.population, r.id)))
```

Cluster founders and candidates in sorted organism-ID order, calculate incremental centroids, create deterministic names/colors/motifs, aggregate founding mutation deltas, preserve extinct records, and smooth territory centers/radii from member home ranges.

- [ ] **Step 4: Run species, lineage, and reproducibility tests**

Run: `.venv\Scripts\python.exe -m pytest tests/model/test_species.py tests/model/test_lineage.py tests/simulation/test_reproducibility.py -q`  
Expected: PASS for boundary thresholds, insertion-order independence, extinction, descendants, and territories.

- [ ] **Step 5: Commit species intelligence**

```powershell
git add src/evolution_sim/model/species.py src/evolution_sim/model/lineage.py src/evolution_sim/simulation/engine.py tests/model/test_species.py tests/model/test_lineage.py tests/simulation/test_reproducibility.py
git commit -m "feat: model deterministic species and territories"
```

### Task 8: Engine Pipeline, Snapshots, and Performance

**Files:**
- Modify: `src/evolution_sim/simulation/engine.py`
- Modify: `src/evolution_sim/simulation/snapshots.py`
- Modify: `tests/simulation/test_engine.py`
- Modify: `tests/simulation/test_stress.py`
- Modify: `tests/simulation/test_performance.py`

**Interfaces:**
- Consumes: clock, terrain, environment, behavior, reproduction, species registry.
- Produces: the exact ten-stage tick order from the spec, `WorldSnapshot` with species/terrain/climate/behavior data, and action-log replay.

- [ ] **Step 1: Write failing pipeline, snapshot, and no-all-pairs tests**

```python
def test_tick_pipeline_records_all_v2_systems(tiny_config):
    engine = SimulationEngine(tiny_config, seed=11)
    engine.step()
    snapshot = engine.snapshot()
    assert snapshot.calendar.tick == 1
    assert snapshot.terrain.cells
    assert snapshot.species
    assert all(creature.behavior for creature in snapshot.creatures)

def test_render_snapshot_does_not_advance_rng_or_engine(tiny_config):
    engine = SimulationEngine(tiny_config, seed=11)
    before = checkpoint_payload(engine)
    engine.snapshot()
    engine.snapshot()
    assert checkpoint_payload(engine) == before
```

- [ ] **Step 2: Run engine and stress tests and confirm incomplete snapshot failures**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation/test_engine.py tests/simulation/test_stress.py -q`  
Expected: FAIL because snapshots lack v2 systems.

- [ ] **Step 3: Integrate ordered services and immutable render snapshots**

```python
def step(self) -> WorldSnapshot:
    self.calendar.advance()
    self.environment.update(self.calendar, self.terrain, self.rng)
    self._rebuild_spatial_indexes()
    decisions = self._decide_behaviors_in_id_order()
    self._apply_actions(decisions)
    self._resolve_health_and_deaths()
    newborns = self._resolve_reproduction()
    self.species.assign_newborns(newborns, self.tick)
    self.species.update(self.creatures.values(), self.tick, self.calendar.current)
    self.metrics.maybe_record(self)
    return self.snapshot()
```

Expose query services for GUI/CLI without mutable engine internals, preserve old `step(count)` behavior if public, and use interval-based species clustering and bounded histories.

- [ ] **Step 4: Run full simulation suite and benchmark**

Run: `.venv\Scripts\python.exe -m pytest tests/simulation -q`  
Expected: PASS, including 100+ organisms, deterministic replay, and configured performance ceilings.

- [ ] **Step 5: Commit engine integration**

```powershell
git add src/evolution_sim/simulation tests/simulation
git commit -m "feat: integrate the v2 ecosystem pipeline"
```

### Task 9: Metrics, Checkpoint v2 Migration, and Causal Exports

**Files:**
- Modify: `src/evolution_sim/analytics/metrics.py`
- Modify: `src/evolution_sim/experiments/charts.py`
- Modify: `src/evolution_sim/io/checkpoints.py`
- Modify: `src/evolution_sim/io/export.py`
- Modify: `tests/analytics/test_metrics.py`
- Modify: `tests/io/test_checkpoints.py`
- Modify: `tests/io/test_export.py`

**Interfaces:**
- Consumes: complete engine state and v1/v2 payloads.
- Produces: exact v2 continuation, deterministic `migrate_v1_payload`, v2 history rows, lineage/mutation exports, and new charts.

- [ ] **Step 1: Write failing migration, continuation, and stable-export tests**

```python
def test_v1_checkpoint_migrates_reproducibly_without_overwriting_source(v1_checkpoint, tmp_path):
    original = v1_checkpoint.read_bytes()
    first = load_checkpoint(v1_checkpoint)
    second = load_checkpoint(v1_checkpoint)
    assert checkpoint_payload(first) == checkpoint_payload(second)
    assert v1_checkpoint.read_bytes() == original
    assert first.schema_version == 2

def test_v2_checkpoint_preserves_pending_species_split(engine_with_split_candidate, tmp_path):
    path = save_checkpoint(engine_with_split_candidate, tmp_path / "run.json")
    resumed = load_checkpoint(path)
    engine_with_split_candidate.step(20)
    resumed.step(20)
    assert checkpoint_payload(resumed) == checkpoint_payload(engine_with_split_candidate)

def test_species_exports_are_stably_ordered(engine, tmp_path):
    manifest = export_run(engine, tmp_path)
    rows = read_csv(manifest.species_mutations)
    assert rows == sorted(rows, key=lambda row: (int(row["species_id"]), row["gene"]))
```

- [ ] **Step 2: Run persistence tests and confirm schema/export failures**

Run: `.venv\Scripts\python.exe -m pytest tests/io tests/analytics -q`  
Expected: FAIL because v2 state and exports are absent.

- [ ] **Step 3: Implement schema v2 payloads, migration, metrics, exports, and charts**

```python
SCHEMA_VERSION = 2

def migrate_v1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    seed = int(payload["seed"])
    migrated = deepcopy(payload)
    migrated["schema_version"] = 2
    migrated["creatures"] = [migrate_v1_creature(row, seed) for row in payload["creatures"]]
    migrated["terrain"] = balanced_terrain_payload(payload["config"], seed)
    migrated["species"] = cluster_migrated_founders(migrated["creatures"], migrated["config"], seed)
    return migrated
```

Serialize RNG, next IDs, clock, terrain, shelters, environment, all organism state, species/split candidates, metrics, and action cursor; stream stable CSV/JSON files named in the spec; add species/climate/behavior/diversity chart series.

- [ ] **Step 4: Run persistence, analytics, replay, and export tests**

Run: `.venv\Scripts\python.exe -m pytest tests/io tests/analytics tests/simulation/test_reproducibility.py -q`  
Expected: PASS with byte-stable row ordering and exact resumed state.

- [ ] **Step 5: Commit persistence and explanation outputs**

```powershell
git add src/evolution_sim/analytics src/evolution_sim/experiments/charts.py src/evolution_sim/io tests/analytics tests/io
git commit -m "feat: persist and export ecosystem history"
```

### Task 10: CLI Parity and Text Leaderboard

**Files:**
- Modify: `src/evolution_sim/cli.py`
- Create: `tests/test_cli_v2.py`
- Modify: `tests/test_cli.py`
- Modify: `src/evolution_sim/experiments/runner.py`
- Modify: `src/evolution_sim/experiments/scenarios.py`

**Interfaces:**
- Consumes: presets, scheduler profile names, engine query/event/checkpoint/export services.
- Produces: `presets`, expanded `run`, `species`, `environment`, expanded `ui`, JSON output, and periodic text leaderboard.

- [ ] **Step 1: Write failing command and GUI/CLI state-equivalence tests**

```python
def test_presets_lists_all_v2_presets(capsys):
    assert main(["presets"]) == 0
    output = capsys.readouterr().out
    assert "rapid_divergence" in output
    assert "deep_time" in output

def test_run_accepts_years_profile_and_prints_dominant_species(tmp_path, capsys):
    assert main(["run", "--preset", "balanced_world", "--years", "2", "--time-profile", "generations", "--output", str(tmp_path)]) == 0
    assert "Dominant species" in capsys.readouterr().out

def test_cli_and_shared_run_service_reach_equal_state(tmp_path):
    cli_payload = run_cli_to_checkpoint(seed=42, years=1, tmp_path=tmp_path)
    service_payload = run_service_to_payload(seed=42, years=1)
    assert cli_payload == service_payload
```

- [ ] **Step 2: Run CLI tests and confirm missing parser commands**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_cli_v2.py -q`  
Expected: FAIL because `presets`, `species`, and `environment` are unavailable.

- [ ] **Step 3: Implement shared command handlers and precise errors**

```python
def _run_species(args: argparse.Namespace) -> int:
    engine = load_checkpoint(args.checkpoint)
    details = engine.species.species_details(args.species) if args.species else engine.species.leaderboard()
    print(json.dumps(to_jsonable(details), indent=2) if args.json else format_species(details))
    return 0

def _run_environment(args: argparse.Namespace) -> int:
    engine = load_checkpoint(args.checkpoint)
    engine.schedule_event(event_from_cli(args, engine.calendar))
    save_checkpoint(engine, args.output or args.checkpoint)
    return 0
```

Add bounded progress reporting with date, rate, population, species count, dominant species, and climate; ensure `--json` is clean JSON and command errors return nonzero status.

- [ ] **Step 4: Run all CLI and experiment tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_cli_v2.py tests/experiments -q`  
Expected: PASS for human and JSON output, action equivalence, and invalid inputs.

- [ ] **Step 5: Commit CLI parity**

```powershell
git add src/evolution_sim/cli.py src/evolution_sim/experiments tests/test_cli.py tests/test_cli_v2.py tests/experiments
git commit -m "feat: bring ecosystem controls to the CLI"
```

### Task 11: Species Leaderboard, Inspectors, Organism Rendering, and GUI Controls

**Files:**
- Create: `src/evolution_sim/ui/species_panel.py`
- Create: `tests/ui/test_species_panel.py`
- Modify: `src/evolution_sim/ui/layout.py`
- Modify: `src/evolution_sim/ui/renderer.py`
- Modify: `src/evolution_sim/ui/app.py`
- Modify: `src/evolution_sim/ui/charts.py`
- Modify: `src/evolution_sim/ui/customization.py`
- Modify: `src/evolution_sim/ui/widgets.py`
- Modify: `src/evolution_sim/ui/theme.py`
- Modify: `tests/ui/test_layout.py`
- Modify: `tests/ui/test_smoke.py`
- Modify: `tests/ui/test_customization.py`
- Modify: `tests/ui/test_controls.py`

**Interfaces:**
- Consumes: immutable v2 snapshots, species query data, scheduler and event services.
- Produces: responsive four-zone layout, `SpeciesLeaderboard`, pinned selection, detailed inspector, biomorphic renderer, habitat/territory layers, event controls, and v2 charts.

- [ ] **Step 1: Write failing ranking, selection, accessibility, and render tests**

```python
def test_leaderboard_orders_population_then_id_and_preserves_selection():
    panel = SpeciesLeaderboard(Rect(0, 0, 240, 500))
    panel.update([summary(8, 20), summary(3, 20), summary(1, 40)])
    assert [row.species_id for row in panel.rows] == [1, 3, 8]
    panel.select(8)
    panel.update([summary(8, 50), summary(1, 10)])
    assert panel.selected_species_id == 8

def test_clicking_row_opens_species_mutations(app, species_snapshot):
    app.set_snapshot(species_snapshot)
    app.click(app.layout.leaderboard.center_for_species(species_snapshot.species[0].id))
    assert app.inspector.mode == "species"
    assert app.inspector.model.founding_mutations

def test_narrow_window_collapses_panels_without_covering_map():
    layout = LaboratoryLayout.calculate(1024, 640, ui_scale=1.0)
    assert not layout.leaderboard.colliderect(layout.world)
    assert layout.collapsed_panels
```

- [ ] **Step 2: Run UI tests and confirm missing leaderboard/layout failures**

Run: `$env:SDL_VIDEODRIVER='dummy'; .venv\Scripts\python.exe -m pytest tests/ui -q; Remove-Item Env:SDL_VIDEODRIVER`  
Expected: FAIL because species panel, four-zone layout, and v2 snapshot rendering are absent.

- [ ] **Step 3: Implement responsive leaderboard and inspector interaction**

```python
@dataclass(slots=True)
class SpeciesLeaderboard:
    rect: pygame.Rect
    rows: list[SpeciesRow] = field(default_factory=list)
    selected_species_id: int | None = None
    scroll_offset: int = 0

    def update(self, summaries: Sequence[SpeciesSummary]) -> None:
        self.rows = build_rows(sorted(summaries, key=lambda item: (-item.population, item.id)))

    def hit_test(self, point: tuple[int, int]) -> int | None:
        return next((row.species_id for row in self.rows if row.rect.collidepoint(point)), None)
```

Render rank, swatch/motif, name, population, trend, and instinct; keep selection by ID; support hover map highlighting, wheel scroll, keyboard traversal, Enter selection, extinct filtering, species/organism modes, and Back to species.

- [ ] **Step 4: Implement biomorphic organisms, layers, controls, header, and timelines**

```python
def draw_creature(surface, view, creature, species, theme):
    center = view.world_to_screen(creature.position)
    facing = normalized_or(creature.facing, np.array([1.0, 0.0]))
    body = body_polygon(center, facing, creature.phenotype.body_length, creature.phenotype.body_width)
    pygame.draw.polygon(surface, species.color, body)
    draw_head_tail_appendages(surface, center, facing, creature, species, theme)
    draw_species_motif(surface, body, species.motif, theme)
    draw_state_indicator(surface, creature.behavior, creature.health, creature.energy, theme)
```

Add toggles/opacity for habitat, food, water, shelter, territory, weather, hazards, trails, and labels; add profile/pause/step/event/food/shelter/restart/checkpoint/export/customization controls; display calendar, season, climate, target and achieved ratio; render population/species/climate/behavior/diversity timelines.

- [ ] **Step 5: Add deterministic screenshot fixtures and visual states**

```python
@pytest.mark.parametrize("state", [
    "setup", "running", "selected_species", "wildfire", "narrow", "high_population"
])
def test_v2_visual_state_renders_nonempty_frame(state, app_factory, tmp_path):
    path = app_factory(state).render_screenshot(tmp_path / f"{state}.png")
    image = pygame.image.load(path)
    assert image.get_width() >= 1024
    assert pygame.image.tostring(image, "RGB").count(b"\x00") < image.get_width() * image.get_height()
```

- [ ] **Step 6: Run the complete headless GUI suite**

Run: `$env:SDL_VIDEODRIVER='dummy'; .venv\Scripts\python.exe -m pytest tests/ui -q`  
Expected: PASS for layout, controls, keyboard, hit testing, customization, rendering, and screenshots.

- [ ] **Step 7: Commit the v2 laboratory interface**

```powershell
git add src/evolution_sim/ui tests/ui
git commit -m "feat: build the interactive ecosystem laboratory"
```

### Task 12: Documentation, Release Verification, Push, Shortcut, and Launch

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/SCIENTIFIC_MODEL.md`
- Modify: `docs/DEMO_SCRIPT.md`
- Modify: `docs/EXPERIMENTS.md`
- Modify: `docs/images/*.png`
- Modify: `pyproject.toml`
- Modify: `src/evolution_sim/__init__.py`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_shortcut.py`

**Interfaces:**
- Consumes: all verified v2 features and the existing shortcut installer.
- Produces: v2.0.0 documentation/release, current screenshots, GitHub push, refreshed desktop shortcut, and a running local GUI instance.

- [ ] **Step 1: Write failing documentation and release-contract tests**

```python
def test_readme_documents_every_v2_operating_surface():
    text = Path("README.md").read_text(encoding="utf-8")
    for phrase in (
        "Species leaderboard", "Instincts", "Territories", "Time profiles",
        "vikasa species", "vikasa environment", "Checkpoint schema v2",
        "Desktop shortcut", "Scientific limitations",
    ):
        assert phrase in text

def test_release_versions_match():
    assert project_version() == package_version() == "2.0.0"
```

- [ ] **Step 2: Run documentation tests and confirm v2 coverage/version failures**

Run: `.venv\Scripts\python.exe -m pytest tests/test_documentation.py tests/test_shortcut.py -q`  
Expected: FAIL until documentation, screenshots, and versions are updated.

- [ ] **Step 3: Write complete user, architecture, science, demo, and experiment guides**

Document installation, first launch, all GUI panels/controls, organism appearance, species/mutations, instincts/breeding, habitat/territory, environment, calendar/time ratios, CLI command examples, configuration, checkpoints/migration, exports, reproducibility, desktop shortcut, troubleshooting, architecture, scientific abstractions, performance, and limitations. Generate real screenshots from the verified application for setup, laboratory, selected species, and environmental pressure states.

- [ ] **Step 4: Update version and reinstall editable package**

Apply this exact patch, then reinstall:

```diff
-version = "1.1.0"
+version = "2.0.0"
```

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]" --disable-pip-version-check
```

- [ ] **Step 5: Run format, lint, all tests, slow tests, and CLI smoke tests**

```powershell
.venv\Scripts\python.exe -m ruff format --check src tests
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -m slow -q
.venv\Scripts\vikasa.exe validate --config config\showcase.json
.venv\Scripts\vikasa.exe run --preset balanced_world --years 2 --time-profile generations --output work\release-smoke
.venv\Scripts\vikasa.exe species --checkpoint work\release-smoke\checkpoint.json --json
```

Expected: all checks exit 0; the smoke run exports nonempty species, mutation, environment, territory, behavior, and summary files.

- [ ] **Step 6: Perform visual and deterministic release checks**

```powershell
$env:SDL_VIDEODRIVER='dummy'
.venv\Scripts\python.exe -m pytest tests/ui/test_smoke.py tests/simulation/test_reproducibility.py tests/io/test_checkpoints.py -q
Remove-Item Env:SDL_VIDEODRIVER
```

Open generated screenshots and verify readable leaderboard hierarchy, distinct creatures, selected-species mutations, visible territories/shelters/weather, no clipping at 1024×640 and 1600×900, and meaningful charts.

- [ ] **Step 7: Commit, tag, and push the verified release**

```powershell
git add README.md docs pyproject.toml src/evolution_sim/__init__.py tests/test_documentation.py tests/test_shortcut.py
git commit -m "docs: complete Vikasa v2 release guide"
git status --short
git tag -a v2.0.0 -m "Vikasa v2.0.0"
git push origin main
git push origin v2.0.0
```

Expected: clean working tree and both branch/tag accepted by `git@github.com:Linuxboii/vikasa.git`.

- [ ] **Step 8: Refresh the desktop shortcut and launch the verified GUI**

```powershell
.venv\Scripts\vikasa.exe shortcut --create --config config\showcase.json
$process = Start-Process -FilePath .venv\Scripts\pythonw.exe -ArgumentList '-m','evolution_sim.cli','ui','--config','config\showcase.json','--time-profile','generations','--seed','2026' -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3
Get-Process -Id $process.Id
```

Expected: `C:\Users\paran\OneDrive\Desktop\Vikasa.lnk` targets the v2 environment, and the launched process remains alive after startup.

- [ ] **Step 9: Commit any verification-only documentation corrections and confirm remote state**

```powershell
git status --short
git log -1 --oneline
git ls-remote --heads --tags origin main v2.0.0
```

Expected: clean tree; local HEAD equals remote `main`; the `v2.0.0` tag resolves to the verified release; the local GUI process is running.

---

## Final Evidence Checklist

- [ ] Ruff formatting and lint pass.
- [ ] Complete normal and slow pytest suites pass.
- [ ] Same seed/config/action log yields the same checkpoint through GUI service, CLI, and save/resume.
- [ ] All five habitats and all eight event types are exercised.
- [ ] Species split, extinction, lineage, mutation provenance, leader ranking, selection, and exports are demonstrated.
- [ ] Target and achieved time compression are visible and correct.
- [ ] Six rendered UI states pass automated checks and manual visual review.
- [ ] README is sufficient for a new user to install, operate, understand, customize, troubleshoot, and extend Vikasa.
- [ ] `main` and `v2.0.0` are pushed to GitHub.
- [ ] Desktop shortcut is refreshed and a verified Vikasa v2 GUI instance is running.
