from __future__ import annotations

import json
from dataclasses import replace

import pytest

from evolution_sim.io.checkpoints import CheckpointError, load_checkpoint, save_checkpoint
from evolution_sim.simulation.behavior import ActionName, BehaviorState, InstinctVector
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


def test_checkpoint_continues_with_exact_rng_and_world_state(tiny_config, tmp_path) -> None:
    engine = SimulationEngine(tiny_config, seed=918)
    engine.environment.schedule(EnvironmentEvent("drought", 20, 25, 0.3))
    engine.step(37)
    path = tmp_path / "session.json"

    save_checkpoint(engine, path)
    restored = load_checkpoint(path)
    engine.step(60)
    restored.step(60)

    assert restored.snapshot() == engine.snapshot()
    assert restored.environment.to_dict() == engine.environment.to_dict()
    assert restored.metrics.rows() == engine.metrics.rows()
    assert restored.audit_invariants() == []


def test_fractional_spawn_accumulator_survives_round_trip(tiny_config, tmp_path) -> None:
    config = replace(
        tiny_config,
        initial_population=1,
        resources=replace(tiny_config.resources, initial_count=0, spawn_rate=0.25),
    )
    engine = SimulationEngine(config, seed=4)
    engine.step(3)
    path = tmp_path / "fractional.json"
    save_checkpoint(engine, path)

    restored = load_checkpoint(path)
    restored.step()

    assert len(restored.resources) == 1


def test_checkpoint_write_is_atomic_and_leaves_no_temporary_file(tiny_config, tmp_path) -> None:
    engine = SimulationEngine(tiny_config, seed=2)
    path = tmp_path / "atomic.json"

    save_checkpoint(engine, path)

    assert path.exists()
    assert not (tmp_path / "atomic.json.tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "vikasa"


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"format":"vikasa","version":999}',
        '{"format":"vikasa","version":1,"tick":NaN}',
    ],
)
def test_corrupt_incompatible_and_nonfinite_checkpoints_are_rejected(
    tiny_config, tmp_path, payload: str
) -> None:
    engine = SimulationEngine(tiny_config, seed=5)
    before = engine.snapshot()
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(CheckpointError):
        load_checkpoint(path)

    assert engine.snapshot() == before


@pytest.mark.parametrize("legacy_version", [1, 2])
def test_legacy_checkpoint_migration_is_in_memory_and_bounds_home_ranges(
    tiny_config, tmp_path, legacy_version: int
) -> None:
    engine = SimulationEngine(tiny_config, seed=18)
    engine.step(4)
    path = tmp_path / f"v{legacy_version}.json"
    save_checkpoint(engine, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["version"] = legacy_version
    saved_positions = {item["id"]: item["position"] for item in payload["creatures"]}
    for creature in payload["creatures"]:
        for key in ("behavior_state", "home_center", "home_radius", "home_migration_ticks"):
            creature.pop(key, None)
    path.write_text(json.dumps(payload), encoding="utf-8")
    source_bytes = path.read_bytes()

    restored = load_checkpoint(path)

    assert path.read_bytes() == source_bytes
    assert restored.tick == engine.tick
    assert restored.rng.bit_generator.state == engine.rng.bit_generator.state
    assert restored.next_creature_id == engine.next_creature_id
    assert restored.next_resource_id == engine.next_resource_id
    limit = min(tiny_config.world.width, tiny_config.world.height) / 2
    for creature in restored.creatures.values():
        assert creature.behavior_state.action is ActionName.EXPLORE
        assert len(creature.behavior_state.drives.values) == 6
        assert all(0 <= value <= 1 for value in creature.behavior_state.drives.values)
        assert 0 < creature.home_radius <= limit
        assert tuple(creature.home_center) == tuple(saved_positions[creature.id])
        assert creature.home_migration_ticks == 0


def test_new_checkpoint_round_trips_behavior_target_and_continues_exactly(
    tiny_config, tmp_path
) -> None:
    engine = SimulationEngine(tiny_config, seed=319)
    creature = engine.creatures[min(engine.creatures)]
    creature.behavior_state = BehaviorState(
        action=ActionName.FORAGE,
        started_tick=3,
        target_kind="food",
        target_id=17,
        target_position=(4.5, 8.25),
        drives=InstinctVector((0.1, 0.8, 0.0, 0.0, 0.0, 0.2)),
        utility_breakdown={ActionName.FORAGE: 0.75},
        reason="Following the strongest nearby food signal",
    )
    creature.home_center = creature.position.copy()
    creature.home_radius = min(tiny_config.world.width, tiny_config.world.height) / 2
    creature.home_migration_ticks = 11
    path = tmp_path / "v3.json"

    save_checkpoint(engine, path)
    restored = load_checkpoint(path)
    engine.step(20)
    restored.step(20)

    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 3
    assert restored.snapshot() == engine.snapshot()
    assert restored.rng.bit_generator.state == engine.rng.bit_generator.state
