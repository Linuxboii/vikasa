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

Data flows from validated config and a seed into the engine. At each tick the engine updates environment, food, spatial perceptions and behavior; executes selected actions; then resolves fights, feeding, reproduction and deaths in stable order. Culture and satisfaction are updated after the tick's survival events. The engine exports immutable snapshots to clients. Rendering can lag or disconnect without changing the simulation state.

## Behavior contract

`BehaviorController` receives tick-local perceived resources, threats, eligible mates, dependents, and hazard/terrain pressures. It calculates normalized drives in a stable presentation order: survival, foraging, mating, offspring care, danger avoidance, territory. Eight candidate actions—explore, forage, rest, seek mate, care, flee, patrol, challenge—are scored from weighted drive affinity plus action reward minus travel, exposure, and conflict costs.

An unavailable action is excluded rather than assigned a competing fabricated score. Danger at or above the configured preemption threshold forces flee; severe survival/injury pressure forces forage or rest. Otherwise an action persists when the alternative is within the configured hysteresis margin; near ties use seeded softmax selection. A creature's fight-wins satisfaction component modestly strengthens eligible repeat-challenge utility and the low encounter probability. The state includes the actual action, target, start tick, utility breakdown, and a human-readable reason. See [mathematical definitions](MATHEMATICS.md).

## Persistence and reproducibility

The current checkpoint is format `vikasa`, **version 3**. It stores configuration, seed, tick, NumPy PCG64 state, entities, lineage, environment, culture, behavior/home-range state, metrics and counters. Saving writes a temporary sibling, flushes it, then atomically replaces the destination.

The loader accepts **versions 1 and 2** and migrates them in memory to the current representation, supplying behavior/home-range defaults and deterministic home-radius migration where missing. Version 3 requires its new behavior/home fields and strict JSON integer IDs/references; unsupported versions and invalid invariants fail closed. Saving a migrated run writes v3; source files are not rewritten during loading.

Determinism depends on equal configuration, seed, scheduled events, tick count, software version and numerical platform. Stable IDs order sensitive updates. Checkpoints preserve the random generator and fractional food-spawn accumulator for exact continuation. Wall-clock rendering and Godot presentation do not feed back into outcomes; explicitly issued world-tool commands do.

## Runtime caveats

The engine's world is 2D. Godot supplies a 3D presentation rather than a three-dimensional physics/ecology engine. Seasonal weather cues and hazard pressure are simplified parameters, not fluid/terrain simulation. Culture is a small seeded rule system. Behavior scores are explanatory utilities, not empirically fitted probabilities of real animal action.
