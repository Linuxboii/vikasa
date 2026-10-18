from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np
import pytest

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine

ROOT = Path(__file__).resolve().parents[2]


def climate_config(**climate_overrides) -> SimulationConfig:
    data = json.loads((ROOT / "config" / "default.json").read_text(encoding="utf-8"))
    data["world"].update(width=240, height=160)
    data["initial_population"] = 20
    data["reproduction"].update(minimum_age=30, cooldown=40, population_cap=60)
    data["resources"].update(initial_count=60, maximum_count=120, spawn_rate=0.8)
    data["climate"] = {"enabled": True, "ticks_per_year": 120, "monthly_c": [25.0] * 12,
                       "tolerance_breadth_c": 4.0, **climate_overrides}
    return SimulationConfig.from_dict(data)


def test_founders_carry_optimum_near_founder_mean() -> None:
    engine = SimulationEngine(climate_config(founder_sd_c=0.5), seed=1)
    optima = [item.thermal_optimum for item in engine.creatures.values()]
    assert statistics.mean(optima) == pytest.approx(25.0, abs=0.5)
    assert len(set(optima)) == len(optima)


def test_climate_run_is_deterministic() -> None:
    def state(engine: SimulationEngine):
        return ([(k, c.thermal_optimum, c.position.tolist()) for k, c in
                 sorted(engine.creatures.items())], str(engine.rng.bit_generator.state))

    first, second = (SimulationEngine(climate_config(), seed=5) for _ in range(2))
    first.step(300)
    second.step(300)
    assert state(first) == state(second)
    assert first.environment.temperature_c == pytest.approx(25.0)


def test_extreme_heat_kills_by_thermal_stress() -> None:
    engine = SimulationEngine(climate_config(tolerance_breadth_c=2.0,
                                             anomaly_c=[[0, 15.0], [1, 15.0]]), seed=2)
    for _ in range(30):
        engine.step(100)
        if engine.extinct:
            break
    assert engine.extinct
    assert engine.death_causes.get("thermal stress", 0) > 0


def test_stress_blocks_reproduction_eligibility() -> None:
    engine = SimulationEngine(climate_config(), seed=3)
    creature = next(iter(engine.creatures.values()))
    creature.age = 1000
    creature.energy = engine.config.energy.maximum
    creature.thermal_stress = 0.0
    assert engine._eligible(creature)
    creature.thermal_stress = 0.9
    assert not engine._eligible(creature)


def test_children_inherit_under_heritable_arm() -> None:
    engine = SimulationEngine(climate_config(founder_sd_c=1.0), seed=4)
    engine.step(1500)
    children = [c for c in engine.creatures.values() if c.parents is not None
                and all(p in engine.creatures for p in c.parents)]
    assert children, "expected births with living parents"
    for child in children:
        mid = np.mean([engine.creatures[p].thermal_optimum for p in child.parents])
        assert abs(child.thermal_optimum - mid) < 6 * 0.42


def test_audit_flags_out_of_bounds_optimum() -> None:
    engine = SimulationEngine(climate_config(), seed=6)
    next(iter(engine.creatures.values())).thermal_optimum = 99.0
    assert any("thermal optimum" in error for error in engine.audit_invariants())


def test_audit_flags_optimum_without_climate(tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=6)
    next(iter(engine.creatures.values())).thermal_optimum = 1.0
    assert any("thermal optimum" in error for error in engine.audit_invariants())
