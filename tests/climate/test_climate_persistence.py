from __future__ import annotations

import json

import pytest

from evolution_sim.bridge import GodotSimulationServer
from evolution_sim.io.checkpoints import CheckpointError, load_checkpoint, save_checkpoint
from evolution_sim.simulation.engine import SimulationEngine

from .test_climate_engine import climate_config


def _thermal_state(engine: SimulationEngine):
    return ([(key, item.thermal_optimum, item.thermal_stress)
             for key, item in sorted(engine.creatures.items())],
            str(engine.rng.bit_generator.state), engine.environment.temperature_c)


def test_climate_checkpoint_round_trip_continues_identically(tmp_path) -> None:
    config = climate_config(anomaly_c=[[0, 0.0], [10, 3.0]])
    original = SimulationEngine(config, seed=8)
    original.step(200)
    path = save_checkpoint(original, tmp_path / "climate.json")
    restored = load_checkpoint(path)
    assert restored.climate is not None and restored.environment.climate is restored.climate
    original.step(200)
    restored.step(200)
    assert _thermal_state(restored) == _thermal_state(original)


def test_legacy_checkpoint_has_no_thermal_keys(tmp_path, tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=8)
    engine.step(20)
    payload = json.loads(save_checkpoint(engine, tmp_path / "legacy.json").read_text())
    assert all("thermal_optimum" not in item for item in payload["creatures"])
    assert "temperature_c" not in payload["environment"]
    assert "climate" not in payload["config"]


def test_climate_checkpoint_missing_optimum_rejected(tmp_path) -> None:
    engine = SimulationEngine(climate_config(), seed=8)
    engine.step(10)
    path = save_checkpoint(engine, tmp_path / "climate.json")
    payload = json.loads(path.read_text())
    del payload["creatures"][0]["thermal_optimum"]
    path.write_text(json.dumps(payload))
    with pytest.raises(CheckpointError, match="thermal_optimum"):
        load_checkpoint(path)


def test_bridge_document_includes_climate_block() -> None:
    bridge = GodotSimulationServer(climate_config(), seed=3, port=0)
    bridge.paused = True
    bridge.engine.step(5)
    state = bridge._build_state()
    assert state["environment"]["temperature_c"] == pytest.approx(25.0)
    assert state["climate"]["mean_optimum_c"] == pytest.approx(25.0, abs=1.0)
    assert set(state["climate"]) >= {"lag_c", "mean_stress", "sd_optimum_c"}


def test_bridge_document_without_climate(tiny_config) -> None:
    bridge = GodotSimulationServer(tiny_config, seed=3, port=0)
    bridge.paused = True
    state = bridge._build_state()
    assert state["climate"] is None
    assert "temperature_c" not in state["environment"]
