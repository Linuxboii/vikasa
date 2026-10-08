"""Predeclared seed-blocked model comparisons and transparent uncertainty."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.experiments.scenarios import deep_merge, load_json
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent

BAND_METRICS = ("population", "max_generation", "plant_energy", "mean_water", "mean_energy_ratio")


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ValueError(f"{name} must be nonempty text of at most 1000 characters")
    return value


def _object(value: Any, required: set[str], optional: set[str], name: str) -> dict:
    if not isinstance(value, dict) or required - value.keys() or value.keys() - required - optional:
        raise ValueError(f"{name} has missing or unsupported fields")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ContrastArm:
    id: str
    label: str
    config: SimulationConfig
    events: tuple[EnvironmentEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "config": self.config.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class ContrastProtocol:
    name: str
    description: str
    control: str
    seeds: tuple[int, ...]
    ticks: int
    sample_interval: int
    bootstrap_seed: int
    bootstrap_samples: int
    arms: tuple[ContrastArm, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any], base: SimulationConfig) -> ContrastProtocol:
        _object(
            data,
            {
                "name",
                "description",
                "control",
                "seeds",
                "ticks",
                "sample_interval",
                "bootstrap_seed",
                "bootstrap_samples",
                "arms",
            },
            set(),
            "protocol",
        )
        name = _text(data["name"], "name")
        description = _text(data["description"], "description")
        ticks = _integer(data["ticks"], "ticks", 1, 1_000_000)
        interval = _integer(data["sample_interval"], "sample_interval", 1, ticks)
        bootstrap_seed = _integer(data["bootstrap_seed"], "bootstrap_seed", 0, 2**63 - 1)
        samples = _integer(data["bootstrap_samples"], "bootstrap_samples", 100, 50_000)
        seeds = data["seeds"]
        if not isinstance(seeds, list) or not 1 <= len(seeds) <= 128:
            raise ValueError("seeds must be a list of 1 to 128 unique integers")
        seeds = tuple(_integer(seed, "seed", 0, 2**63 - 1) for seed in seeds)
        if len(set(seeds)) != len(seeds):
            raise ValueError("seed blocks must be unique")
        if not isinstance(data["arms"], list) or not 2 <= len(data["arms"]) <= 8:
            raise ValueError("arms must contain 2 to 8 configurations")
        arms = []
        for item in data["arms"]:
            _object(item, {"id", "label", "overrides", "events"}, set(), "arm")
            aid = _text(item["id"], "arm.id")
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", aid):
                raise ValueError("arm.id must be a short lowercase identifier")
            if not isinstance(item["overrides"], dict) or not isinstance(item["events"], list):
                raise ValueError("arm overrides must be an object and events a list")
            if len(item["events"]) > 64:
                raise ValueError("each arm supports at most 64 events")
            config = SimulationConfig.from_dict(deep_merge(base.to_dict(), item["overrides"]))
            events = []
            for event in item["events"]:
                _object(event, {"kind", "start_tick", "duration", "intensity"}, {"label"}, "event")
                start = _integer(event["start_tick"], "start_tick", 0, ticks - 1)
                duration = _integer(event["duration"], "duration", 1, ticks - start)
                intensity = event["intensity"]
                if (
                    isinstance(intensity, bool)
                    or not isinstance(intensity, (int, float))
                    or not math.isfinite(intensity)
                    or not 0 < intensity <= 100
                ):
                    raise ValueError("event intensity must be finite in (0, 100]")
                if not isinstance(event.get("label", ""), str):
                    raise ValueError("event.label must be text")
                if not isinstance(event["kind"], str):
                    raise ValueError("event.kind must be text")
                events.append(
                    EnvironmentEvent(
                        event["kind"], start, duration, float(intensity), event.get("label", "")
                    )
                )
            arms.append(ContrastArm(aid, _text(item["label"], "arm.label"), config, tuple(events)))
        ids = [arm.id for arm in arms]
        if len(set(ids)) != len(ids):
            raise ValueError("arm identifiers must be unique")
        control = _text(data["control"], "control")
        if control not in ids:
            raise ValueError("control must identify an existing arm")
        protocol = cls(
            name, description, control, seeds, ticks, interval, bootstrap_seed, samples, tuple(arms)
        )
        if len(protocol.sample_ticks()) * len(arms) * len(seeds) > 250_000:
            raise ValueError("protocol exceeds the 250000 stored trajectory records limit")
        return protocol

    @classmethod
    def from_json(cls, path: str | Path) -> ContrastProtocol:
        source = Path(path).resolve()
        data = load_json(source)
        config_path = data.pop("config", None)
        if not isinstance(config_path, str) or not config_path:
            raise ValueError("protocol.config must specify a configuration path")
        config = SimulationConfig.from_json(source.parent / config_path)
        return cls.from_dict(data, config)

    def sample_ticks(self) -> tuple[int, ...]:
        ticks = {0, self.ticks, *range(self.sample_interval, self.ticks, self.sample_interval)}
        for arm in self.arms:
            for event in arm.events:
                ticks.update((event.start_tick, event.end_tick))
        return tuple(sorted(ticks))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "control": self.control,
            "seeds": list(self.seeds),
            "ticks": self.ticks,
            "sample_interval": self.sample_interval,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_samples": self.bootstrap_samples,
            "arms": [arm.to_dict() for arm in self.arms],
            "rescue": False,
            "population_integral": "sum of post-transition populations at ticks 1..T",
        }


def paired_effect_statistics(
    treatment: list[float | None],
    control: list[float | None],
    *,
    bootstrap_seed: int,
    bootstrap_samples: int,
) -> dict[str, Any]:
    """Resample entire seed pairs, never individual trajectory observations."""
    if not treatment or len(treatment) != len(control) or len(treatment) > 128:
        raise ValueError("effects require 1 to 128 aligned seed pairs")
    _integer(bootstrap_seed, "bootstrap_seed", 0, 2**63 - 1)
    _integer(bootstrap_samples, "bootstrap_samples", 100, 50_000)
    for value in (*treatment, *control):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("effect values must be finite numbers or unavailable")
    differences = [
        None if a is None or b is None else a - b for a, b in zip(treatment, control, strict=True)
    ]
    n = len(differences)
    available = sum(value is not None for value in differences)
    result = {
        "pairs": n,
        "available_pairs": available,
        "differences": differences,
        "mean_difference": None,
        "sample_variance": None,
        "standard_error": None,
        "bootstrap_percentile_95": None,
    }
    if available != n:
        return result  # No complete-case exclusion disguised as a full experiment.
    values = np.asarray(differences, dtype=float)
    result["mean_difference"] = float(values.mean())
    if n == 1:
        return result
    variance = float(values.var(ddof=1))
    result["sample_variance"] = variance
    result["standard_error"] = math.sqrt(variance / n)
    rng = np.random.default_rng(bootstrap_seed)  # Never the simulation RNG.
    means = np.empty(bootstrap_samples)
    for start in range(0, bootstrap_samples, 256):
        end = min(bootstrap_samples, start + 256)
        indices = rng.integers(0, n, size=(end - start, n))
        means[start:end] = values[indices].mean(axis=1)
    result["bootstrap_percentile_95"] = np.quantile(means, [0.025, 0.975]).tolist()
    return result


def _bands(rows: list[dict], ticks: tuple[int, ...]) -> list[dict]:
    result = []
    for index, tick in enumerate(ticks):
        point = {"tick": tick}
        for metric in BAND_METRICS:
            values = [
                row["trajectory"][index][metric] if row["status"] == "completed" else None
                for row in rows
            ]
            if any(value is None for value in values):
                point[metric] = None
            else:
                point[metric] = {
                    "mean": float(np.mean(values)),
                    "q25": float(np.quantile(values, 0.25)),
                    "q75": float(np.quantile(values, 0.75)),
                    "replicates": len(values),
                }
        result.append(point)
    return result


def _observation(engine: SimulationEngine, errors: list[str]) -> dict[str, Any]:
    row = engine.metrics.record(engine).to_row()
    for field, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            row[field] = None
            errors.append(f"Non-finite observation at tick {engine.tick}: {field}")
    return row


def _run_replicate(
    protocol: ContrastProtocol, arm: ContrastArm, seed: int, ticks: tuple[int, ...]
) -> dict[str, Any]:
    names = (
        "final_population",
        "mean_population",
        "population_tick_sum",
        "total_births",
        "total_deaths",
        "max_living_generation",
        "max_recorded_generation",
        "survived",
        "plant_energy",
        "mean_water",
    )
    engine = None
    observed = {}
    errors = []
    execution_error = None
    extinction_tick = None
    population_sum = 0
    stage = "initialization"
    outcomes = dict.fromkeys(names)
    try:
        engine = SimulationEngine(arm.config, seed)
        stage = "scheduling"
        for event in arm.events:
            engine.environment.schedule(event)
        stage = "measurement"
        observed[0] = _observation(engine, errors)
        del engine.metrics.samples[:-1]
        stage = "audit"
        errors.extend(engine.audit_invariants())
        tick_set = set(ticks)
        while engine.tick < protocol.ticks:
            stage = "step"
            engine.step()
            population_sum += len(engine.creatures)
            if engine.extinct and extinction_tick is None:
                extinction_tick = engine.tick
            if engine.tick in tick_set:
                stage = "measurement"
                observed[engine.tick] = _observation(engine, errors)
                stage = "audit"
                errors.extend(engine.audit_invariants())
            # The package owns its sampled history; engine observation must not grow
            # with every automatic sample during million-tick protocols.
            del engine.metrics.samples[:-1]
        stage = "outcomes"
        final = observed[protocol.ticks]
        outcomes = {
            "final_population": len(engine.creatures),
            "mean_population": population_sum / protocol.ticks,
            "population_tick_sum": population_sum,
            "total_births": engine.total_births,
            "total_deaths": engine.total_deaths,
            "max_living_generation": final["max_generation"],
            "max_recorded_generation": max(
                (engine.lineage.generation_of(cid) for cid in range(engine.next_creature_id)),
                default=0,
            ),
            "survived": int(extinction_tick is None),
            "plant_energy": final["plant_energy"],
            "mean_water": final["mean_water"],
        }
    except Exception as exc:
        # Model failures are evidence, not permission to discard a seed block.
        # KeyboardInterrupt/SystemExit still abort normally; source-change guards
        # below reject an incoherent report rather than certifying partial code.
        execution_error = {
            "stage": stage,
            "tick": engine.tick if engine is not None else 0,
            "type": type(exc).__name__,
            "message": str(exc),
        }
    status = "failed" if execution_error or errors else "completed"
    if status == "failed":
        outcomes = dict.fromkeys(names)
    trajectory = [
        observed.get(tick, {"tick": tick, **dict.fromkeys(BAND_METRICS)}) for tick in ticks
    ]
    return {
        "seed": seed,
        "arm": arm.id,
        "status": status,
        "ticks_completed": engine.tick if engine is not None else 0,
        "extinction_tick": extinction_tick,
        "outcomes": outcomes,
        "death_causes": dict(engine.death_causes) if engine is not None else {},
        "invariant_errors": sorted(set(errors)),
        "execution_error": execution_error,
        "trajectory": trajectory,
    }


def run_contrast(
    protocol: ContrastProtocol, *, progress: Callable[[dict[str, Any]], None] | None = None
) -> dict[str, Any]:
    """Fixed-horizon trajectories; extinction is absorbing, not a dropped replicate."""
    from evolution_sim.experiments import runner

    source_digest = runner._source_digest()
    definition = protocol.to_dict()
    protocol_digest = _digest(definition)
    ticks = protocol.sample_ticks()
    replicates = []
    for seed in protocol.seeds:
        for arm in protocol.arms:
            row = _run_replicate(protocol, arm, seed, ticks)
            replicates.append(row)
            if progress is not None:
                progress(
                    {
                        "completed_runs": len(replicates),
                        "total_runs": len(protocol.seeds) * len(protocol.arms),
                        "seed": seed,
                        "arm": arm.id,
                        "status": row["status"],
                    }
                )
    by_arm = {arm.id: [row for row in replicates if row["arm"] == arm.id] for arm in protocol.arms}
    contrasts = []
    for arm in protocol.arms:
        if arm.id == protocol.control:
            continue
        effects = {}
        for metric in by_arm[arm.id][0]["outcomes"]:
            effects[metric] = paired_effect_statistics(
                [row["outcomes"][metric] for row in by_arm[arm.id]],
                [row["outcomes"][metric] for row in by_arm[protocol.control]],
                bootstrap_seed=protocol.bootstrap_seed,
                bootstrap_samples=protocol.bootstrap_samples,
            )
        contrasts.append({"arm": arm.id, "control": protocol.control, "effects": effects})
    if runner._source_digest() != source_digest or _digest(protocol.to_dict()) != protocol_digest:
        raise ValueError("Experiment source or protocol changed during execution; rerun")
    return {
        "schema": "vikasa-seed-blocked-contrast-v1",
        "protocol": definition,
        "provenance": {
            "source_sha256": source_digest,
            "protocol_sha256": protocol_digest,
            "arm_config_sha256": {arm.id: _digest(arm.config.to_dict()) for arm in protocol.arms},
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "replicates": replicates,
        "contrasts": contrasts,
        "trajectory_bands": {aid: _bands(rows, ticks) for aid, rows in by_arm.items()},
        "invariant_failure_replicates": sum(bool(row["invariant_errors"]) for row in replicates),
        "execution_failure_replicates": sum(
            row["execution_error"] is not None for row in replicates
        ),
        "caveats": [
            "Model counterfactuals, not species validation or proof of adaptation.",
            "Seed blocks are replicates; trajectory time points are not independent replicates.",
            "Same seed labels do not guarantee common random draws after branches diverge.",
            "Selected seeds can bias inference. Small-sample intervals are exploratory.",
            "Intervals are marginal and unadjusted for multiple metrics or arm comparisons.",
            "Trajectory ribbons show between-seed interquartile spread, not confidence intervals.",
            "Unavailable metrics invalidate the entire metric contrast; no seed pairs are dropped.",
        ],
    }
