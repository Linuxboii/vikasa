"""Finite-volume habitat tests catch creation, unstable transport and lost state."""
from dataclasses import replace

import numpy as np
import pytest

from evolution_sim import config
from evolution_sim.simulation import environment


def habitat(**overrides):
    assert hasattr(config, "EcologyConfig"), "Spatial ecology configuration is missing"
    assert hasattr(environment, "HabitatField"), "Finite habitat dynamics are missing"
    settings = config.EcologyConfig(enabled=True, columns=3, rows=2, **overrides)
    return environment.HabitatField(settings, width=90, height=60, boundary="collision")


def weather(tick=0):
    state = environment.EnvironmentState()
    state.update(tick)
    return state


def test_diffusion_preserves_mass_and_nonnegativity():
    field = habitat(growth_rate=0, rainfall_rate=0, evaporation_rate=0,
                    water_diffusion=.2, biomass_diffusion=.2)
    field.water[:] = [[1, 0, 0], [0, 0, 0]]
    field.biomass[:] = [[60, 0, 0], [0, 0, 0]]
    field.step(weather())
    assert field.water.sum() == pytest.approx(1)
    assert field.biomass.sum() == pytest.approx(60)
    assert field.water[0, 0] == pytest.approx(.6)
    assert field.water[0, 1] == pytest.approx(.2)
    assert field.biomass[0, 0] == pytest.approx(36)
    assert np.min(field.water) >= 0


def test_harvest_transfers_exact_energy_and_exhaustion_refuses_food():
    field = habitat()
    before = field.biomass.sum()
    position = field.harvest(30, np.random.default_rng(4))
    assert position is not None and 0 <= position[0] < 90 and 0 <= position[1] < 60
    assert field.biomass.sum() == pytest.approx(before - 30)
    assert field.summary()["harvested_energy"] == 30
    assert abs(field.summary()["biomass_balance_residual"]) < 1e-10
    field.biomass[:] = 0
    assert field.harvest(30, np.random.default_rng(4)) is None


def test_drought_reduces_water_and_biomass_without_hidden_refill():
    normal, drought = habitat(), habitat()
    dry = weather()
    dry.schedule(environment.EnvironmentEvent("drought", 0, 100, .05))
    for tick in range(100):
        wet = weather(tick)
        dry.update(tick)
        normal.step(wet)
        drought.step(dry)
    assert drought.water.mean() < normal.water.mean()
    assert drought.biomass.sum() < normal.biomass.sum()
    assert abs(drought.summary()["biomass_balance_residual"]) < 1e-8
    assert abs(drought.summary()["water_balance_residual"]) < 1e-8


def test_logistic_flow_reaches_hand_derived_value():
    field = habitat(growth_rate=.1, rainfall_rate=0, evaporation_rate=0,
                    water_diffusion=0, biomass_diffusion=0, water_half_saturation=0,
                    transpiration_rate=0)
    field.biomass[:] = 50
    state = weather()
    state.temperature = .6
    state.seasonal_food_multiplier = 1
    field.step(state)
    assert field.biomass[0, 0] == pytest.approx(52.4979187479)


def test_integer_json_parameters_do_not_truncate_water_or_crash():
    field = habitat(capacity=100, initial_fraction=1)
    assert field.water[0, 0] == .6
    field.step(weather())
    assert field.audit() == []


def test_seasonal_bucket_balance_matches_independent_annual_sum():
    # 96*(sum(rain)=2.28)*.004 - 96*(sum(.5+temperature)=4.25)*.002 = .05952.
    field = habitat(growth_rate=0, rainfall_rate=.004, evaporation_rate=.002,
                    water_diffusion=0, biomass_diffusion=0)
    for tick in range(384):
        field.step(weather(tick))
    assert field.water[0, 0] == pytest.approx(.65952)
    assert abs(field.summary()["water_balance_residual"]) < 1e-10


def test_habitat_round_trip_preserves_dynamics_and_rejects_corruption():
    field = habitat()
    field.step(weather())
    payload = field.to_dict()
    restored = environment.HabitatField.from_dict(payload, field.settings,
                                                   width=90, height=60, boundary="collision")
    field.step(weather(1))
    restored.step(weather(1))
    assert restored.to_dict() == field.to_dict()
    payload["water"][0][0] = float("nan")
    with pytest.raises(ValueError):
        environment.HabitatField.from_dict(payload, field.settings,
                                          width=90, height=60, boundary="collision")


@pytest.mark.parametrize("corruption", ["baseline", "unobserved_flux"])
def test_compensating_ledger_corruption_is_rejected(corruption):
    field = habitat()
    payload = field.to_dict()
    if corruption == "baseline":
        payload["ledger"]["initial_biomass"] += 100
        payload["ledger"]["weather_loss"] += 100
    else:
        payload["ledger"]["grown_energy"] += 100
        payload["ledger"]["weather_loss"] += 100
    with pytest.raises(ValueError):
        environment.HabitatField.from_dict(payload, field.settings,
                                          width=90, height=60, boundary="collision")


def test_external_feeding_is_distinct_persisted_input(tiny_config, tmp_path):
    import json

    from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
    from evolution_sim.io.export import export_experiment
    from evolution_sim.simulation.engine import SimulationEngine
    engine = SimulationEngine(replace(tiny_config, ecology=config.EcologyConfig(enabled=True)), 4)
    assert hasattr(engine, "add_food"), "External feeding has no audited input path"
    harvested = engine.habitat.summary()["harvested_energy"]
    engine.add_food(np.array([40., 40.]), 30.)
    assert engine.external_food_energy == 30
    assert engine.habitat.summary()["harvested_energy"] == harvested
    assert engine.interventions[-1]["energy"] == 30
    path = tmp_path / "fed.json"
    save_checkpoint(engine, path)
    restored = load_checkpoint(path)
    assert restored.external_food_energy == 30
    assert restored.interventions == engine.interventions
    manifest = export_experiment(restored, tmp_path / "export")
    events = json.loads((manifest.root / "events.json").read_text())
    assert events["external_food_energy"] == 30
    assert events["interventions"] == engine.interventions


@pytest.mark.parametrize("change", [{"water_diffusion": .26}, {"rows": True},
                                     {"capacity": -1}, {"enabled": "yes"},
                                     {"capacity": 1e308}])
def test_unstable_or_invalid_ecology_rejected(change):
    assert hasattr(config, "EcologyConfig"), "Spatial ecology configuration is missing"
    with pytest.raises(config.ConfigError):
        config.EcologyConfig(**change)


def test_spatial_engine_draws_from_real_field_and_checkpoint_continues(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
    from evolution_sim.simulation.engine import SimulationEngine
    assert hasattr(config, "EcologyConfig"), "Spatial ecology configuration is missing"
    settings = config.EcologyConfig(enabled=True, columns=4, rows=3)
    cfg = replace(tiny_config, ecology=settings)
    engine = SimulationEngine(cfg, 3)
    assert engine.habitat.summary()["harvested_energy"] == 8 * cfg.resources.energy_value
    engine.step(30)
    path = tmp_path / "spatial.json"
    save_checkpoint(engine, path)
    restored = load_checkpoint(path)
    engine.step(30)
    restored.step(30)
    assert engine.snapshot() == restored.snapshot()
    assert engine.habitat.to_dict() == restored.habitat.to_dict()
    assert engine.audit_invariants() == []


def test_sparse_vegetation_yields_real_partial_food_instead_of_blocking(tiny_config):
    from evolution_sim.simulation.engine import SimulationEngine
    settings = config.EcologyConfig(enabled=True, columns=3, rows=2, initial_fraction=.1)
    cfg = replace(tiny_config, ecology=settings,
                  resources=replace(tiny_config.resources, initial_count=1))
    engine = SimulationEngine(cfg, 3)
    assert len(engine.resources) == 1, "Usable low-density vegetation was made inaccessible"
    assert engine.resources[0].energy == pytest.approx(9.)
    assert engine.habitat.summary()["harvested_energy"] == pytest.approx(9.)
    assert engine.audit_invariants() == []
