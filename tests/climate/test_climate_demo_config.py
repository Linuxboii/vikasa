from __future__ import annotations

from pathlib import Path

from evolution_sim.bridge import GodotSimulationServer
from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "config" / "climate-demo.json"


def test_demo_config_enables_visible_warming() -> None:
    config = SimulationConfig.from_json(DEMO)
    assert config.climate.enabled and config.climate.ticks_per_year == 384
    assert config.climate.anomaly_c[-1][1] >= 4.0


def test_demo_world_is_large_but_within_renderer_capacity() -> None:
    config = SimulationConfig.from_json(DEMO)
    showcase = SimulationConfig.from_json(ROOT / "config" / "showcase.json")
    area = config.world.width * config.world.height
    assert area >= 4 * showcase.world.width * showcase.world.height
    # Godot instancing capacities: CreatureSwarm.CAPACITY 640, FoodField.CAPACITY 1024.
    assert config.reproduction.population_cap <= 640
    assert config.resources.maximum_count <= 1024


def test_demo_runs_cleanly_and_exposes_climate() -> None:
    config = SimulationConfig.from_json(DEMO)
    engine = SimulationEngine(config, seed=2026)
    engine.step(500)
    assert engine.audit_invariants() == []
    bridge = GodotSimulationServer(config, seed=2026, port=0)
    bridge.paused = True
    bridge.engine.step(20)
    state = bridge._build_state()
    assert state["climate"]["mean_optimum_c"] is not None
    assert "temperature_c" in state["environment"]


def test_hud_reads_climate_fields() -> None:
    hud = (ROOT / "godot" / "scripts" / "HUD.gd").read_text(encoding="utf-8")
    assert '"temperature_c"' in hud and '"climate"' in hud and "lag_c" in hud
