from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evolution_sim.climate.assess import AssessmentRequest, assess, plan_ssp, verdict
from evolution_sim.climate.data import RegionClimate, ssp_anomaly_c
from evolution_sim.climate.sensitivity import parameters
from evolution_sim.climate.surrogate import Surrogate

ROOT = Path(__file__).resolve().parents[2]
BASE = json.loads((ROOT / "config" / "climate-rescue.json").read_text(encoding="utf-8"))
MONTHLY = tuple(25.0 + 2.0 * np.sin(2 * np.pi * (m + 0.5) / 12) for m in range(12))
REGION = RegionClimate(
    key="test", name="Test region", latitude=10.0, longitude=70.0, monthly_c=MONTHLY,
    annual_mean_c=float(np.mean(MONTHLY)), seasonal_amplitude_c=2.0,
    trend_c_per_decade=0.2, trend_se_c_per_decade=0.03, first_year=1981, last_year=2025,
    series=((2020, 1, 24.0),), provenance={"sha256": "0" * 64})


def request(**overrides) -> AssessmentRequest:
    values = {"region": REGION, "generation_years": 1.0, "breadth_c": 4.0,
              "ssps": ("SSP2-4.5",), "seeds": (1, 2)}
    return AssessmentRequest(**{**values, **overrides})


def test_plan_ssp_math() -> None:
    plan = plan_ssp(request(generation_years=2.0), "SSP2-4.5", generation_ticks=400)
    assert plan["rate_c_per_year"] == pytest.approx(1.8 / 85)
    assert plan["rate_c_per_generation"] == pytest.approx(2 * 1.8 / 85)
    assert plan["start_anomaly_c"] == pytest.approx(ssp_anomaly_c("SSP2-4.5", 2025))
    assert plan["span_years"] == 75 and plan["truncated"] is False
    assert plan["ticks_per_year"] == 200
    a0 = plan["start_anomaly_c"]
    assert plan["knots"] == pytest.approx([(0.0, a0), (10.0, a0), (85.0, a0 + 75 * 1.8 / 85)])
    assert plan["phases"]["warming"] == pytest.approx(37.5)
    assert plan["founder_mean_c"] == pytest.approx(REGION.annual_mean_c + a0)
    short = plan_ssp(request(generation_years=1.0), "SSP2-4.5", generation_ticks=400)
    assert short["truncated"] is True and short["span_years"] == 40


def test_verdict_thresholds() -> None:
    assert verdict(0.8) == "likely persists"
    assert verdict(0.5) == "at risk"
    assert verdict(0.19) == "likely lost"


def test_request_validates_inputs() -> None:
    with pytest.raises(ValueError, match="generation_years"):
        request(generation_years=0.0)
    with pytest.raises(ValueError, match="Unknown SSP"):
        request(ssps=("SSP9",))


def _surrogate() -> Surrogate:
    params = parameters(1.0)
    rng = np.random.default_rng(0)
    x = np.column_stack([rng.uniform(p.low, p.high, 40) for p in params])
    ratio = np.clip(1 - x[:, 0], 0, 2)
    return Surrogate(params).fit(x, ratio, ratio > 0.3)


def test_outside_domains_reported(tmp_path) -> None:
    sweep_summary = {"critical_rate": {"heritable": {"logistic": {"b0": 3.0, "b1": -10.0}}}}
    result = assess(request(breadth_c=12.0, max_warming_generations=1), BASE,
                    results_dir=tmp_path, workers=1, sweep_summary=sweep_summary,
                    sweep_domain={"amplitude_c": 2.0, "breadth_c": 4.0},
                    surrogate=_surrogate(), calibration_override={"generation_ticks": 60})
    entry = result["ssps"][0]
    assert entry["sweep"] == {"status": "outside sweep domain"}
    assert entry["surrogate"] == {"status": "outside surrogate domain"}


def test_sweep_reference_withheld_beyond_swept_rates(tmp_path) -> None:
    sweep_summary = {"critical_rate": {"heritable": {"logistic": {"b0": 3.0, "b1": -10.0}}}}
    domain = {"amplitude_c": 2.0, "breadth_c": 4.0, "max_rate": 0.4,
              "founder_sd_c": 1.0, "segregation_sd_c": 0.4}
    # 20-year generations: SSP5-8.5 is ~0.82 °C/generation, twice the swept maximum.
    result = assess(request(generation_years=20.0, ssps=("SSP5-8.5",),
                            max_warming_generations=1, seeds=(1,)), BASE,
                    results_dir=tmp_path, workers=1, sweep_summary=sweep_summary,
                    sweep_domain=domain, calibration_override={"generation_ticks": 60})
    assert result["ssps"][0]["sweep"] == {"status": "outside sweep domain"}
    other = assess(request(ssps=("SSP5-8.5",), max_warming_generations=1, seeds=(1,),
                           founder_sd_c=2.0), BASE, results_dir=tmp_path / "b", workers=1,
                   sweep_summary=sweep_summary, sweep_domain=domain,
                   calibration_override={"generation_ticks": 60})
    assert other["ssps"][0]["sweep"] == {"status": "outside sweep domain"}


def test_region_too_harsh_at_baseline_is_reported_not_crashed(tmp_path) -> None:
    harsh = replace(REGION, key="harsh", seasonal_amplitude_c=15.0,
                    monthly_c=tuple(25.0 + 16.0 * np.sin(2 * np.pi * (m + 0.5) / 12)
                                    for m in range(12)))
    result = assess(request(region=harsh, breadth_c=1.0), BASE, results_dir=tmp_path,
                    workers=1, calibration_kwargs={"seeds": [101], "burn_in_ticks": 400,
                                                   "measure_ticks": 400})
    json.dumps(result, allow_nan=False)
    assert result["baseline_viable"] is False
    entry = result["ssps"][0]
    assert entry["verdict"] == "not viable in present-day climate"
    assert entry["direct"]["n"] == 0
    assert not (tmp_path / "results.jsonl").exists()
    assert any("present-day" in caveat for caveat in result["caveats"])
    assert result["baseline_viability"] == {"survived": 0, "n": 1}
    assert any("0 of 1" in caveat for caveat in result["caveats"])


def test_worker_crash_is_not_reported_as_non_viable(tmp_path, monkeypatch) -> None:
    from evolution_sim.climate import assess as module

    def crash(*args, **kwargs):
        raise RuntimeError("A process in the process pool was terminated abruptly")

    monkeypatch.setattr(module, "calibrate_generation_ticks", crash)
    with pytest.raises(RuntimeError, match="terminated abruptly"):
        assess(request(), BASE, results_dir=tmp_path, workers=1)
    assert not (tmp_path / "assessment.json").exists()


def test_calibration_uses_the_assessment_seasonal_clock(tmp_path, monkeypatch) -> None:
    from evolution_sim.climate import assess as module

    seen = {}

    def fake(base, seeds, **kwargs):
        seen.update(kwargs, seeds=seeds)
        return {"generation_ticks": 60, "seeds": seeds, "viable_seeds": len(seeds)}

    monkeypatch.setattr(module, "calibrate_generation_ticks", fake)
    assess(request(generation_years=2.0, max_warming_generations=1, seeds=(1,)), BASE,
           results_dir=tmp_path, workers=1,
           calibration_kwargs={"reference_generation_ticks": 400})
    assert seen["provisional_ticks_per_year"] == 200
    assert len(seen["seeds"]) == 4


def test_assess_end_to_end_small(tmp_path) -> None:
    sweep_summary = {"critical_rate": {"heritable": {"logistic": {"b0": 3.0, "b1": -10.0}}}}
    result = assess(replace(request(), ssps=("SSP1-2.6", "SSP5-8.5"),
                            max_warming_generations=2), BASE,
                    results_dir=tmp_path, workers=2, sweep_summary=sweep_summary,
                    sweep_domain={"amplitude_c": 2.0, "breadth_c": 4.0},
                    surrogate=_surrogate(), calibration_override={"generation_ticks": 60})
    json.dumps(result, allow_nan=False)
    assert [entry["ssp"] for entry in result["ssps"]] == ["SSP1-2.6", "SSP5-8.5"]
    for entry in result["ssps"]:
        assert entry["direct"]["n"] == 2
        assert entry["verdict"] in {"likely persists", "at risk", "likely lost"}
        assert 0 <= entry["sweep"]["p"] <= 1
        assert 0 <= entry["surrogate"]["p"] <= 1
        assert entry["observed_trend_c_per_decade"] == 0.2
    assert (tmp_path / "assessment.json").exists()
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == 4
    assert result["caveats"]
