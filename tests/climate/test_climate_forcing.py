from __future__ import annotations

import pytest

from evolution_sim.climate.forcing import ClimateForcing
from evolution_sim.config import ClimateConfig
from evolution_sim.simulation.environment import EnvironmentState

MONTHLY = tuple(20.0 + 0.5 * m for m in range(12))


def forcing(**overrides) -> ClimateForcing:
    return ClimateForcing(ClimateConfig(enabled=True, ticks_per_year=120, monthly_c=MONTHLY,
                                        **overrides))


def test_seasonal_interpolation_hits_month_centres() -> None:
    model = forcing()
    for month, value in enumerate(MONTHLY):
        assert model.seasonal_c((month + 0.5) / 12) == pytest.approx(value, abs=1e-12)


def test_seasonal_wraps_december_to_january() -> None:
    model = forcing()
    assert model.seasonal_c(0.0) == pytest.approx((MONTHLY[0] + MONTHLY[11]) / 2, abs=1e-12)
    assert model.seasonal_c(0.999999) == pytest.approx(model.seasonal_c(0.0), abs=1e-4)


def test_anomaly_linear_and_clamped() -> None:
    model = forcing(anomaly_c=((0.0, 0.0), (10.0, 2.0)))
    assert model.anomaly_c(5.0) == pytest.approx(1.0)
    assert model.anomaly_c(20.0) == 2.0
    assert model.anomaly_c(-1.0) == 0.0
    assert forcing().anomaly_c(50.0) == 0.0


def test_temperature_combines_season_and_anomaly() -> None:
    model = forcing(anomaly_c=((0.0, 1.0), (1.0, 1.0)))
    tick = 5  # phase 5/120 = month 0 centre
    assert model.temperature_c(tick) == pytest.approx(MONTHLY[0] + 1.0)
    assert model.annual_temperature_c(tick) == pytest.approx(sum(MONTHLY) / 12 + 1.0)
    assert model.year(240) == 2.0


def test_normalized_is_clamped_around_annual_mean() -> None:
    model = forcing()
    mean = sum(MONTHLY) / 12
    assert model.normalized(mean) == pytest.approx(0.6)
    assert model.normalized(mean + 100) == 1.0
    assert model.normalized(mean - 100) == 0.0


def test_environment_uses_forcing_season_and_temperature() -> None:
    model = ClimateForcing(ClimateConfig(enabled=True, ticks_per_year=40, monthly_c=MONTHLY))
    environment = EnvironmentState(model)
    environment.update(0)
    assert environment.season == "spring"
    assert environment.temperature_c == pytest.approx(model.temperature_c(0))
    environment.update(10)
    assert environment.season == "summer"
    assert environment.temperature == pytest.approx(model.normalized(model.temperature_c(10)))
    assert environment.to_dict()["temperature_c"] == pytest.approx(model.temperature_c(10))
    restored = EnvironmentState.from_dict(environment.to_dict())
    assert restored.temperature_c == environment.temperature_c


def test_environment_without_forcing_unchanged() -> None:
    environment = EnvironmentState()
    environment.update(100)
    assert environment.temperature_c is None
    assert "temperature_c" not in environment.to_dict()
    assert environment.season == "summer"
