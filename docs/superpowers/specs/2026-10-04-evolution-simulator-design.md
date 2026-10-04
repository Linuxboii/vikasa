# Evolution Simulator Design

## Intent

Build a demonstration-ready artificial-life laboratory where evolution is visible, measurable, reproducible, and explorable. The application must run as a polished desktop simulation and as a faster-than-real-time headless experiment engine. A viewer should be able to begin with 100 genetically varied creatures, apply environmental pressure, watch traits shift, inspect ancestry, save the state, and export evidence without editing code.

The source PRD is authoritative for product requirements. Where it leaves implementation choices open, this design favors scientific reproducibility, clear causal relationships, laptop performance, and a cohesive presentation over speculative features.

## Product Decisions

- Use a continuous, collision-bounded 2D world. Collision boundaries make habitat edges visible and avoid teleportation artifacts.
- Keep the six required genes: size, max speed, perception radius, metabolic efficiency, reproduction threshold, and fertility investment.
- Use asexual two-parent pairing between eligible nearby creatures. This gives crossover a biological role without adding mate-choice complexity.
- Natural survival and reproduction drive selection. A computed fitness score is analytical only and never directly chooses survivors.
- Use NumPy's `Generator(PCG64)` as the single simulation randomness source. Every stochastic operation receives that generator.
- Use a uniform spatial hash for nearby-food and nearby-mate queries. This keeps the engine responsive as populations grow.
- Use custom lightweight charts inside Pygame and Matplotlib for publication-quality exports.
- Use versioned JSON checkpoints containing configuration, entities, lineage, metrics, scheduled events, counters, and RNG state.
- Preserve the PRD's non-goals: no neural networks, predators, multiplayer, photorealistic art, or molecular biology.

## Experience Design

The visual direction is a modern scientific observatory rather than a game HUD: deep navy surfaces, cool cyan data accents, warm amber environmental alerts, crisp typography, restrained motion, and luminous organisms whose form encodes their genomes.

The main window contains:

1. A dominant world viewport with resources, organisms, optional perception rings, movement trails, habitat zones, and environmental-event overlays.
2. A compact top status rail for seed, tick, population, food, births, deaths, generation proxy, simulation rate, and recording state.
3. A right laboratory panel with tabs for Controls, Inspector, Traits, Lineage, and Events.
4. A bottom analytics strip with selectable live charts for population, births/deaths, and mean traits.
5. A start/setup overlay for preset, seed, population, boundary, mutation, and food settings.

Mouse interaction selects organisms and panel controls. Keyboard shortcuts cover pause (`Space`), simulation speed (`1`-`5`), restart (`R`), save (`Ctrl+S`), load (`Ctrl+O`), chart export (`E`), overlays (`P`, `T`, `Z`), and help (`?`). UI actions only manipulate engine commands or presentation state; they never alter simulation equations.

## Architecture

The project uses a `src` package layout with strict dependency direction:

```text
config -> domain/genetics -> world/environment -> engine
                                      engine -> analytics/storage
                                      engine -> UI (read-only snapshots + commands)
                                      engine -> CLI/experiments
```

### Configuration

`SimulationConfig` is a tree of frozen dataclasses loaded from JSON. Validation rejects invalid dimensions, gene bounds, negative rates, impossible age/energy settings, and unsupported checkpoint versions. Presets are ordinary JSON files so experiments are inspectable and reusable.

### Genetics and Phenotype

`Genome` stores six floats in stable trait order. It validates and clamps values through `GeneSpec` bounds. Uniform and arithmetic crossover are supported. Mutation independently applies a Gaussian perturbation per gene with configurable probability and sigma, then clamps.

Visual phenotype maps size to rendered radius, speed to a cyan-magenta hue axis, metabolic efficiency to brightness, and fertility investment to a subtle outer arc. These mappings are presentation-only; the engine uses physical trait values.

### Creatures and Resources

`Creature` stores identity, position, velocity, age, energy, genome, parents, offspring count, food acquired, birth tick, and alive state. Movement chooses the nearest sensed food or a slowly changing wander heading. Steering is acceleration-limited so motion reads as intentional rather than jittery.

`Resource` stores identity, position, energy value, and radius. Food consumption is resolved deterministically by distance then creature ID to avoid collection-order effects.

### Energy and Reproduction

Each tick applies basal cost scaled by size and inverse metabolic efficiency, plus movement cost scaled by distance, size, and normalized speed. Eating adds configured energy up to a generous cap. Death occurs at zero energy or after maximum age.

Eligible creatures must satisfy minimum age, energy threshold, cooldown, and nearby-mate requirements. Parents contribute energy based on fertility investment. One offspring is created between the parents using configured crossover and mutation. It is placed near the midpoint, records both parents, starts with inherited energy, and cannot reproduce immediately. Population caps and minimum energy contributions prevent runaway allocation.

### Environment

Food spawns through a deterministic accumulator so fractional rates are stable across tick sizes. Optional rectangular habitat zones multiply spawn density. Scheduled and interactive events include drought, abundance, heat penalty, and resource redistribution. Events have explicit start/end ticks and appear in the timeline and export.

### Engine

`SimulationEngine.step()` owns the PRD tick order: events, spawn, sense/behavior, movement, costs, consumption, reproduction, death, metrics. It produces immutable `WorldSnapshot` data for the UI. The same step method powers interactive and headless modes.

Commands (`pause`, `set_speed`, `schedule_event`, `restart`) are applied at tick boundaries. No wall-clock data enters simulation state. Stable ordering by entity ID plus the single RNG ensures repeatability.

### Analytics and Lineage

`MetricsRecorder` samples population, food, births, deaths, diversity, fitness summary, and mean/median/variance/standard deviation for all six traits. It calculates correlations between traits and reproductive success when sample size permits. `LineageStore` records parent/child links and provides ancestors, descendants, and a compact lineage neighborhood for the inspector.

### Persistence and Export

Checkpoints are human-readable, versioned JSON written atomically through a temporary sibling file. Loading performs schema and invariant validation before replacing live state. Experiment export produces:

- `config.json` with effective configuration and seed;
- `metrics.csv` with time-series observations;
- `creatures.csv` with final organism records;
- `lineage.csv` with parent-child edges;
- `events.json` with environmental history;
- `summary.json` with outcome and reproducibility metadata;
- PNG charts for population, traits, births/deaths, and final distributions.

### Experiments

The experiment runner accepts preset/config paths, seeds, ticks, replicates, and output directory. Built-in scenarios cover baseline, scarcity, mutation comparison, and environmental shift. The showcase preset compresses the scientific story into a 3-5 minute accelerated demonstration.

## Error Handling

- Configuration errors list the exact dotted field and rejected value.
- Extinction is a terminal simulation state with a visible message and valid export, not an exception.
- Population-cap pressure skips reproduction and records a diagnostic counter.
- Corrupt or incompatible checkpoints leave the current session untouched.
- Export failures show the target path and preserve simulation state.
- Rendering failures cannot mutate the engine; headless mode remains usable.

## Performance

- The engine targets at least 100 organisms at a smooth 60 FPS on a normal laptop.
- Rendering may interpolate or skip frames while fixed simulation ticks remain deterministic.
- Spatial hashing limits neighborhood search work.
- Metrics sampling frequency is configurable and pairwise diversity uses a deterministic bounded sample above a threshold.
- A required headless stress path runs 100,000 ticks and validates finite values, ID uniqueness, and lineage consistency.

## Accessibility and Usability

- Never rely on color alone: selected state, events, and trait encodings also use shape, text, or line style.
- Maintain high contrast and minimum 14 px body text at the reference resolution.
- Every action has a keyboard shortcut and visible label.
- Tooltips and an in-app help overlay explain controls and trait encodings.
- UI supports resizable windows down to 1100 x 700 and scales panel geometry.

## Test Strategy

- Unit tests: configuration, genome bounds, crossover, mutation, movement math, energy equations, spatial queries, lineage, analytics, serialization.
- Simulation tests: lifecycle, resource competition, reproduction, death ordering, extinction, environmental events, population cap, deterministic replay.
- Persistence tests: checkpoint round-trip and invalid-checkpoint rollback.
- Export tests: artifact presence and equality between CSV values and recorder state.
- UI/controller tests: pause and speed controls change scheduling only, never rules.
- Property-style seeded tests: random genomes remain bounded and all dynamic numeric state remains finite.
- Stress test: 100,000 headless ticks, tagged `slow`, with invariant audits.
- Visual validation: screenshots at reference and minimum window sizes plus interaction smoke testing.

## Acceptance Evidence

Completion requires fresh evidence for all of the following:

- Full pytest suite passes, including deterministic checkpoint/export coverage.
- Slow 100,000-tick stress run completes without state corruption.
- Ruff lint and formatting checks pass.
- Application starts in headless SDL mode and advances scripted UI frames without errors.
- Four example scenarios run and export CSV/JSON/PNG artifacts.
- Same seed/config/ticks produce byte-equivalent canonical summaries.
- Screenshots show the start screen, running laboratory, inspector, and environmental shift state without clipping.
- README explains installation, equations, architecture, controls, experiments, exports, tests, and troubleshooting.

## Assumptions

- The target is Windows first, with portable Python code for macOS/Linux.
- Local desktop operation is sufficient; no network service is needed.
- GitHub publication and a remote v1.0 tag cannot be completed without repository credentials, so the local repository will be release-ready and locally tagged only if identity is configured.
- Pygame-ce is used as the maintained drop-in Pygame implementation while preserving the PRD's Pygame API choice.
