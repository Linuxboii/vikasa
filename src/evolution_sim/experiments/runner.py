"""Run single, replicated, and stress experiments."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.experiments.charts import export_charts
from evolution_sim.experiments.contrast import ContrastProtocol as ContrastProtocol
from evolution_sim.experiments.contrast import paired_effect_statistics as paired_effect_statistics
from evolution_sim.experiments.contrast import run_contrast as run_contrast
from evolution_sim.experiments.scenarios import ScenarioError, deep_merge, load_json
from evolution_sim.io.export import ExportManifest, export_experiment
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


def _source_digest() -> str:
    source_root = Path(__file__).resolve().parents[1]
    source_hash = hashlib.sha256()
    for file in sorted(source_root.rglob("*.py")):
        source_hash.update(file.relative_to(source_root).as_posix().encode("utf-8"))
        source_hash.update(file.read_text(encoding="utf-8").encode("utf-8"))
    return source_hash.hexdigest()


def run_development_study(
    config: SimulationConfig, *, seeds: list[int], ticks: int, sample_interval: int = 500
) -> dict[str, Any]:
    """Replicate long-run renewal without rescue and report binomial uncertainty.

    This is an exploratory simulation protocol, not empirical validation. Each
    replicate gets a fresh RNG; all seeds, failures and extinction times survive
    into the report. Observer sampling never drives reproductive outcomes.
    """
    if (not seeds or any(isinstance(seed, bool) or not isinstance(seed, int)
                         or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError("seeds must be unique non-negative integers")
    if (isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1
            or isinstance(sample_interval, bool) or not isinstance(sample_interval, int)
            or sample_interval < 1):
        raise ValueError("ticks and sample_interval must be positive integers")
    source_digest = _source_digest()
    replicates = []
    for seed in seeds:
        engine = SimulationEngine(config, seed)
        trajectory = [engine.metrics.record(engine).to_row()]
        invariant_errors: list[str] = []
        while engine.tick < ticks and not engine.extinct:
            engine.step()
            if engine.tick % sample_interval == 0 or engine.extinct or engine.tick == ticks:
                trajectory.append(engine.metrics.record(engine).to_row())
                invariant_errors.extend(engine.audit_invariants())
        replicates.append({
            "seed": seed, "ticks_completed": engine.tick,
            "extinction_tick": engine.tick if engine.extinct else None,
            "final_population": len(engine.creatures), "total_births": engine.total_births,
            "total_deaths": engine.total_deaths, "death_causes": dict(engine.death_causes),
            "max_living_generation": trajectory[-1]["max_generation"],
            "max_recorded_generation": max((engine.lineage.generation_of(cid)
                                            for cid in range(engine.next_creature_id)), default=0),
            "invariant_errors": sorted(set(invariant_errors)), "trajectory": trajectory,
        })
    count = len(replicates)
    survivors = sum(row["extinction_tick"] is None for row in replicates)
    fraction = survivors / count
    z = 1.959963984540054
    denominator = 1 + z*z / count
    center = (fraction + z*z / (2*count)) / denominator
    radius = z * math.sqrt(fraction*(1-fraction)/count + z*z/(4*count*count)) / denominator
    config_json = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":"))
    if _source_digest() != source_digest:
        raise ValueError("Study source changed during execution; rerun with a stable source tree")
    return {
        "schema": "vikasa-development-study-v1",
        "protocol": {"seeds": list(seeds), "ticks": ticks, "sample_interval": sample_interval,
                     "rescue": False, "mortality_mode": config.demography.mode},
        "provenance": {"config": config.to_dict(),
                       "config_sha256": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
                       "source_sha256": source_digest,
                       "python": platform.python_version(), "numpy": np.__version__},
        "aggregate": {"replicates": count, "survivors": survivors,
                      "survival_fraction": fraction,
                      "survival_wilson_95": [max(0.0, center-radius), min(1.0, center+radius)],
                      "invariant_failure_replicates": sum(bool(row["invariant_errors"])
                                                          for row in replicates)},
        "caveat": "Exploratory seeded simulations, not species validation. Wilson intervals "
                  "assume independent Bernoulli seed outcomes; selected seeds may be biased.",
        "replicates": replicates,
    }


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
