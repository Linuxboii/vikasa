"""A presentation biome must replace founders through actual reproduction."""

from pathlib import Path

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine


def test_showcase_replaces_founders_with_multiple_living_generations():
    config = SimulationConfig.from_json(Path(__file__).resolve().parents[2] /
                                        "config" / "showcase.json")
    engine = SimulationEngine(config, 2026)
    engine.step(6000)
    assert len(engine.creatures) >= 30
    assert engine.total_births >= 150
    assert engine.total_deaths >= 30
    assert max(engine.lineage.generation_of(c.id) for c in engine.creatures.values()) >= 3
    assert engine.audit_invariants() == []
