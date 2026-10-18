"""Statistics for rescue sweeps: survival curves, critical rates and criteria."""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from typing import Any

import numpy as np
from scipy import stats
from sklearn.linear_model import LogisticRegression

Z95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def fit_logistic(rates: np.ndarray, survived: np.ndarray) -> tuple[float, float]:
    """Lightly penalised logistic fit (finite under perfect separation)."""
    x = np.asarray(rates, dtype=float)
    y = np.asarray(survived, dtype=int)
    if len(set(y.tolist())) < 2:
        raise ValueError("logistic fit needs both survivors and extinctions")
    scale = float(np.max(np.abs(x))) or 1.0
    model = LogisticRegression(C=10.0, solver="lbfgs", max_iter=1000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit((x / scale).reshape(-1, 1), y)
    return float(model.intercept_[0]), float(model.coef_[0, 0] / scale)


def _ok(rows: list[dict[str, Any]], arm: str | None = None) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("status") == "ok"
            and (arm is None or row["meta"]["arm"] == arm)]


def _by_rate(rows: list[dict[str, Any]]) -> dict[float, list[dict[str, Any]]]:
    grouped: dict[float, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[float(row["meta"]["rate_c_per_gen"])].append(row)
    return {rate: sorted(items, key=lambda r: r["meta"]["seed"])
            for rate, items in sorted(grouped.items())}


def _critical(x: np.ndarray, y: np.ndarray, max_rate: float) -> float | None:
    try:
        b0, b1 = fit_logistic(x, y)
    except ValueError:
        return None
    if b1 >= 0:
        return None
    value = -b0 / b1
    return value if 0.0 <= value <= 2.0 * max_rate else None


def _arrays(groups: dict[float, list[dict[str, Any]]],
            picks: dict[float, np.ndarray] | None = None) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    for rate, items in groups.items():
        chosen = items if picks is None else [items[i] for i in picks[rate]]
        x.extend([rate] * len(chosen))
        y.extend(int(row["survived"]) for row in chosen)
    return np.array(x), np.array(y)


def _percentile_ci(values: list[float]) -> list[float] | None:
    if len(values) < 10:
        return None
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def critical_rate(rows: list[dict[str, Any]], arm: str, *, n_boot: int = 2000,
                  seed: int = 0) -> dict[str, Any]:
    groups = _by_rate(_ok(rows, arm))
    if not groups:
        raise ValueError(f"no completed rows for arm {arm!r}")
    max_rate = max(groups)
    curve = []
    for rate, items in groups.items():
        k = sum(bool(row["survived"]) for row in items)
        low, high = wilson_interval(k, len(items))
        curve.append({"rate": rate, "n": len(items), "survived": k, "p": k / len(items),
                      "wilson_lo": low, "wilson_hi": high})
    x, y = _arrays(groups)
    estimate = _critical(x, y, max_rate)
    try:
        b0, b1 = fit_logistic(x, y)
        logistic = {"b0": b0, "b1": b1}
    except ValueError:
        logistic = None
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        picks = {rate: rng.integers(0, len(items), len(items)) for rate, items in groups.items()}
        value = _critical(*_arrays(groups, picks), max_rate)
        if value is not None:
            boots.append(value)
    return {"arm": arm, "estimate": estimate, "ci95": _percentile_ci(boots),
            "undefined_fraction": 1.0 - len(boots) / n_boot if n_boot else None,
            "curve": curve, "logistic": logistic, "n_boot": n_boot}


def rescue_gain(rows: list[dict[str, Any]], *, n_boot: int = 2000,
                seed: int = 0) -> dict[str, Any]:
    heritable, control = _by_rate(_ok(rows, "heritable")), _by_rate(_ok(rows, "none"))
    rates = sorted(set(heritable) & set(control))
    heritable = {rate: heritable[rate] for rate in rates}
    control = {rate: control[rate] for rate in rates}
    if not rates:
        raise ValueError("rescue gain needs both arms at shared rates")
    max_rate = max(rates)
    first = _critical(*_arrays(heritable), max_rate)
    second = _critical(*_arrays(control), max_rate)
    estimate = first - second if first is not None and second is not None else None
    rng = np.random.default_rng(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        # Paired: the same seed positions are drawn for both arms at every rate.
        picks = {rate: rng.integers(0, min(len(heritable[rate]), len(control[rate])),
                                    min(len(heritable[rate]), len(control[rate])))
                 for rate in rates}
        a = _critical(*_arrays(heritable, picks), max_rate)
        b = _critical(*_arrays(control, picks), max_rate)
        if a is not None and b is not None:
            boots.append(a - b)
    return {"estimate": estimate, "ci95": _percentile_ci(boots),
            "undefined_fraction": 1.0 - len(boots) / n_boot if n_boot else None}


def lag_regression(rows: list[dict[str, Any]], *, arm: str = "heritable",
                   below_rate: float) -> dict[str, Any]:
    points = [(float(row["meta"]["rate_c_per_gen"]), float(row["lag_c"]))
              for row in _ok(rows, arm)
              if row["survived"] and row.get("lag_c") is not None
              and float(row["meta"]["rate_c_per_gen"]) < below_rate]
    if len(points) < 3 or len({rate for rate, _ in points}) < 2:
        return {"slope": None, "intercept": None, "pearson_r": None, "n": len(points)}
    x, y = np.array(points).T
    slope, intercept = np.polyfit(x, y, 1)
    r = float(stats.pearsonr(x, y).statistic) if np.std(y) > 0 else None
    return {"slope": float(slope), "intercept": float(intercept), "pearson_r": r,
            "n": len(points), "below_rate": below_rate}


def signature_frequency(rows: list[dict[str, Any]],
                        arm: str = "heritable") -> list[dict[str, Any]]:
    return [{"rate": rate, "fraction": float(np.mean([bool(r["rescue_signature"])
                                                       for r in items]))}
            for rate, items in _by_rate(_ok(rows, arm)).items()]


def _shift(rows: list[dict[str, Any]], arm: str) -> list[dict[str, Any]]:
    result = []
    for rate, items in _by_rate(_ok(rows, arm)).items():
        shifts = [r["evolved_shift_c"] for r in items if r.get("evolved_shift_c") is not None
                  and r["survived"]]
        result.append({"rate": rate, "mean_shift_c": float(np.mean(shifts)) if shifts else None,
                       "n": len(shifts)})
    return result


def summarize_sweep(rows: list[dict[str, Any]], *, n_boot: int = 2000, seed: int = 0,
                    warming_generations: float = 20.0) -> dict[str, Any]:
    arms = sorted({row["meta"]["arm"] for row in _ok(rows)})
    critical = {arm: critical_rate(rows, arm, n_boot=n_boot, seed=seed) for arm in arms}
    heritable_kc = critical.get("heritable", {}).get("estimate")
    summary = {
        "critical_rate": critical,
        "rescue_gain": (rescue_gain(rows, n_boot=n_boot, seed=seed)
                        if {"heritable", "none"} <= set(arms) else None),
        "lag": (lag_regression(rows, below_rate=heritable_kc)
                if heritable_kc is not None else None),
        "signature": signature_frequency(rows) if "heritable" in arms else [],
        "shift": {arm: _shift(rows, arm) for arm in arms},
        "warming_generations": warming_generations,
        "rows": len(rows),
        "error_rows": sum(row.get("status") != "ok" for row in rows),
        "invariant_error_rows": sum(bool(row.get("invariant_errors")) for row in _ok(rows)),
    }
    summary["criteria"] = sweep_criteria(summary)
    return summary


def _criterion(identifier: str, statement: str, value: Any, threshold: str,
               passed: bool | None) -> dict[str, Any]:
    return {"id": identifier, "statement": statement, "value": value, "threshold": threshold,
            "passed": bool(passed) if passed is not None else False}


def sweep_criteria(summary: dict[str, Any]) -> list[dict[str, Any]]:
    heritable = summary["critical_rate"].get("heritable")
    curve = heritable["curve"] if heritable else []
    baseline = next((point["p"] for point in curve if point["rate"] == 0.0), None)
    rho = None
    if len(curve) >= 3 and len({p["p"] for p in curve}) > 1:
        rho = float(stats.spearmanr([p["rate"] for p in curve],
                                    [p["p"] for p in curve]).statistic)
    gain = summary.get("rescue_gain") or {}
    gain_low = gain["ci95"][0] if gain.get("ci95") else None
    kc = heritable["estimate"] if heritable else None
    shift_ok, shift_value = None, []
    if kc is not None and "none" in summary["shift"]:
        control = {row["rate"]: row for row in summary["shift"]["none"]}
        checks = []
        for row in summary["shift"]["heritable"]:
            rate = row["rate"]
            if not 0 < rate <= kc / 2 or row["mean_shift_c"] is None:
                continue
            warming = rate * summary["warming_generations"]
            other = control.get(rate, {}).get("mean_shift_c")
            enough = row["mean_shift_c"] >= 0.5 * warming
            beats = other is None or row["mean_shift_c"] >= 2 * abs(other)
            checks.append(enough and beats)
            shift_value.append({"rate": rate, "heritable_shift_c": row["mean_shift_c"],
                                "control_shift_c": other, "warming_c": warming})
        shift_ok = bool(checks) and all(checks)
    lag_r = (summary.get("lag") or {}).get("pearson_r")
    integrity = summary["error_rows"] == 0 and summary["invariant_error_rows"] == 0
    return [
        _criterion("C1", "Without warming, heritable populations persist", baseline, "≥ 0.9",
                   baseline is not None and baseline >= 0.9),
        _criterion("C2", "Faster warming lowers survival (Spearman rho)", rho, "≤ -0.8",
                   rho is not None and rho <= -0.8),
        _criterion("C3", "Heritable adaptation raises the critical rate (gain CI low)",
                   gain_low, "> 0", gain_low is not None and gain_low > 0),
        _criterion("C4", "Optima track warming at ≤ k_c/2 (≥ 50 % of ΔT, ≥ 2x control)",
                   shift_value, "all rates pass", shift_ok),
        _criterion("C5", "Adaptation lag grows with warming rate (Pearson r)", lag_r, "≥ 0.8",
                   lag_r is not None and lag_r >= 0.8),
        _criterion("C6", "No invariant violations or failed runs",
                   {"error_rows": summary["error_rows"],
                    "invariant_error_rows": summary["invariant_error_rows"]}, "0 and 0",
                   integrity),
    ]
