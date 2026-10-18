from __future__ import annotations

import json
from pathlib import Path

import pytest

from evolution_sim.config import ConfigError, SimulationConfig

ROOT = Path(__file__).resolve().parents[2]


def raw_config(**climate) -> dict:
    data = json.loads((ROOT / "config" / "default.json").read_text(encoding="utf-8"))
    if climate:
        data["climate"] = climate
    return data


def enabled(**overrides) -> dict:
    return {"enabled": True, "ticks_per_year": 120, "monthly_c": [20.0 + m for m in range(12)],
            "anomaly_c": [[0, 0.0], [10, 2.5]], **overrides}


def test_climate_absent_means_disabled_and_not_serialized() -> None:
    config = SimulationConfig.from_json(ROOT / "config" / "default.json")
    assert config.climate.enabled is False
    assert "climate" not in config.to_dict()


def test_climate_round_trip_preserves_all_fields() -> None:
    config = SimulationConfig.from_dict(raw_config(**enabled(inheritance="none",
                                                              founder_mean_c=24.0)))
    data = config.to_dict()
    assert data["climate"]["anomaly_c"] == [[0.0, 0.0], [10.0, 2.5]]
    assert SimulationConfig.from_dict(json.loads(json.dumps(data))) == config
    assert config.climate.inheritance == "none"


def test_climate_annual_mean_and_founder_default() -> None:
    config = SimulationConfig.from_dict(raw_config(**enabled(monthly_c=[float(m)
                                                                        for m in range(12)])))
    assert config.climate.annual_mean_c == 5.5
    assert config.climate.resolved_founder_mean_c == 5.5


@pytest.mark.parametrize(("patch", "fragment"), [
    ({"monthly_c": [20.0] * 11}, "climate.monthly_c"),
    ({"anomaly_c": [[5, 1.0], [5, 2.0]]}, "climate.anomaly_c"),
    ({"tolerance_breadth_c": 0}, "climate.tolerance_breadth_c"),
    ({"inheritance": "lamarck"}, "climate.inheritance"),
    ({"unknown": 1}, "climate.unknown"),
    ({"ticks_per_year": 2}, "climate.ticks_per_year"),
    ({"warm_side_ratio": 0}, "climate.warm_side_ratio"),
])
def test_climate_rejects_invalid(patch: dict, fragment: str) -> None:
    with pytest.raises(ConfigError, match=fragment.replace(".", r"\.")):
        SimulationConfig.from_dict(raw_config(**enabled(**patch)))
