from __future__ import annotations

import json
from dataclasses import replace

import pytest

from evolution_sim.io.checkpoints import CheckpointError, load_checkpoint, save_checkpoint
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
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == "evolution-simulator"


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"format":"evolution-simulator","version":999}',
        '{"format":"evolution-simulator","version":1,"tick":NaN}',
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
