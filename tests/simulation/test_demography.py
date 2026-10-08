"""Age-dependent mortality must replace a synchronized age cliff, not disable death."""

import math
from dataclasses import replace

import pytest

from evolution_sim.config import ConfigError, SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine


def demographic_config(config, **overrides):
    data = config.to_dict()
    data["demography"] = {
        "mode": "gompertz",
        "background_hazard": 0.00002,
        "senescence_age": 1800,
        "senescence_rate": 0.002,
        **overrides,
    }
    return SimulationConfig.from_dict(data)


def test_gompertz_probability_increases_after_senescence(tiny_config):
    config = demographic_config(tiny_config, background_hazard=0.1,
                                senescence_age=100, senescence_rate=0.01)
    engine = SimulationEngine(config, seed=3)
    assert engine.senescence_probability(0) == pytest.approx(0.09516258196404043)
    assert engine.senescence_probability(100) == pytest.approx(0.09516258196404043)
    assert engine.senescence_probability(200) == pytest.approx(-math.expm1(-0.1 * math.e))
    assert engine.senescence_probability(1_000_000) == 1.0


@pytest.mark.parametrize("field,value", [("background_hazard", -1),
                                       ("senescence_rate", math.inf),
                                       ("senescence_age", True), ("mode", "immortal")])
def test_invalid_demography_is_rejected(tiny_config, field, value):
    with pytest.raises(ConfigError, match="demography"):
        demographic_config(tiny_config, **{field: value})


def test_stochastic_senescence_retains_determinism_and_mortality(tiny_config):
    config = demographic_config(tiny_config, background_hazard=0.08,
                                senescence_age=0, senescence_rate=0.01)
    config = replace(config, initial_population=30,
                     reproduction=replace(config.reproduction, minimum_age=1000),
                     energy=replace(config.energy, basal_cost=0, movement_cost=0))
    first, second = SimulationEngine(config, 19), SimulationEngine(config, 19)
    for engine in (first, second):
        for creature in engine.creatures.values():
            creature.age = 0
    first.step(20)
    second.step(20)
    assert first.snapshot() == second.snapshot()
    assert 0 < len(first.creatures) < 30
    assert first.death_causes.get("senescence", 0) > 0
    assert first.audit_invariants() == []


def test_gompertz_checkpoint_continues_exactly(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
    config = demographic_config(tiny_config, background_hazard=.003,
                                senescence_age=20, senescence_rate=.015)
    engine = SimulationEngine(config, 19)
    engine.step(12)
    path = tmp_path / "gompertz.json"
    save_checkpoint(engine, path)
    restored = load_checkpoint(path)
    engine.step(25)
    restored.step(25)
    assert restored.snapshot() == engine.snapshot()
    assert restored.death_causes == engine.death_causes
