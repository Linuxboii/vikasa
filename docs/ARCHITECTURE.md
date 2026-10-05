# Architecture

## Boundary rule

The simulation engine owns outcomes. UI, charts, persistence, and experiments can read state or issue explicit commands, but none may select a target, choose a mate, mutate a gene, or decide a death.

## Dependency direction

```text
configuration
    ↓
genome + entities + math + spatial index
    ↓
environment + simulation engine + snapshots
    ↓                  ↓
analytics          persistence/export
    ↓                  ↓
experiments/CLI      Pygame UI
                       ↓
                    Godot 4 3D client
```

`simulation.engine` imports analytics only to attach its observational recorder. Analytics accepts engine-like state but does not call `step` or write organism fields.

## Key interfaces

- `SimulationConfig.from_json/from_dict/to_dict`: validated configuration boundary.
- `Genome`: immutable ordered six-gene value object.
- `SimulationEngine.step(count)`: only state-advance entry point.
- `SimulationEngine.snapshot()`: immutable presentation boundary.
- `EnvironmentState.schedule(event)`: tick-addressed pressure command.
- `MetricsRecorder.record(engine)`: observational sample.
- `save_checkpoint/load_checkpoint`: exact continuation boundary.
- `export_experiment`: portable evidence package.
- `ExperimentSpec`: reusable scenario plus nested overrides.
- `EvolutionApp`: user event loop; delegates steps to `SimulationController`.
- `GodotSimulationServer`: owns the same `SimulationEngine`, advances it at a bounded real-time rate, and exposes local `/state` plus validated `/command` operations to `godot/`.
- `godot/scripts/Main.gd`: presentation, selection, camera, controls, and 3D scene; it never calculates survival, combat, inheritance, or cultural outcomes.

## Deterministic spatial search

The uniform grid maps IDs to cells and retains positions for exact radius filtering. Queries always return sorted IDs. Food uses a cell width of half maximum perception (minimum 24 units), which avoids scanning thousands of empty micro-cells while preserving exact distance results. The index is built once per tick and shared by movement and consumption.

Fights and belief transmission use a separate creature-position hash. The bridge binds to `127.0.0.1`, caps request sizes, validates every command, and accepts no remote host configuration. Godot polls immutable JSON presentation data; commands are applied by the Python engine between locked ticks.

## Persistence transaction

1. Build a complete versioned payload.
2. Reject every non-finite value.
3. Write sorted JSON to a temporary sibling.
4. Flush and `fsync`.
5. Replace the destination atomically.

Loading constructs and audits a candidate engine before returning it. Callers replace their current engine only after success.

## Extension points

- New gene: extend the stable `Trait` enum, config bounds, phenotype mapping, tests, and migration version together.
- New environment event: add validation, deterministic tick semantics, export representation, and tests.
- New metric: add one `MetricSample` field and flatten it in `to_row`.
- New renderer: consume `WorldSnapshot`; never import engine-private behavior.
- Neural behavior: introduce a brain interface that receives sensors and returns steering, keeping energy/genetics in the existing engine.
- Multiple resources or predators: use separate entity types and spatial indexes; define deterministic contention ordering.

## Performance and profiling

The main cost is neighborhood search. A regression test requires 100 default founders to advance 120 ticks within five seconds on the development device. A second slow test runs 100,000 ticks with invariant checks every 1,000 ticks.

```powershell
.\.venv\Scripts\python.exe -m cProfile -o profile.pstats main.py stress --config config/default.json --ticks 10000
```

Optimize without changing stable ordering, RNG call order, or tick semantics unless a checkpoint/version migration explicitly permits it.

