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
from evolution_sim.model.temperament import Temperament
from evolution_sim.simulation.behavior import ActionName, BehaviorState, InstinctVector
from evolution_sim.simulation.culture import CultureLedger
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentState, HabitatField

FORMAT = "vikasa"
VERSION = 3


class CheckpointError(ValueError):
    """Raised when a checkpoint is unreadable, incompatible, or unsafe."""


def _reject_constant(value: str) -> None:
    raise CheckpointError(f"Non-finite JSON constant is not allowed: {value}")


def _json_integer(value: Any, field: str) -> int:
    """Require an actual JSON integer instead of silently coercing IDs."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CheckpointError(f"{field} must be a JSON integer")
    return value


def _nullable_json_integer(value: Any, field: str) -> int | None:
    """Validate an optional identity reference without coercing JSON values."""
    if value is None:
        return None
    return _json_integer(value, field)


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
    behavior = creature.behavior_state
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
        "temperament": creature.temperament.to_dict(),
        "hunger": creature.hunger,
        "satisfaction_vector": list(creature.satisfaction_vector),
        "satisfaction": creature.satisfaction,
        "fights_won": creature.fights_won,
        "fights_lost": creature.fights_lost,
        "alpha": creature.alpha,
        "injury": creature.injury,
        "starvation_ticks": creature.starvation_ticks,
        "death_cause": creature.death_cause,
        "belief_id": creature.belief_id,
        "ritual_ticks": creature.ritual_ticks,
        "behavior_state": {
            "action": behavior.action.value,
            "started_tick": behavior.started_tick,
            "target_kind": behavior.target_kind,
            "target_id": behavior.target_id,
            "target_position": list(behavior.target_position) if behavior.target_position else None,
            "drives": list(behavior.drives.values),
            "utility_breakdown": {
                key.value: value for key, value in behavior.utility_breakdown.items()
            },
            "reason": behavior.reason,
        },
        "home_center": creature.home_center.tolist(),
        "home_radius": creature.home_radius,
        "home_migration_ticks": creature.home_migration_ticks,
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
        "culture": engine.culture.to_dict(),
        "death_causes": dict(engine.death_causes),
        "combat_events": list(engine.combat_events),
        "recent_events": list(engine.recent_events),
        "metrics": [asdict(sample) for sample in engine.metrics.samples],
        "birth_cohorts": engine.metrics.birth_cohorts,
        "habitat": engine.habitat.to_dict() if engine.habitat is not None else None,
        "external_food_energy": engine.external_food_energy,
        "interventions": engine.interventions,
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


def _restore_creature(data: dict[str, Any], *, strict_v3: bool = False) -> Creature:
    parents = data.get("parents")
    state = data.get("behavior_state", {})
    if strict_v3:
        if not isinstance(state, dict):
            raise CheckpointError("behavior_state must be an object")
        for field in ("action", "started_tick", "target_kind", "target_id",
                      "target_position", "drives", "utility_breakdown", "reason"):
            if field not in state:
                raise CheckpointError(f"Missing required v3 field behavior_state.{field}")
        for field in ("home_center", "home_radius", "home_migration_ticks"):
            if field not in data:
                raise CheckpointError(f"Missing required v3 field {field}")
    if parents is not None:
        if not isinstance(parents, list) or len(parents) != 2:
            raise CheckpointError("parents must be null or a pair of JSON integer IDs")
        parent_ids = (
            _json_integer(parents[0], "parent ID"),
            _json_integer(parents[1], "parent ID"),
        )
    else:
        parent_ids = None
    belief_id = _nullable_json_integer(data.get("belief_id"), "belief_id")
    target_id = _nullable_json_integer(state.get("target_id"), "behavior_state.target_id")
    creature = Creature(
        id=_json_integer(data["id"], "creature ID"),
        position=np.asarray(data["position"], dtype=float),
        velocity=np.asarray(data["velocity"], dtype=float),
        age=int(data["age"]),
        energy=float(data["energy"]),
        genome=Genome(tuple(float(item) for item in data["genome"])),  # type: ignore[arg-type]
        parents=parent_ids,
        offspring_count=int(data["offspring_count"]),
        food_acquired=float(data["food_acquired"]),
        birth_tick=int(data["birth_tick"]),
        last_reproduction_tick=int(data["last_reproduction_tick"]),
        wander_angle=float(data["wander_angle"]),
        alive=bool(data["alive"]),
        temperament=Temperament.from_dict(data.get("temperament")),
        hunger=float(data.get("hunger", 0.0)),
        satisfaction_vector=tuple(
            float(value) for value in data.get("satisfaction_vector", (0, 0, 0, 0))
        ),
        satisfaction=float(data.get("satisfaction", 0.0)),
        fights_won=int(data.get("fights_won", 0)),
        fights_lost=int(data.get("fights_lost", 0)),
        alpha=bool(data.get("alpha", False)),
        injury=float(data.get("injury", 0.0)),
        starvation_ticks=int(data.get("starvation_ticks", 0)),
        death_cause=data.get("death_cause"),
        belief_id=belief_id,
        ritual_ticks=int(data.get("ritual_ticks", 0)),
        behavior_state=BehaviorState(
            action=ActionName(state.get("action", "explore")),
            started_tick=(
                _json_integer(state["started_tick"], "behavior_state.started_tick")
                if strict_v3
                else int(state.get("started_tick", 0))
            ),
            target_kind=state.get("target_kind"),
            target_id=target_id,
            target_position=(
                tuple(float(v) for v in state["target_position"])
                if state.get("target_position") is not None
                else None
            ),
            drives=InstinctVector(tuple(state.get("drives", (0.0,) * 6))),
            utility_breakdown={
                ActionName(key): float(value)
                for key, value in state.get("utility_breakdown", {}).items()
            },
            reason=state.get("reason", "Exploring nearby"),
        ),
        home_center=np.asarray(
            data["home_center"] if strict_v3 else data.get("home_center", data["position"]),
            dtype=float,
        ),
        home_radius=float(data["home_radius"] if strict_v3 else data.get("home_radius", 24.0)),
        home_migration_ticks=(
            _json_integer(data["home_migration_ticks"], "home_migration_ticks")
            if strict_v3
            else int(data.get("home_migration_ticks", 0))
        ),
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
        version = payload.get("version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise CheckpointError("Checkpoint version must be a JSON integer")
        if version not in {1, 2, VERSION}:
            raise CheckpointError(
                f"Unsupported checkpoint version {version}; expected 1, 2, or {VERSION}"
            )
        if version in {1, 2}:
            payload = dict(payload)
            payload["version"] = VERSION
        if version == 1:
            payload.setdefault("culture", {})
            payload.setdefault("death_causes", {})
            payload.setdefault("combat_events", [])
            payload.setdefault("recent_events", [])
        config = SimulationConfig.from_dict(payload["config"])
        max_home_radius = min(config.world.width, config.world.height) / 2.0
        if max_home_radius <= 0:
            raise CheckpointError("World dimensions cannot support a positive home range")
        # Migrate legacy entities in-memory only. Current schemas are strict:
        # persisted home bounds are validated by the engine invariant audit.
        payload = dict(payload)
        if version in {1, 2}:
            migrated_creatures = []
            for raw in payload["creatures"]:
                item = dict(raw)
                position = item["position"]
                center = item.get("home_center", position)
                item["home_center"] = [
                    min(config.world.width, max(0.0, float(center[0]))),
                    min(config.world.height, max(0.0, float(center[1]))),
                ]
                if "home_radius" not in item:
                    migration_rng = np.random.default_rng(
                        np.random.SeedSequence([int(payload["seed"]), int(item["id"]), 3])
                    )
                    item["home_radius"] = float(migration_rng.uniform(18.0, 36.0))
                item["home_radius"] = min(
                    max_home_radius, max(1e-9, float(item["home_radius"]))
                )
                item.setdefault("home_migration_ticks", 0)
                item.setdefault("behavior_state", {})
                migrated_creatures.append(item)
            payload["creatures"] = migrated_creatures

        creature_ids = [_json_integer(item["id"], "creature ID") for item in payload["creatures"]]
        resource_ids = [_json_integer(item["id"], "resource ID") for item in payload["resources"]]
        next_creature_id = _json_integer(payload["next_creature_id"], "next_creature_id")
        next_resource_id = _json_integer(payload["next_resource_id"], "next_resource_id")
        all_ids = (*creature_ids, *resource_ids, next_creature_id, next_resource_id)
        if any(value < 0 for value in all_ids):
            raise CheckpointError("Checkpoint IDs and ID counters must be non-negative")
        if creature_ids and next_creature_id <= max(creature_ids):
            raise CheckpointError("next_creature_id must exceed every saved creature ID")
        if resource_ids and next_resource_id <= max(resource_ids):
            raise CheckpointError("next_resource_id must exceed every saved resource ID")
        engine = SimulationEngine(config, seed=int(payload["seed"]))
        engine.tick = int(payload["tick"])
        external_food = payload.get("external_food_energy", 0.)
        if isinstance(external_food, bool) or not isinstance(external_food, (int, float)):
            raise CheckpointError("External food energy must be a numeric input counter")
        engine.external_food_energy = float(external_food)
        records = payload.get("interventions", [])
        if not isinstance(records, list) or not all(isinstance(entry, dict) for entry in records):
            raise CheckpointError("Interventions must be an array of records")
        engine.interventions = [dict(entry) for entry in records]
        engine.rng.bit_generator.state = payload["rng_state"]
        creatures = [
            _restore_creature(item, strict_v3=version == VERSION)
            for item in payload["creatures"]
        ]
        resources = [
            Resource(
                id=_json_integer(item["id"], "resource ID"),
                position=np.asarray(item["position"], dtype=float),
                energy=float(item["energy"]),
                radius=float(item["radius"]),
            )
            for item in payload["resources"]
        ]
        engine.creatures = {item.id: item for item in creatures}
        if len(engine.creatures) != len(creatures):
            raise CheckpointError("Checkpoint contains duplicate creature IDs")
        engine.resources = {item.id: item for item in resources}
        if len(engine.resources) != len(resources):
            raise CheckpointError("Checkpoint contains duplicate resource IDs")
        engine.lineage = LineageStore.from_records(payload["lineage"])
        engine.environment = EnvironmentState.from_dict(payload["environment"])
        if config.ecology.enabled:
            engine.habitat = HabitatField.from_dict(
                payload["habitat"], config.ecology, width=config.world.width,
                height=config.world.height, boundary=config.world.boundary)
        elif payload.get("habitat") is not None:
            raise CheckpointError("Disabled ecology cannot contain an active habitat field")
        engine.culture = CultureLedger.from_dict(payload.get("culture"))
        engine.death_causes = {
            str(key): int(value) for key, value in payload.get("death_causes", {}).items()
        }
        engine.combat_events = [dict(item) for item in payload.get("combat_events", [])]
        engine.recent_events = [dict(item) for item in payload.get("recent_events", [])]
        engine.metrics = MetricsRecorder()
        engine.metrics.samples = [MetricSample(**item) for item in payload.get("metrics", [])]
        engine.metrics.restore_birth_cohorts(payload.get("birth_cohorts", []),
                                           current_tick=engine.tick,
                                           total_births=int(payload["total_births"]))
        engine.next_creature_id = next_creature_id
        engine.next_resource_id = next_resource_id
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
