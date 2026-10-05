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


def test_behavior_logs_repeat_each_tick_in_stable_id_order(tiny_config):
    first = SimulationEngine(tiny_config, seed=2026)
    second = SimulationEngine(tiny_config, seed=2026)
    second.creatures = dict(reversed(list(second.creatures.items())))
    actions = set()
    for _ in range(120):
        first.step()
        second.step()
        first_log = [
            (
                key,
                item.behavior_state,
                item.home_center.tolist(),
                item.home_radius,
                item.home_migration_ticks,
            )
            for key, item in sorted(first.creatures.items())
        ]
        second_log = [
            (
                key,
                item.behavior_state,
                item.home_center.tolist(),
                item.home_radius,
                item.home_migration_ticks,
            )
            for key, item in sorted(second.creatures.items())
        ]
        assert first_log == second_log
        assert first.audit_invariants() == second.audit_invariants() == []
        actions.update(item.behavior_state.action for item in first.creatures.values())
    assert "forage" in actions
    assert len(actions) > 1
