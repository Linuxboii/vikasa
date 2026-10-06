# Vikasa Ecosystem v2 Design

> **Status: historical/superseded.** This concept is not the current implementation specification. The approved replacement is [the 2026-10-05 wildlife experience spec](2026-10-05-vikasa-wildlife-experience-design.md); see [the scientific model](../../SCIENTIFIC_MODEL.md), [architecture](../../ARCHITECTURE.md), and [README](../../../README.md) for delivered scope. Proposed deployment, release, and remote-push steps below were planning intent only; they are not evidence that those actions were performed.

**Status:** Approved concept, implementation specification  
**Date:** 2026-10-04  
**Product:** Vikasa  
**Target release:** v2.0.0

## 1. Purpose

Vikasa v2 turns the existing individual-organism evolution simulator into a readable, deterministic ecosystem laboratory. Users must be able to see why populations rise or fall, identify the dominant species, inspect the traits and mutations that formed a species, observe habitat and territory pressure, and run the same model through either the graphical application or the command line.

The simulation remains an educational abstraction. A “species” is a stable simulated clade defined by genetic distance, ancestry, and reproductive compatibility; it is not a claim that the model reproduces every biological species concept.

## 2. User goals

The release must let a user:

- distinguish organisms visually without opening an inspector;
- follow a live ranked species leaderboard and select any species;
- understand a selected species' physical traits, instincts, habitat, ancestry, and founding mutations;
- watch organisms choose among food, safety, shelter, mating, social activity, territory defense, migration, and exploration;
- see terrain, shelters, territories, seasons, weather, hazards, and recovery affect survival and reproduction;
- relate simulation time to real time through explicit, adjustable time profiles;
- manipulate the world from a rich GUI and perform equivalent operations from the CLI;
- save, resume, export, and reproduce a run from a seed.

## 3. Non-goals

- Molecular genetics, chromosomes, gene regulation, and embryology are outside v2.
- The model does not claim taxonomic or ecological predictive accuracy for real species.
- Organisms do not possess language, planning, or human-like goals. “Instinct” means a heritable weighting in a deterministic utility model.
- The simulation will not use a nondeterministic machine-learning policy.
- Networked multiplayer and cloud persistence are outside v2.

## 4. Design principles

1. **Causality must be visible.** Every species split, mutation, environmental change, and population trend must be inspectable.
2. **One engine, two interfaces.** GUI and CLI call the same configuration, simulation, event, checkpoint, and export services.
3. **Determinism first.** A seed, configuration, action log, and checkpoint produce the same state and species identities.
4. **Biological plausibility over fantasy.** Appearance and behavior derive from genes, state, habitat, and trade-offs.
5. **Scale gracefully.** The default experience remains smooth with at least 100 living organisms and useful at larger populations.

The behavioral trade-off model is motivated by work connecting life-history strategy and animal personalities ([Wolf et al.](https://www.nature.com/articles/nature05835)). Habitat choice, territorial movement, reproductive assortment, and landscape resources follow simplified patterns supported by research on [movement and habitat selection](https://pmc.ncbi.nlm.nih.gov/articles/PMC13190373/), [territorial movement](https://pmc.ncbi.nlm.nih.gov/articles/PMC4032549/), [assortative mating and speciation](https://pmc.ncbi.nlm.nih.gov/articles/PMC2516082/), [agent-based pair formation](https://pmc.ncbi.nlm.nih.gov/articles/PMC7512863/), and [resource and shelter landscapes](https://pmc.ncbi.nlm.nih.gov/articles/PMC7561532/).

## 5. System architecture

The existing deterministic engine remains authoritative. New domain services are integrated into its ordered tick pipeline rather than calculated after rendering.

| Area | Responsibility | Proposed location |
|---|---|---|
| Genome | Physical and behavioral genes, mutation deltas, genetic distance | `src/evolution_sim/model/genome.py`, `genetics.py` |
| Organisms | Runtime state, behavior state, home range, health, species identity | `src/evolution_sim/model/entities.py` |
| Behavior | Need calculation, utility scoring, action selection | `src/evolution_sim/model/behavior.py` |
| Species | Registry, deterministic assignment, splits, lineage, phenotype summaries | `src/evolution_sim/model/species.py` |
| Terrain | Habitat grid, shelters, productivity, water, exposure, recovery | `src/evolution_sim/simulation/terrain.py` |
| Time | Calendar, seasons, time profiles, real-time compression | `src/evolution_sim/simulation/clock.py` |
| Environment | Weather, hazards, disease, habitat-specific effects | `src/evolution_sim/simulation/environment.py` |
| Engine | Ordered orchestration and action log | `src/evolution_sim/simulation/engine.py` |
| Analytics | Species, behavior, climate, diversity, and territory series | `src/evolution_sim/analytics/metrics.py` |
| Persistence | Versioned checkpoint migration and exports | `src/evolution_sim/persistence/` |
| GUI | Responsive layout, leaderboard, inspector, controls, charts | `src/evolution_sim/ui/` |
| CLI | Commands exposing the same services and vocabulary | `src/evolution_sim/cli.py` |

### 5.1 Tick order

Every tick executes in this fixed order:

1. advance the simulation calendar;
2. update seasons, weather, active events, habitat recovery, and resource growth;
3. rebuild spatial indexes;
4. calculate each organism's needs and deterministic behavior choice in organism-ID order;
5. apply movement, foraging, sheltering, courtship, defense, social, migration, and exploration actions;
6. resolve energy, thermal load, health, disease, aging, and deaths;
7. resolve compatible mating pairs and births;
8. assign newborns to species or create deterministic descendant species;
9. update territories, species summaries, population histories, and metrics;
10. record action-log entries, scheduled snapshots, and exports.

Random draws use the engine's seeded NumPy generator only. Collections involved in decisions are sorted by stable IDs before sampling or tie-breaking.

## 6. Genome and phenotype

### 6.1 Gene set

The six existing physical genes remain and receive six behavioral genes.

| Gene | Range | Primary effect |
|---|---:|---|
| `size` | 0–1 | body mass, energy reserve, movement cost, visual body size |
| `speed` | 0–1 | maximum movement speed and movement energy cost |
| `perception` | 0–1 | sensing radius and eye scale |
| `metabolism` | 0–1 | energy use, thermal response, food demand |
| `reproduction_threshold` | 0–1 | energy/health readiness threshold |
| `fertility` | 0–1 | courtship success and offspring opportunity |
| `foraging_drive` | 0–1 | preference for acquiring food |
| `survival_drive` | 0–1 | caution, hazard avoidance, and shelter response |
| `shelter_drive` | 0–1 | preference for secure resting habitat |
| `mating_drive` | 0–1 | preference for courtship when reproductively ready |
| `territoriality` | 0–1 | defense intensity and home-range exclusivity |
| `sociality` | 0–1 | preference for nearby compatible organisms |

`Genome.values` becomes a named, versioned 12-gene mapping at persistence boundaries while retaining indexed numeric storage internally for efficient vector operations. Configuration defines per-gene minimum, maximum, initial mean, initial spread, mutation rate, and mutation magnitude. Unknown genes are rejected with a precise validation error.

### 6.2 Mutation provenance

Every birth stores zero or more mutation records:

```json
{
  "gene": "shelter_drive",
  "parent_baseline": 0.42,
  "inherited_value": 0.45,
  "mutation_delta": 0.08,
  "final_value": 0.53,
  "direction": "increased",
  "birth_tick": 810,
  "organism_id": 431,
  "parent_ids": [201, 208]
}
```

Floating-point values are stored at full engine precision and displayed to three decimal places. Species founding mutations aggregate the founder cohort's gene deltas against its ancestral species centroid. Only statistically meaningful deltas at or above the configured founding-delta threshold appear as causal founding changes; smaller differences remain available in the raw export.

### 6.3 Appearance

Each organism is drawn as a directional, biomorphic animal assembled from inexpensive primitives:

- an ellipse body scaled by size and current energy;
- a head positioned along its velocity or last-facing vector;
- a tail and paired appendages scaled by speed and habitat adaptation;
- eyes scaled by perception;
- earth-derived species base colors with accessible luminance separation;
- stable species markings: stripes, spots, dorsal band, flank patch, or ring pattern;
- posture and secondary indicators for current behavior, age, sex, health, and low energy.

Shape parameters come from the physical genome; base palette and motif come from the species ID; transient state changes posture or a compact indicator, not species identity. The renderer must remain legible at ordinary zoom and fall back to simplified silhouettes at low zoom.

## 7. Instinct and behavior model

An organism evaluates normalized state signals in `[0, 1]`: hunger, hazard, thermal stress, reproductive readiness, shelter deficit, territory pressure, social isolation, resource opportunity, and novelty. It scores available actions:

```text
forage    = foraging_drive * hunger * resource_opportunity
shelter   = shelter_drive * max(hazard, thermal_stress, shelter_deficit)
court     = mating_drive * reproductive_readiness * mate_opportunity
defend    = territoriality * territory_pressure * health_factor
socialize = sociality * social_isolation * group_opportunity
migrate   = max(hunger, hazard, crowding) * low_local_quality
explore   = perception * novelty * (1 - survival_drive * hazard)
rest      = fatigue * shelter_quality
```

Scores also receive habitat suitability, distance cost, health, age, recent-action hysteresis, and a small seeded tie-break value. The largest valid score becomes the behavior state. Hysteresis prevents flicker: an action continues until another exceeds it by `behavior.switch_margin`, or the current action becomes invalid.

User-facing dominant instinct is the highest of the six behavioral genes after stable tie-breaking by the gene order above. Dominant behavior is measured from recent executed actions, so the UI distinguishes inherited tendency from current behavior.

### 7.1 Breeding

Two organisms can form a mating pair only when all are true:

- both are alive, mature, sufficiently healthy, and above their genome-derived reproduction thresholds;
- they are within perception/courtship distance;
- neither is inside a blocking cooldown;
- genetic compatibility is above the configured floor;
- habitat and territory rules permit contact;
- their pair score exceeds the configured mating threshold.

Pair score combines reciprocal mating drive, energy, health, proximity, genetic similarity, habitat preference similarity, and social/territorial compatibility. This creates assortative mating without forcing identical genomes. Parent selection and offspring mutation use the seeded engine generator.

## 8. Species and lineage

### 8.1 Genetic distance

For genomes `a` and `b`, normalized genetic distance is:

```text
d(a, b) = sqrt(sum(w_i * ((a_i - b_i) / range_i)^2) / sum(w_i))
```

Weights are configuration values and must be positive. Behavioral and physical groups receive equal total weight by default. Distance is calculated from unrounded values.

### 8.2 Species registry

`SpeciesRecord` contains:

- stable integer ID and generated common name;
- parent species ID and founding organism IDs;
- founding tick, simulated date, and extinction tick when applicable;
- current genome centroid and founder centroid;
- color, motif, and phenotype summary;
- current population and bounded population history;
- dominant instinct, dominant recent behavior, and habitat affinity;
- territory center, radius, occupancy, and home habitat distribution;
- founding mutation summary and full lineage links.

Founder populations are assigned in deterministic organism-ID order. The first unassigned founder creates a species; subsequent founders join the compatible species with the nearest centroid under `species.founder_distance`, with species ID breaking ties.

### 8.3 Birth assignment and speciation

A newborn first tests its parents' species. It remains in that species when its distance to the current species centroid is at or below `species.membership_distance` and the pair is reproductively compatible. Otherwise it joins the closest compatible species under the same threshold.

A descendant species is created only when a candidate lineage satisfies all of these conditions:

- at least `species.split_min_population` living related organisms occupy the candidate cluster;
- their centroid is at least `species.split_distance` from the ancestral centroid;
- the separation persists for `species.split_persistence_ticks`;
- mean cross-cluster mating compatibility is below `species.cross_compatibility_ceiling`;
- the cluster is internally connected by the configured membership distance.

Candidate clusters and new IDs are processed by `(ancestor_species_id, earliest_birth_tick, smallest_organism_id)`. A split reassigns the living candidate cluster and future compatible descendants, but historical records retain the species ID held at each recorded tick. Extinct species remain in the lineage registry and exports.

Species names use a deterministic two-word generator seeded from the global seed and species ID. Names, colors, and motifs never change after creation.

## 9. Habitat, shelter, and territory

### 9.1 Terrain

The world uses a deterministic low-resolution habitat grid sampled smoothly by organisms and rendered as a natural map.

| Habitat | Food | Water | Shelter | Movement | Thermal exposure | Hazard tendency |
|---|---|---|---|---|---|---|
| Grassland | high seasonal | medium | low | easy | high | drought, fire |
| Woodland | medium | medium | high | moderate | low | fire, disease |
| Wetland | high | high | medium | difficult | medium | flood, disease |
| Rocky | low | low | high | difficult | medium | cold, storm |
| Exposed | low | low | none | easy | very high | heat, cold, storm |

Each cell stores habitat type, base productivity, current food, water access, shelter quality, movement cost, thermal exposure, damage, and recovery. Shelter sites are persistent entities with position, capacity, quality, habitat, damage, and recovery state.

### 9.2 Natal imprinting and home range

Each newborn stores its birthplace, natal habitat, and a home-range preference blended from both parents and birthplace:

```text
home_center = 0.4 * birthplace + 0.3 * parent_a_home + 0.3 * parent_b_home
home_radius = clamp(parent_mean_radius * inherited_range_factor, min, max)
```

An organism's habitat utility receives a natal bonus that decays with distance from its home center and weakens during migration. The imprint is heritable context, not a gene: offspring may establish a new range when local crowding, hazards, or resource scarcity outweigh the home bonus.

### 9.3 Species territory

A species territory is a displayable aggregate of living members' home ranges. Its center is the robust population center; its radius covers the configured quantile of member distances. Territoriality tightens exclusive use, sociality encourages overlap, density expands pressure, and resource richness contracts necessary range. Territory changes are smoothed over time and do not teleport.

The map provides independent layers for habitat, food, water, shelters, territory fill, territory borders, weather, hazards, trails, and organism labels. Layer opacity is configurable.

## 10. Environment

Seasons follow the simulation calendar. Baseline temperature and rainfall use deterministic annual curves plus seeded bounded variability. Habitat response converts climate into local productivity, water, exposure, and recovery.

| Factor/event | Trigger and duration | Main effects |
|---|---|---|
| Seasonal cycle | calendar driven | temperature, rainfall, food growth, fertility |
| Drought | scheduled or threshold event | lower water/food, higher movement and metabolism cost |
| Abundance | scheduled or manual event | faster food growth and reproduction opportunity |
| Heat wave | event | thermal stress, shelter demand, exposed-habitat mortality |
| Cold snap | event | thermal stress, energy use, shelter demand, rocky/exposed risk |
| Storm | event | movement penalty, shelter benefit, local damage |
| Flood | rainfall/event | wetland displacement, food redistribution, shelter damage |
| Wildfire | dryness/event | habitat/food/shelter damage, forced migration, gradual recovery |
| Disease | density/event | health loss and reduced fertility; crowding/social contact affects spread |

Events have stable IDs, start/end ticks, intensity, affected region/habitats, source (`scheduled`, `generated`, or `manual`), and resolved effects. Manual GUI and CLI events call the same validation and scheduling service. Overlapping effects compose through documented bounded multipliers; they never mutate configuration in place.

## 11. Simulation calendar and real-time profiles

One engine tick represents exactly two simulated days. A common year has 365 simulated days, with seasons divided into four equal model quarters for deterministic display. The calendar shows elapsed day, season, year, and generation statistics. It does not model leap years.

The engine runs a configurable number of ticks per rendered frame and is not coupled to display refresh rate. A time profile specifies a target simulated-years-per-real-second; the scheduler accumulates wall-clock delta and advances the required number of ticks within a per-frame work budget. If the machine cannot sustain the target, the UI shows the achieved rate instead of skipping simulation steps.

Default profiles are:

| Profile | Target simulated years / real second | Approximate simulation time / real day |
|---|---:|---:|
| Naturalist | 0.25 | 59 years |
| Field study | 2 | 473 years |
| Generations | 20 | 4,734 years |
| Century | 100 | 23,671 years |
| Deep time | 10,000 | 2.37 million years |

The header always displays both the target and achieved ratio. Pause and single-step are exact. Deep-time rendering may reduce visual refresh frequency but must not change engine ordering, RNG use, or results.

## 12. Graphical interface

### 12.1 Layout

```text
┌ simulated calendar · season · climate · target/achieved time ratio ┐
├ species leaderboard ┬ living habitat map ┬ inspector and controls ┤
│ rank/pop/trend       │ organisms          │ species/organism       │
│ color/instinct       │ territory/shelter  │ traits/mutations        │
│ selectable rows      │ resources/weather  │ lineage/actions         │
├──────────────────────┴─────────────────────┴────────────────────────┤
│ population · species · climate · behavior · diversity timelines    │
└─────────────────────────────────────────────────────────────────────┘
```

Panels collapse responsively below the minimum comfortable width. Keyboard focus, mouse selection, high-contrast state, tooltips, and scroll behavior must work without hiding the map. Existing customization remains available and gains layer opacity, panel scale, palette, motif visibility, chart selection, and label density.

### 12.2 Species leaderboard

The left panel ranks living species by current population descending, then species ID ascending. Each row shows rank, species swatch/motif, name, population, short-term trend, and dominant instinct. Extinct species are available through a filter but do not occupy the default live ranking.

A row is a real hit-tested control. Hover highlights the species on the map. Click pins the species and opens its inspector. Keyboard users can move through rows and press Enter. Selection remains stable while ranks reorder.

The species inspector shows:

- population, trend, founding date, age, and extinction state;
- territory center/radius, occupancy, and primary habitat;
- physical phenotype and six behavioral instincts;
- dominant instinct and recent observed behaviors;
- parent species, founders, descendants, and compact lineage tree;
- exact founding gene deltas, direction, magnitude, and comparison centroid;
- recent environment pressures and population history.

Selecting an organism shows individual genome, expressed phenotype, energy, health, age, sex, behavior, home range, parents, offspring, species, and its birth mutations. A “Back to species” action restores the pinned species view.

### 12.3 Controls

The GUI exposes:

- pause, resume, single tick, and the five time profiles;
- zoom, pan, follow selection, reset view, and screenshot;
- independent map layers and opacity controls;
- species visibility, rank cutoff, habitat, sex, age, and behavior filters;
- schedule drought, abundance, heat wave, cold snap, storm, flood, wildfire, and disease with intensity/duration/region;
- food pulse, shelter placement/repair, and habitat recovery actions;
- territory and shelter visualization settings;
- restart with seed/config/preset, save checkpoint, load checkpoint, and export;
- appearance, accessibility, chart, and density customization.

Potentially destructive restart/load actions require an in-application confirmation when the current run has unsaved progress. Event scheduling does not pause the run unless the user chooses it.

## 13. CLI parity

The CLI and GUI use the same terms and service calls.

| User capability | GUI | CLI |
|---|---|---|
| List presets | setup/preset menu | `vikasa presets` |
| Run scenario | Start/restart | `vikasa run --preset NAME --years N --time-profile PROFILE` |
| Open GUI | launcher | `vikasa ui --preset NAME --time-profile PROFILE` |
| Species ranking | live leaderboard | periodic/final text leaderboard from `vikasa run` |
| Inspect species | click row | `vikasa species --checkpoint FILE [--species ID]` |
| Schedule environment | event controls | `vikasa environment --checkpoint FILE --event TYPE --intensity N --duration-years N [--region ...]` |
| Layers/metrics | map and charts | exported CSV/JSON summaries |
| Save/resume | checkpoint controls | `--checkpoint-out`, `--resume` |
| Export | export controls | `--export-dir`, `--format csv|json|both` |
| Desktop shortcut | launcher action | `vikasa shortcut --create` |

`vikasa run` prints current simulated date, achieved processing rate, total population, species count, dominant species, its population, and current environment at a bounded reporting interval. Noninteractive commands support `--json` for machine-readable output. CLI configuration overrides use the same names and validators as GUI controls.

## 14. Configuration

Configuration remains strict and versioned. New top-level sections are `behavior`, `species`, `terrain`, `clock`, `environment`, and expanded `ui`. Every shipped preset specifies or inherits validated defaults. Invalid ranges, unknown keys, contradictory thresholds, unavailable profiles, or impossible event durations fail before a run starts with the full dotted setting name.

Presets:

- **Balanced world:** readable default ecosystem;
- **Harsh frontier:** exposed terrain, scarce resources, stronger selection;
- **Sheltered abundance:** rich woodland/wetland and high social opportunity;
- **Rapid divergence:** elevated mutation and stricter reproductive separation;
- **Deep time:** performance-oriented visuals and long-horizon calendar profile.

Existing v1 presets are migrated to v2 defaults during load and keep their prior physical-gene intent.

## 15. Persistence, migration, and exports

Checkpoint schema version becomes `2`. It stores:

- configuration and seed;
- engine tick, calendar, RNG state, next IDs, and action-log cursor;
- organisms, complete genomes, mutations, behavior, health, disease, home ranges, and species IDs;
- species registry, centroids, candidate splits, population history, territory, and lineage;
- terrain grid, shelters, resources, damage/recovery, climate, and active/scheduled events;
- metrics required to continue charts without discontinuity.

A v1 checkpoint is migrated deterministically: behavioral genes use documented v2 defaults with an ID-seeded bounded variation, all living organisms are clustered into founder species, the existing world becomes a balanced terrain, and the original tick/physical genome/RNG state is retained. Migration writes a v2 checkpoint only when explicitly saved; it does not overwrite the source. Newer unknown schemas are rejected with a clear version message.

Exports include:

- `summary.json` with run/config/calendar/environment overview;
- `organisms.csv` and `organism_mutations.csv`;
- `species.csv`, `species_history.csv`, `species_mutations.csv`, and `lineage.json`;
- `environment_history.csv`, `behavior_history.csv`, and `territory_history.csv`;
- existing population/diversity metrics and charts.

Column order, numeric precision, and row ordering are stable for identical runs.

## 16. Performance and reliability

- Spatial queries must use the existing spatial index or a habitat-grid lookup; no all-pairs scan may be added to the normal tick path.
- Species centroids update incrementally. Full split clustering runs at a configurable interval, not every tick.
- Population and chart histories use bounded/downsampled series in memory; full data may stream to export.
- At low zoom or high population, renderer detail degrades before simulation correctness.
- The standard 100-organism showcase must remain interactively responsive on the target Windows device.
- Simulation results must not depend on frame rate, window size, panel state, rendering detail, or whether the CLI or GUI is used.

## 17. Error handling

- Configuration errors identify the invalid dotted field and accepted range.
- Checkpoint errors distinguish unreadable, corrupt, unsupported-newer, and failed-migration cases.
- CLI commands return nonzero status and concise corrective text.
- GUI failures preserve the current run where possible and provide a specific recovery action.
- If a target time profile cannot be sustained, the run continues correctly and reports the lower achieved rate.
- An invalid manual event is rejected atomically; it cannot partially change the world.

## 18. Verification strategy

Implementation follows test-driven development. Tests must cover:

1. genome bounds, inheritance, behavioral mutation, and provenance;
2. normalized distance, stable founder clustering, birth assignment, persistent split rules, extinction, and deterministic names;
3. need signals, utility scores, behavior hysteresis, and seeded tie-breaking;
4. assortative mating and compatibility boundaries;
5. habitat generation, shelter capacity/damage/recovery, natal imprinting, migration, and territory aggregation;
6. calendar conversion, all profiles, pause/step, achieved-rate reporting, and frame-rate independence;
7. each environmental factor, overlap composition, habitat-specific impact, and manual scheduling;
8. v1-to-v2 checkpoint migration, v2 round-trip continuation, newer-version rejection, and deterministic replay;
9. species and mutation exports with stable ordering;
10. leaderboard order, row hit-testing, stable selection, keyboard behavior, inspector data, layer toggles, and responsive layout;
11. GUI/CLI runs reaching equivalent state from the same seed and action schedule;
12. stress and performance runs at 100+ organisms;
13. rendered screenshot review at setup, normal run, selected species, active hazard, narrow window, and high population states.

## 19. Acceptance criteria

Vikasa v2 is complete only when all of the following are true:

- Organisms visibly encode species and physical traits with realistic biomorphic silhouettes.
- Twelve heritable genes influence body, survival, behavior, and breeding.
- Every organism continuously chooses among the specified behavior states from inspectable needs and instincts.
- Breeding uses readiness, compatibility, proximity, habitat, and instinct, and records inherited mutations.
- Species identities, splits, extinctions, lineage, colors, names, motifs, and founding mutations are deterministic and persistent.
- The live left-side leaderboard ranks species and selecting a row opens the complete species and mutation inspector.
- Five terrain types, persistent shelters, natal imprinting, home ranges, species territories, and configurable map layers are functional.
- Seasons plus drought, abundance, heat wave, cold snap, storm, flood, wildfire, and disease alter the correct ecological systems and are visible.
- One tick equals two simulated days; the five profiles show both target and achieved real-time compression, including millions of simulated years per real day in Deep time.
- The GUI offers the listed controls and remains responsive and accessible.
- CLI commands expose equivalent presets, time profiles, environment actions, species inspection, checkpoints, exports, and leaderboard summaries.
- Schema-v2 checkpoints resume exactly, v1 checkpoints migrate deterministically, and exports explain species history and mutation provenance.
- Automated tests, lint, deterministic replay, CLI smoke tests, checkpoint continuation, performance checks, and visual QA pass.
- README documents the model, controls, CLI, configuration, persistence, exports, scientific abstractions, installation, desktop shortcut, troubleshooting, and limitations.
- The verified release is committed, tagged, pushed to `git@github.com:Linuxboii/vikasa.git`, installed on this device, launched successfully, and the desktop shortcut starts the new version.

## 20. Delivery sequence

Implementation should proceed in dependency order:

1. schema, genome, mutation provenance, and clock;
2. terrain, shelters, environment, and organism runtime state;
3. behavior and reproduction;
4. species registry, splitting, territory, and lineage;
5. checkpoint migration, metrics, and exports;
6. CLI parity;
7. GUI layout, organism rendering, leaderboard, inspectors, controls, and charts;
8. documentation, full verification, release, push, shortcut refresh, and local launch.

Each stage must preserve a runnable deterministic core and land with its tests.
