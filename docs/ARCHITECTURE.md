# Architecture

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
| `bridge.py` | Loopback HTTP bridge and command handling for the Godot client. |
| `godot/` | Procedural 3D habitat, client polling, controls, HUD, world tools, and selected-creature inspection. |
| `godot/scripts/Observatory.gd`, `LiveChart.gd` | Switchable chart groups, bounded real histories, hover inspection, life/death totals and exposure shading. |
| `godot/scripts/AtmosphereOverlay.gd` | Rain, cold and fire cues using inexpensive CanvasItem drawing; no simulation feedback. |

Data flows from validated config and a seed into the engine. At each tick the engine updates environment, food, spatial perceptions and behavior; executes selected actions; then resolves fights, feeding, reproduction and deaths in stable order. Culture and satisfaction are updated after the tick's survival events. The engine exports immutable snapshots to clients. Rendering can lag or disconnect without changing the simulation state.

## Behavior contract

The bridge publishes a completed snapshot about every 160 milliseconds. HTTP readers return the last publication without waiting for the simulation lock, allowing presentation to remain responsive at high requested tick rates. Commands are serialized under the engine lock and publish their result immediately. Requested speeds are 16/48/120 ticks per second; the HUD also reports an actual rate measured from completed ticks. Unachievable catch-up work is dropped. History payloads include at most 240 metric samples and the client draws at most 180, so chart cost stays bounded.

The presentation configuration begins with 64 creatures and a population cap of 180. Above 40 creatures, cognition is deterministically staggered across six ticks; movement and vital processes execute each tick. Contest opportunities are evaluated every four ticks. Rendered creatures use shared low-detail meshes and one simple body shadow; instanced vegetation and a 30 FPS ceiling preserve GPU headroom.

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

The engine's world is 2D. Godot supplies a 3D presentation rather than a three-dimensional physics/ecology engine. Seasonal weather cues and hazard pressure are simplified parameters, not fluid/terrain simulation. Culture is a small seeded rule system. Behavior scores are explanatory utilities, not empirically fitted probabilities of real animal action.
