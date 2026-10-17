# Architecture

The spatial hash rebuild validates a full float64 cloud once, retaining sorted
IDs and immutable coordinate copies for scalar radius checks. The historical
comparison tool checks complete checkpoint equality and guards source/config
provenance; see [performance contracts](PERFORMANCE.md).

`analytics/trait_space.py` computes observer-only six-trait geometry at export.
`io/export.py` joins stable IDs/generations and hashes `trait-space.json`;
`experiments/charts.py` renders the fifth static figure, `trait_space.png`.
No geometry calculation runs in the engine tick or live bridge publishing loop.

Vikasa separates simulation outcomes from their presentation. `SimulationEngine` owns all persistent state and advances fixed, deterministic ticks. The Pygame laboratory, headless experiment runner, and Godot Living Biome are clients; none decide creature outcomes.

## Runtime boundaries

| Area | Responsibility |
| --- | --- |
| `config.py` | Typed, validated configuration and defaults, including behavior parameters. |
| `model/` | Creature/resource state, six-gene genome, temperament, lineage, spatial and genetic primitives. |
| `simulation/behavior.py` | Local perception contract, six drives, action utilities, arbitration, reason and target. |
| `simulation/engine.py` | Tick order, movement/energy, home ranges, care, fights, resource contention, reproduction, death, culture and snapshots. |
| `simulation/environment.py`, `culture.py` | Seasonal/event pressures and cue-based shared traditions. |
| `io/checkpoints.py` | Strict versioned checkpoint serialization/migration. |
| `experiments/` and `analytics/` | Scenario execution, metrics, invariant audits, and result charts/exports. |
| `ui/` | Pygame setup, controls, rendering and inspection. |
| `bridge.py` | Loopback bridge: binary frame push stream (`/stream`), slim incremental explanation document (`/state?lite=1`), sequenced event feed and command handling for the Godot client. |
| `godot/` | Procedural 3D habitat, stream client, controls, HUD, world tools, and selected-creature inspection. See [the showcase guide](SHOWCASE.md). |
| `godot/scripts/CreatureMesh.gd`, `CreatureSwarm.gd`, `shaders/creature.gdshader` | One baked quadruped mesh drawn for the whole population as near/far GPU-instanced LODs; gait and pose animated in the vertex shader; frame interpolation, births, deaths and picking. |
| `godot/scripts/Atmos.gd`, `Habitat.gd`, `WeatherFX.gd`, `LifeFX.gd`, `FoodField.gd` | Sky, presentation daylight, seasons, instanced meadow/trees/water, weather particles, life-event particles and instanced food. |
| `godot/scripts/Main.gd`, `HUD.gd`, `CameraRig.gd`, `QualityManager.gd`, `Soundscape.gd` | Director camera, lenses, photo mode, event feed, radar, legends, adaptive quality and procedural audio. |
| `godot/scripts/Observatory.gd`, `LiveChart.gd` | Switchable chart groups, bounded real histories, hover inspection, life/death totals and exposure shading. |
| `godot/scripts/AtmosphereOverlay.gd` | Screen-space vignette and faint weather tint; no simulation feedback. |

Data flows from validated config and a seed into the engine. At each tick the engine updates environment, food, spatial perceptions and behavior; executes selected actions; then resolves fights, feeding, reproduction and deaths in stable order. Culture and satisfaction are updated after the tick's survival events. The engine exports immutable snapshots to clients. Rendering can lag or disconnect without changing the simulation state.

## Behavior contract

The bridge publishes a compact binary frame up to 30 times per second and pushes it to the client over one long-lived socket, and publishes the explanatory document every 0.4 seconds, serialised once per publication. Readers receive the last publication without waiting for the simulation lock, allowing presentation to remain responsive at high requested tick rates. Per-tick births, deaths, clashes and culture entries are collected into a sequenced feed so none are lost between polls. Commands are serialized under the engine lock and publish their result immediately. Requested speeds are 16/48/120 ticks per second; the HUD also reports an actual rate measured from completed ticks. Unachievable catch-up work is dropped. History rows travel incrementally (only rows newer than the client's cursors); the client keeps at most 240 metric samples and draws at most 180, so chart cost stays bounded.

The presentation configuration begins with 64 creatures and a population cap of 180. Above 40 creatures, cognition is deterministically staggered across six ticks; movement and vital processes execute each tick. Contest opportunities are evaluated every four ticks. The whole population renders as two instanced draws plus instanced contact shadows; vegetation, food and particles are instanced and GPU-animated, and an adaptive quality manager keeps the frame rate locked to the display. Measurements are in [SHOWCASE.md](SHOWCASE.md).

The optional validated `DemographyConfig` supplies a seeded age-dependent hazard;
old configurations retain fixed-age mortality. `LineageStore.generation_of` uses
iterative, cycle-detecting ancestry traversal. Its derived cache invalidates only
the newly defined child and its descendants, retaining unaffected ancestry.
`MetricsRecorder.record_birth_cohort` observes the entire pre-birth population and
real child genomes without consuming simulation RNG. Its last 512 exact Price
observations persist in checkpoints and `evolution.json`; the bridge publishes
180. The Evolution tab uses a signed chart axis and exposes the observation scope.

`BehaviorController` receives tick-local perceived resources, threats, eligible mates, dependents, and hazard/terrain pressures. It calculates normalized drives in a stable presentation order: survival, foraging, mating, offspring care, danger avoidance, territory. Eight candidate actions—explore, forage, rest, seek mate, care, flee, patrol, challenge—are scored from weighted drive affinity plus action reward minus travel, exposure, and conflict costs.

An unavailable action is excluded rather than assigned a competing fabricated score. Danger at or above the configured preemption threshold forces flee; severe survival/injury pressure forces forage or rest. Otherwise an action persists when the alternative is within the configured hysteresis margin; near ties use seeded softmax selection. A creature's fight-wins satisfaction component modestly strengthens eligible repeat-challenge utility and the low encounter probability. The state includes the actual action, target, start tick, utility breakdown, and a human-readable reason. See [mathematical definitions](MATHEMATICS.md).

## Persistence and reproducibility

The optional `HabitatField` owns bounded plant/water arrays and cumulative flux
ledgers. It evolves independently of rendering and supplies energy for natural
resource placement; low-density cells yield accurately sized partial patches.
`SimulationEngine.add_food` records intentional external provisioning separately.
The bridge publishes bounded grid observations and the Ecology tab exposes real
histories and cell values. Checkpoint restoration validates arrays, immutable
initialization totals, reservoir balances and external input records.
See [spatial ecology equations and limitations](SPATIAL_ECOLOGY.md).

The current checkpoint is format `vikasa`, **version 3**. It stores configuration, seed, tick, NumPy PCG64 state, entities, lineage, environment, culture, behavior/home-range state, metrics and counters. Saving writes a temporary sibling, flushes it, then atomically replaces the destination.

The loader accepts **versions 1 and 2** and migrates them in memory to the current representation, supplying behavior/home-range defaults and deterministic home-radius migration where missing. Version 3 requires its new behavior/home fields and strict JSON integer IDs/references; unsupported versions and invalid invariants fail closed. Saving a migrated run writes v3; source files are not rewritten during loading.

Determinism depends on equal configuration, seed, scheduled events, tick count, software version and numerical platform. Stable IDs order sensitive updates. Checkpoints preserve the random generator and fractional food-spawn accumulator for exact continuation. Wall-clock rendering and Godot presentation do not feed back into outcomes; explicitly issued world-tool commands do.

## Runtime caveats

The headless `contrast` runner validates a complete multi-condition protocol
before execution, retains fixed-horizon trajectories and failed runs, and uses a
separate observer RNG for paired bootstrap statistics. It caps automatic metric
history independently of the biological state. Source/protocol changes reject
publication. The CLI exclusively claims a new output directory and publishes a
hashed JSON/HTML evidence package; the offline viewer cannot change the engine.
See [controlled experiment contracts](CONTROLLED_EXPERIMENTS.md).

The engine's world is 2D. Godot supplies a 3D presentation rather than a three-dimensional physics/ecology engine. Seasonal weather cues and hazard pressure are simplified parameters, not fluid/terrain simulation. Culture is a small seeded rule system. Behavior scores are explanatory utilities, not empirically fitted probabilities of real animal action.
