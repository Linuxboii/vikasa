from __future__ import annotations

import numpy as np
import pytest

from evolution_sim.climate.sensitivity import latin_hypercube, parameters, scale
from evolution_sim.climate.surrogate import Surrogate, cross_validate, holdout_metrics

PARAMS = parameters(1.0)


def synthetic(n: int, seed: int):
    rng = np.random.default_rng(seed)
    x = scale(latin_hypercube(n, 6, seed), PARAMS)
    ratio = np.clip(1 - 1.2 * x[:, 0] + 0.1 * x[:, 1] / 8 + rng.normal(0, 0.05, n), 0, 2)
    return x, ratio, ratio > 0.2


def test_threshold_learned_between_classes() -> None:
    x, ratio, survived = synthetic(120, 8)
    model = Surrogate(PARAMS).fit(x, ratio, survived)
    assert ratio[~survived].max() <= model.threshold <= ratio[survived].min()


def test_surrogate_fits_synthetic_signal() -> None:
    x, ratio, survived = synthetic(120, 1)
    model = Surrogate(PARAMS, seed=0).fit(x[:90], ratio[:90], survived[:90])
    metrics = holdout_metrics(model, x[90:], ratio[90:], survived[90:])
    assert metrics["r2"] >= 0.8
    assert metrics["auc"] >= 0.9
    assert metrics["n"] == 30


def test_survival_probability_decreases_with_rate() -> None:
    x, ratio, survived = synthetic(120, 2)
    model = Surrogate(PARAMS).fit(x, ratio, survived)
    probe = np.tile(np.array([[0.0, 5.0, 4.0, 1.0, 0.5, 1.0]]), (5, 1))
    probe[:, 0] = np.linspace(0.0, 1.0, 5)
    probability = model.predict(probe)["survival_probability"]
    assert probability[0] > 0.5 > probability[-1]
    assert all(np.diff(probability) <= 1e-9)


def test_save_load_round_trip(tmp_path) -> None:
    x, ratio, survived = synthetic(60, 3)
    model = Surrogate(PARAMS).fit(x, ratio, survived)
    model.save(tmp_path / "model")
    loaded = Surrogate.load(tmp_path / "model")
    first, second = model.predict(x[:7]), loaded.predict(x[:7])
    for key in first:
        np.testing.assert_allclose(first[key], second[key], atol=1e-12)
    assert [p.name for p in loaded.params] == [p.name for p in PARAMS]


def test_saved_model_contains_no_pickle(tmp_path) -> None:
    x, ratio, survived = synthetic(30, 7)
    Surrogate(PARAMS).fit(x, ratio, survived).save(tmp_path / "model")
    files = sorted(path.name for path in (tmp_path / "model").iterdir())
    assert files == ["model.json", "training.npz"]
    with np.load(tmp_path / "model" / "training.npz", allow_pickle=False) as data:
        assert set(data.files) == {"x_unit", "ratio", "survived"}


def test_object_arrays_in_training_file_are_refused(tmp_path) -> None:
    x, ratio, survived = synthetic(30, 8)
    Surrogate(PARAMS).fit(x, ratio, survived).save(tmp_path / "model")
    np.savez(tmp_path / "model" / "training.npz", x_unit=np.array([object()], dtype=object),
             ratio=ratio, survived=survived)
    with pytest.raises(ValueError):
        Surrogate.load(tmp_path / "model")


def test_single_class_is_degenerate_not_crash() -> None:
    x, ratio, _ = synthetic(40, 4)
    model = Surrogate(PARAMS).fit(x, ratio, np.ones(40, dtype=bool))
    assert model.degenerate_survival
    assert np.allclose(model.predict(x[:3])["survival_probability"], 1.0)


def test_in_domain_flags_outside_points() -> None:
    x, ratio, survived = synthetic(40, 5)
    model = Surrogate(PARAMS).fit(x, ratio, survived)
    outside = x[:2].copy()
    outside[1, 1] = 12.0
    assert model.in_domain(outside).tolist() == [True, False]


def test_cross_validate_reports_folds() -> None:
    x, ratio, survived = synthetic(80, 6)
    result = cross_validate(PARAMS, x, ratio, survived, folds=4, seed=0)
    assert len(result["r2_folds"]) == 4
    assert result["r2_mean"] == pytest.approx(np.mean(result["r2_folds"]))
    assert result["auc_mean"] > 0.85
