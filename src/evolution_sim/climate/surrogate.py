"""Gaussian-process emulator of rescue outcomes over the sensitivity parameters."""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.metrics import accuracy_score, brier_score_loss, r2_score, roc_auc_score
from sklearn.model_selection import KFold

from evolution_sim.climate.sensitivity import Parameter, unscale

RATIO_CLIP = (0.0, 2.0)


class Surrogate:
    """GP regression of the final/pre-warming population ratio.

    Survival probability is P(ratio > tau) under the GP predictive normal, with
    tau learned from training data as the midpoint between the largest extinct
    ratio and the smallest surviving ratio. One model keeps the two outputs
    consistent and extrapolates the fitted trend at sparse domain edges, where a
    GP classifier's latent reverts toward p = 0.5.
    """

    def __init__(self, params: tuple[Parameter, ...], seed: int = 0) -> None:
        self.params = tuple(params)
        self.seed = seed
        self.regressor: GaussianProcessRegressor | None = None
        self.threshold = 0.5
        self.degenerate_survival = False
        self.constant_probability: float | None = None
        self.n = 0

    def _unit(self, x: np.ndarray) -> np.ndarray:
        x = np.atleast_2d(np.asarray(x, dtype=float))
        if x.shape[1] != len(self.params):
            raise ValueError(f"expected {len(self.params)} input columns, got {x.shape[1]}")
        return unscale(x, self.params)

    def fit(self, x: np.ndarray, ratio: np.ndarray, survived: np.ndarray) -> Surrogate:
        unit = self._unit(x)
        d = unit.shape[1]
        target = np.clip(np.asarray(ratio, dtype=float), *RATIO_CLIP)
        labels = np.asarray(survived, dtype=int)
        self.regressor = GaussianProcessRegressor(
            kernel=ConstantKernel(1.0) * Matern(length_scale=[0.3] * d, nu=2.5)
            + WhiteKernel(0.01),
            normalize_y=True, n_restarts_optimizer=3, random_state=self.seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.regressor.fit(unit, target)
        alive, dead = target[labels == 1], target[labels == 0]
        self.degenerate_survival = len(alive) == 0 or len(dead) == 0
        if self.degenerate_survival:
            self.constant_probability = float(labels[0])
        else:
            self.constant_probability = None
            self.threshold = float(np.clip((dead.max() + alive.min()) / 2, 0.05, 0.5))
        self.n = len(target)
        return self

    def predict(self, x: np.ndarray) -> dict[str, np.ndarray]:
        if self.regressor is None:
            raise ValueError("Surrogate has not been fitted")
        unit = self._unit(x)
        mean, sd = self.regressor.predict(unit, return_std=True)
        if self.degenerate_survival:
            probability = np.full(len(unit), float(self.constant_probability))
        else:
            probability = norm.cdf((mean - self.threshold) / np.maximum(sd, 1e-9))
        return {"ratio_mean": np.clip(mean, *RATIO_CLIP), "ratio_sd": sd,
                "survival_probability": probability}

    def in_domain(self, x: np.ndarray) -> np.ndarray:
        unit = self._unit(x)
        return np.all((unit >= -1e-9) & (unit <= 1 + 1e-9), axis=1)

    def save(self, directory: Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump({"regressor": self.regressor},
                    directory / "model.joblib")
        digest = hashlib.sha256((directory / "model.joblib").read_bytes()).hexdigest()
        metadata = {"model_sha256": digest, "params": [asdict(p) for p in self.params],
                    "seed": self.seed,
                    "n": self.n, "degenerate_survival": self.degenerate_survival,
                    "threshold": self.threshold,
                    "constant_probability": self.constant_probability,
                    "regressor_kernel": str(self.regressor.kernel_),
                    "sklearn": sklearn.__version__}
        (directory / "model.json").write_text(json.dumps(metadata, indent=2, sort_keys=True)
                                              + "\n", encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> Surrogate:
        directory = Path(directory)
        metadata = json.loads((directory / "model.json").read_text(encoding="utf-8"))
        # joblib unpickles, which can execute code: only load models this tool wrote.
        # The recorded hash catches accidental replacement or corruption of the file.
        digest = hashlib.sha256((directory / "model.joblib").read_bytes()).hexdigest()
        if digest != metadata.get("model_sha256"):
            raise ValueError(f"Surrogate model file hash mismatch in {directory}; refusing to load")
        model = cls(tuple(Parameter(**p) for p in metadata["params"]), metadata["seed"])
        models = joblib.load(directory / "model.joblib")
        model.regressor = models["regressor"]
        model.degenerate_survival = metadata["degenerate_survival"]
        model.threshold = metadata["threshold"]
        model.constant_probability = metadata["constant_probability"]
        model.n = metadata["n"]
        return model


def _auc(labels: np.ndarray, probability: np.ndarray) -> float | None:
    return float(roc_auc_score(labels, probability)) if len(set(labels.tolist())) > 1 else None


def holdout_metrics(model: Surrogate, x: np.ndarray, ratio: np.ndarray,
                    survived: np.ndarray) -> dict[str, Any]:
    prediction = model.predict(x)
    labels = np.asarray(survived, dtype=int)
    target = np.clip(np.asarray(ratio, dtype=float), *RATIO_CLIP)
    probability = prediction["survival_probability"]
    return {"r2": float(r2_score(target, prediction["ratio_mean"])),
            "auc": _auc(labels, probability),
            "accuracy": float(accuracy_score(labels, probability >= 0.5)),
            "brier": float(brier_score_loss(labels, probability, labels=[0, 1])),
            "n": len(target),
            "observed_ratio": target.tolist(),
            "predicted_ratio": prediction["ratio_mean"].tolist(),
            "predicted_sd": prediction["ratio_sd"].tolist()}


def cross_validate(params: tuple[Parameter, ...], x: np.ndarray, ratio: np.ndarray,
                   survived: np.ndarray, *, folds: int = 5, seed: int = 0) -> dict[str, Any]:
    x, ratio, survived = np.asarray(x), np.asarray(ratio), np.asarray(survived)
    r2_folds, auc_folds = [], []
    for train, test in KFold(folds, shuffle=True, random_state=seed).split(x):
        model = Surrogate(params, seed).fit(x[train], ratio[train], survived[train])
        metrics = holdout_metrics(model, x[test], ratio[test], survived[test])
        r2_folds.append(metrics["r2"])
        auc_folds.append(metrics["auc"])
    valid_auc = [value for value in auc_folds if value is not None]
    return {"r2_folds": r2_folds, "r2_mean": float(np.mean(r2_folds)),
            "auc_folds": auc_folds,
            "auc_mean": float(np.mean(valid_auc)) if valid_auc else None}
