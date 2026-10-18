from __future__ import annotations

import json

import numpy as np
import pytest

from evolution_sim.climate.analysis import (
    critical_rate,
    fit_logistic,
    lag_regression,
    rescue_gain,
    signature_frequency,
    summarize_sweep,
    sweep_criteria,
    wilson_interval,
)

RATES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)


def fake_rows(kc_heritable=0.4, kc_none=0.15, seeds=12, noise=0.0, rng_seed=0):
    rng = np.random.default_rng(rng_seed)
    rows = []
    for arm, kc in (("heritable", kc_heritable), ("none", kc_none)):
        for rate in RATES:
            for seed in range(seeds):
                jitter = rng.normal(0, noise) if noise else 0.0
                survived = rate + jitter < kc
                warming = rate * 20
                shift = (0.8 if arm == "heritable" else 0.05) * warming
                rows.append({
                    "key": f"{arm}-{rate}-{seed}", "status": "ok",
                    "meta": {"arm": arm, "rate_c_per_gen": rate, "seed": seed},
                    "survived": bool(survived), "ratio": 1.0 if survived else 0.0,
                    "lag_c": 2.0 * rate if survived else None,
                    "evolved_shift_c": shift if survived else None,
                    "rescue_signature": bool(survived and arm == "heritable"
                                             and rate > kc / 2),
                    "invariant_errors": [],
                })
    return rows


def test_wilson_matches_known_value() -> None:
    low, high = wilson_interval(9, 12)
    assert low == pytest.approx(0.4677, abs=1e-3)
    assert high == pytest.approx(0.9111, abs=1e-3)
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_fit_logistic_rejects_single_class() -> None:
    with pytest.raises(ValueError, match="both"):
        fit_logistic(np.array([0.1, 0.2]), np.array([1, 1]))


def test_critical_rate_recovers_threshold() -> None:
    result = critical_rate(fake_rows(noise=0.05), "heritable", n_boot=400, seed=1)
    assert result["estimate"] == pytest.approx(0.4, abs=0.06)
    assert result["ci95"][0] <= 0.4 <= result["ci95"][1]
    assert [point["rate"] for point in result["curve"]] == list(RATES)


def test_perfect_separation_is_finite() -> None:
    result = critical_rate(fake_rows(), "heritable", n_boot=200, seed=2)
    assert np.isfinite(result["estimate"])
    assert 0.3 < result["estimate"] < 0.5
    assert 0.0 <= result["undefined_fraction"] <= 1.0


def test_rescue_gain_positive() -> None:
    gain = rescue_gain(fake_rows(noise=0.05), n_boot=400, seed=3)
    assert gain["estimate"] == pytest.approx(0.25, abs=0.08)
    assert gain["ci95"][0] > 0


def test_lag_regression_linear() -> None:
    result = lag_regression(fake_rows(), below_rate=0.4)
    assert result["slope"] == pytest.approx(2.0)
    assert result["pearson_r"] == pytest.approx(1.0)


def test_signature_frequency_per_rate() -> None:
    frequency = {row["rate"]: row["fraction"] for row in signature_frequency(fake_rows())}
    assert frequency[0.0] == 0.0 and frequency[0.3] == 1.0


def test_criteria_report_pass_and_fail() -> None:
    passing = {c["id"]: c["passed"] for c in sweep_criteria(
        summarize_sweep(fake_rows(noise=0.05), n_boot=300, seed=4))}
    assert passing == {"C1": True, "C2": True, "C3": True, "C4": True, "C5": True, "C6": True}
    flipped = {c["id"]: c["passed"] for c in sweep_criteria(
        summarize_sweep(fake_rows(kc_heritable=0.15, kc_none=0.4, noise=0.05),
                        n_boot=300, seed=4))}
    assert flipped["C3"] is False


def test_error_rows_fail_integrity() -> None:
    rows = fake_rows()
    rows.append({"key": "x", "status": "error", "error": "boom",
                 "meta": {"arm": "heritable", "rate_c_per_gen": 0.1, "seed": 99}})
    criteria = {c["id"]: c for c in sweep_criteria(summarize_sweep(rows, n_boot=100, seed=5))}
    assert criteria["C6"]["passed"] is False


def test_summary_is_json_serializable() -> None:
    json.dumps(summarize_sweep(fake_rows(), n_boot=100, seed=6), allow_nan=False)
