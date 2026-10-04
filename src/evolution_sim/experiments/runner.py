"""Run single, replicated, and stress experiments."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from evolution_sim.config import SimulationConfig
from evolution_sim.experiments.charts import export_charts
from evolution_sim.experiments.scenarios import ScenarioError, deep_merge, load_json
from evolution_sim.io.export import ExportManifest, export_experiment
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    name: str
    description: str
    config_path: Path
    seed: int
    ticks: int
    overrides: dict[str, Any]
    events: tuple[EnvironmentEvent, ...]

    @classmethod
    def from_json(cls, path: str | Path) -> ExperimentSpec:
        source = Path(path).resolve()
        data = load_json(source)
        required = {"name", "description", "config", "seed", "ticks", "overrides", "events"}
        missing = sorted(required - set(data))
        if missing:
            raise ScenarioError(f"Scenario is missing {missing[0]}")
        config_path = Path(data["config"])
        if not config_path.is_absolute():
            config_path = (source.parent / config_path).resolve()
        ticks = int(data["ticks"])
        if ticks < 0:
            raise ScenarioError("ticks must be non-negative")
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            config_path=config_path,
            seed=int(data["seed"]),
            ticks=ticks,
            overrides=dict(data["overrides"]),
            events=tuple(EnvironmentEvent.from_dict(item) for item in data["events"]),
        )

    def with_runtime(self, *, ticks: int | None = None, seed: int | None = None) -> ExperimentSpec:
        return replace(
            self,
            ticks=self.ticks if ticks is None else ticks,
            seed=self.seed if seed is None else seed,
        )

    def load_config(self) -> SimulationConfig:
        base = json.loads(self.config_path.read_text(encoding="utf-8"))
        return SimulationConfig.from_dict(deep_merge(base, self.overrides))


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    spec: ExperimentSpec
    engine: SimulationEngine
    manifest: ExportManifest
    charts: tuple[Path, ...]
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class StressReport:
    ticks_completed: int
    elapsed_seconds: float
    final_population: int
    invariant_errors: list[str]


def run_experiment(spec: ExperimentSpec, output_dir: str | Path) -> ExperimentResult:
    engine = SimulationEngine(spec.load_config(), seed=spec.seed)
    for event in spec.events:
        engine.environment.schedule(event)
    started = time.perf_counter()
    engine.step(spec.ticks)
    elapsed = time.perf_counter() - started
    errors = engine.audit_invariants()
    if errors:
        raise RuntimeError("Experiment invariant failure: " + "; ".join(errors))
    manifest = export_experiment(engine, output_dir)
    charts = export_charts(engine, manifest.root)
    return ExperimentResult(spec, engine, manifest, charts, elapsed)


def run_batch(
    spec: ExperimentSpec,
    *,
    output_dir: str | Path,
    replicates: int,
) -> list[ExperimentResult]:
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    root = Path(output_dir)
    results = []
    for index in range(replicates):
        replicate = index + 1
        current = spec.with_runtime(seed=spec.seed + index)
        directory = root / f"replicate-{replicate:03d}-seed-{current.seed}"
        results.append(run_experiment(current, directory))
    return results


def run_stress(
    config: SimulationConfig,
    *,
    seed: int,
    ticks: int,
    audit_interval: int = 1_000,
) -> StressReport:
    if ticks < 0 or audit_interval <= 0:
        raise ValueError("ticks must be non-negative and audit_interval positive")
    engine = SimulationEngine(config, seed=seed)
    errors: list[str] = []
    started = time.perf_counter()
    remaining = ticks
    while remaining:
        chunk = min(audit_interval, remaining)
        engine.step(chunk)
        errors.extend(engine.audit_invariants())
        if errors:
            break
        remaining -= chunk
    elapsed = time.perf_counter() - started
    return StressReport(engine.tick, elapsed, len(engine.creatures), errors)
