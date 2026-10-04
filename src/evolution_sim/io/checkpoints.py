"""Atomic, versioned JSON checkpoints with strict validation."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.analytics.metrics import MetricSample, MetricsRecorder
from evolution_sim.config import ConfigError, SimulationConfig
from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genome import Genome
from evolution_sim.model.lineage import LineageStore
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentState

FORMAT = "vikasa"
VERSION = 1


class CheckpointError(ValueError):
    """Raised when a checkpoint is unreadable, incompatible, or unsafe."""


def _reject_constant(value: str) -> None:
    raise CheckpointError(f"Non-finite JSON constant is not allowed: {value}")


def _validate_finite(value: Any, path: str = "root") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CheckpointError(f"{path} contains a non-finite value")
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_finite(item, f"{path}[{index}]")


def _creature_to_dict(creature: Creature) -> dict[str, Any]:
    return {
        "id": creature.id,
        "position": creature.position.tolist(),
        "velocity": creature.velocity.tolist(),
        "age": creature.age,
        "energy": creature.energy,
        "genome": list(creature.genome.values),
        "parents": list(creature.parents) if creature.parents else None,
        "offspring_count": creature.offspring_count,
        "food_acquired": creature.food_acquired,
        "birth_tick": creature.birth_tick,
        "last_reproduction_tick": creature.last_reproduction_tick,
        "wander_angle": creature.wander_angle,
        "alive": creature.alive,
        "trail": [list(point) for point in creature.trail],
    }


def _resource_to_dict(resource: Resource) -> dict[str, Any]:
    return {
        "id": resource.id,
        "position": resource.position.tolist(),
        "energy": resource.energy,
        "radius": resource.radius,
    }


def checkpoint_payload(engine: SimulationEngine) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "config": engine.config.to_dict(),
        "seed": engine.seed,
        "tick": engine.tick,
        "rng_state": engine.rng.bit_generator.state,
        "creatures": [_creature_to_dict(engine.creatures[key]) for key in sorted(engine.creatures)],
        "resources": [_resource_to_dict(engine.resources[key]) for key in sorted(engine.resources)],
        "lineage": engine.lineage.to_records(),
        "environment": engine.environment.to_dict(),
        "metrics": [asdict(sample) for sample in engine.metrics.samples],
        "next_creature_id": engine.next_creature_id,
        "next_resource_id": engine.next_resource_id,
        "spawn_accumulator": engine.spawn_accumulator,
        "tick_births": engine.tick_births,
        "tick_deaths": engine.tick_deaths,
        "total_births": engine.total_births,
        "total_deaths": engine.total_deaths,
        "reproduction_skipped_at_cap": engine.reproduction_skipped_at_cap,
    }


def save_checkpoint(engine: SimulationEngine, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    payload = checkpoint_payload(engine)
    _validate_finite(payload)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise CheckpointError(f"Could not save checkpoint {target}: {exc}") from exc
    return target


def _restore_creature(data: dict[str, Any]) -> Creature:
    parents = data.get("parents")
    creature = Creature(
        id=int(data["id"]),
        position=np.asarray(data["position"], dtype=float),
        velocity=np.asarray(data["velocity"], dtype=float),
        age=int(data["age"]),
        energy=float(data["energy"]),
        genome=Genome(tuple(float(item) for item in data["genome"])),  # type: ignore[arg-type]
        parents=(int(parents[0]), int(parents[1])) if parents else None,
        offspring_count=int(data["offspring_count"]),
        food_acquired=float(data["food_acquired"]),
        birth_tick=int(data["birth_tick"]),
        last_reproduction_tick=int(data["last_reproduction_tick"]),
        wander_angle=float(data["wander_angle"]),
        alive=bool(data["alive"]),
    )
    creature.trail = [(float(point[0]), float(point[1])) for point in data.get("trail", [])]
    return creature


def load_checkpoint(path: str | Path) -> SimulationEngine:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"), parse_constant=_reject_constant)
        if not isinstance(payload, dict):
            raise CheckpointError("Checkpoint root must be an object")
        _validate_finite(payload)
        if payload.get("format") != FORMAT:
            raise CheckpointError("Not a Vikasa checkpoint")
        if payload.get("version") != VERSION:
            raise CheckpointError(
                f"Unsupported checkpoint version {payload.get('version')}; expected {VERSION}"
            )
        config = SimulationConfig.from_dict(payload["config"])
        engine = SimulationEngine(config, seed=int(payload["seed"]))
        engine.tick = int(payload["tick"])
        engine.rng.bit_generator.state = payload["rng_state"]
        creatures = [_restore_creature(item) for item in payload["creatures"]]
        resources = [
            Resource(
                id=int(item["id"]),
                position=np.asarray(item["position"], dtype=float),
                energy=float(item["energy"]),
                radius=float(item["radius"]),
            )
            for item in payload["resources"]
        ]
        engine.creatures = {item.id: item for item in creatures}
        engine.resources = {item.id: item for item in resources}
        engine.lineage = LineageStore.from_records(payload["lineage"])
        engine.environment = EnvironmentState.from_dict(payload["environment"])
        engine.metrics = MetricsRecorder()
        engine.metrics.samples = [MetricSample(**item) for item in payload.get("metrics", [])]
        engine.next_creature_id = int(payload["next_creature_id"])
        engine.next_resource_id = int(payload["next_resource_id"])
        engine.spawn_accumulator = float(payload["spawn_accumulator"])
        engine.tick_births = int(payload["tick_births"])
        engine.tick_deaths = int(payload["tick_deaths"])
        engine.total_births = int(payload["total_births"])
        engine.total_deaths = int(payload["total_deaths"])
        engine.reproduction_skipped_at_cap = int(payload["reproduction_skipped_at_cap"])
        errors = engine.audit_invariants()
        if errors:
            raise CheckpointError("Checkpoint invariant failure: " + "; ".join(errors))
        return engine
    except CheckpointError:
        raise
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ConfigError) as exc:
        raise CheckpointError(f"Could not load checkpoint {source}: {exc}") from exc
