from __future__ import annotations

from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


def test_seeded_engines_remain_equivalent_through_environmental_shift(tiny_config) -> None:
    first = SimulationEngine(tiny_config, seed=2026)
    second = SimulationEngine(tiny_config, seed=2026)
    for engine in (first, second):
        engine.environment.schedule(EnvironmentEvent("drought", 30, 25, 0.25))
        engine.environment.schedule(EnvironmentEvent("abundance", 70, 15, 1.8))

    first.step(120)
    second.step(120)

    assert first.snapshot() == second.snapshot()
    assert first.environment.to_dict() == second.environment.to_dict()
    assert first.audit_invariants() == []


def test_different_seeds_produce_different_worlds(tiny_config) -> None:
    first = SimulationEngine(tiny_config, seed=10)
    second = SimulationEngine(tiny_config, seed=11)
    first.step(10)
    second.step(10)

    assert first.snapshot() != second.snapshot()
