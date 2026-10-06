from pathlib import Path

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent

ROOT = Path(__file__).resolve().parents[2]


def test_fire_causes_exposure_deaths_and_preserves_resilient_survivors() -> None:
    config = SimulationConfig.from_json(ROOT / "config" / "showcase.json")
    control = SimulationEngine(config, seed=2026)
    exposed = SimulationEngine(config, seed=2026)
    exposed.environment.schedule(EnvironmentEvent("wildfire", 80, 160, 0.7))
    control.step(300)
    exposed.step(300)

    assert 0 < len(exposed.creatures) < len(control.creatures)
    assert exposed.death_causes.get("environmental exposure", 0) > 0
    assert exposed.total_deaths > control.total_deaths
    assert exposed.audit_invariants() == []


def test_drought_erodes_existing_food_even_before_regeneration(tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=8)
    before = sum(food.energy for food in engine.resources.values())
    engine.environment.schedule(EnvironmentEvent("drought", 0, 200, 0.2))
    engine.environment.update(0)
    engine._weather_resource_loss()

    assert sum(food.energy for food in engine.resources.values()) < before
    assert engine.environment.rainfall < 0.76
    assert engine.environment.metabolic_multiplier > 1
