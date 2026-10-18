from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from evolution_sim.climate.protocol import (
    RescueCondition,
    RescuePhases,
    build_config,
    calibrate_generation_ticks,
    run_replicate,
    run_tasks,
    sweep_tasks,
)

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "config" / "climate-rescue.json").read_text(encoding="utf-8"))
G = 120
PHASES = RescuePhases(burn_in=1, warming=2, hold=1)


def strip(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "elapsed_seconds"}


def test_build_config_knots_and_capacity_scaling() -> None:
    config = build_config(BASE, RescueCondition("none", 0.5, 1, capacity_scale=0.5), G,
                          RescuePhases(8, 20, 8))
    assert config.climate.anomaly_c == ((0.0, 0.0), (8.0, 0.0), (28.0, 10.0))
    assert config.climate.ticks_per_year == G
    assert config.climate.inheritance == "none"
    assert config.reproduction.population_cap == round(BASE["reproduction"]["population_cap"] / 2)
    assert config.resources.spawn_rate == pytest.approx(BASE["resources"]["spawn_rate"] / 2)
    assert config.initial_population <= config.reproduction.population_cap


def test_amplitude_override_builds_sinusoid() -> None:
    config = build_config(BASE, RescueCondition("heritable", 0.0, 1, amplitude_c=3.0,
                                                breadth_c=6.0), G, PHASES)
    mean = sum(BASE["climate"]["monthly_c"]) / 12
    assert sum(config.climate.monthly_c) / 12 == pytest.approx(mean, abs=1e-9)
    assert (max(config.climate.monthly_c) - min(config.climate.monthly_c)) / 2 == \
        pytest.approx(3.0, abs=1e-9)
    assert math.isclose(config.climate.monthly_c[2], config.climate.monthly_c[3], abs_tol=1e-9)
    assert config.climate.tolerance_breadth_c == 6.0


def test_condition_key_is_canonical() -> None:
    assert RescueCondition("heritable", 0.1, 3).key() == RescueCondition("heritable", 0.1, 3).key()
    assert RescueCondition("heritable", 0.1, 3).key() != RescueCondition("none", 0.1, 3).key()


def test_replicate_outcome_schema_and_determinism() -> None:
    config = build_config(BASE, RescueCondition("heritable", 0.2, 4), G, PHASES)
    first = run_replicate(config, 4, G, PHASES)
    second = run_replicate(config, 4, G, PHASES)
    assert strip(first) == strip(second)
    assert first["status"] == "ok" and first["invariant_errors"] == []
    expected = {"survived", "extinction_generation", "n_pre", "n_min", "n_final", "ratio",
                "theta0", "evolved_shift_c", "lag_c", "rescue_signature", "death_causes",
                "ticks", "trajectory"}
    assert expected <= set(first)
    assert {"tick", "generation", "population", "annual_temperature_c", "anomaly_c",
            "mean_optimum_c", "sd_optimum_c", "mean_stress"} <= set(first["trajectory"][0])
    assert first["trajectory"][-1]["anomaly_c"] == pytest.approx(0.4)


def test_extinct_replicate_serializes_with_nulls() -> None:
    config = build_config(BASE, RescueCondition("heritable", 12.0, 2), G, PHASES)
    row = run_replicate(config, 2, G, PHASES)
    assert row["survived"] is False and row["ratio"] == 0.0
    assert row["extinction_generation"] is not None
    assert row["lag_c"] is None and row["evolved_shift_c"] is None
    json.dumps(row, allow_nan=False)


def _tasks():
    return sweep_tasks(BASE, rates=(0.0, 0.3), arms=("heritable",), seeds=(1, 2),
                       generation_ticks=G, phases=PHASES)[:3]


def test_run_tasks_resumes_and_drops_partial_line(tmp_path) -> None:
    path = tmp_path / "results.jsonl"
    rows = run_tasks(_tasks(), path, workers=1)
    assert len(rows) == 3
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n" + lines[1] + "\n" + lines[2][:25], encoding="utf-8")
    seen = []
    resumed = run_tasks(_tasks(), path, workers=1, progress=seen.append)
    assert len(seen) == 1, "only the truncated task is recomputed"
    assert [strip(row) for row in resumed] == [strip(row) for row in rows]
    assert all(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())


def test_run_tasks_parallel_matches_serial(tmp_path) -> None:
    serial = run_tasks(_tasks(), tmp_path / "serial.jsonl", workers=1)
    parallel = run_tasks(_tasks(), tmp_path / "parallel.jsonl", workers=2)
    assert [strip(row) for row in serial] == [strip(row) for row in parallel]
    assert [row["key"] for row in serial] == sorted(row["key"] for row in serial)
    assert all(row["meta"]["arm"] == "heritable" for row in serial)


def test_task_failure_becomes_error_row(tmp_path) -> None:
    task = dict(_tasks()[0], config={"broken": True}, key="bad")
    rows = run_tasks([task], tmp_path / "r.jsonl", workers=1)
    assert rows[0]["status"] == "error" and "broken" in rows[0]["error"]


def test_calibration_returns_positive_generation_ticks() -> None:
    result = calibrate_generation_ticks(BASE, [3], burn_in_ticks=300, measure_ticks=900)
    assert result["generation_ticks"] > 0
    assert result["seeds"] == [3] and len(result["slopes"]) == 1
    assert result["viable_seeds"] == 1


def test_calibration_raises_dedicated_error_when_every_seed_dies() -> None:
    from evolution_sim.climate.protocol import CalibrationExtinct

    harsh = json.loads(json.dumps(BASE))
    harsh["climate"]["monthly_c"] = [25.0 + (15.0 if m in (4, 5, 6) else -15.0)
                                     for m in range(12)]
    with pytest.raises(CalibrationExtinct, match="0 of 1"):
        calibrate_generation_ticks(harsh, [3], breadth_c=1.0, burn_in_ticks=300,
                                   measure_ticks=300)
    assert not issubclass(CalibrationExtinct, RuntimeError)
