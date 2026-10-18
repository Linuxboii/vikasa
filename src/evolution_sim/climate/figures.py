"""Static report figures (PNG bytes) for the climate-rescue evidence package."""

from __future__ import annotations

import io
import math
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Reference categorical slots (validated adjacent pairs), recessive ink and grid.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
ARM_COLOR = {"heritable": SERIES[0], "none": SERIES[1]}
ARM_LABEL = {"heritable": "Heritable tolerance", "none": "Control: no heritability"}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"


def _figure(width: float = 7.2, height: float = 3.8, ncols: int = 1):
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), dpi=150, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes[0]:
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.xaxis.label.set_color(INK)
        ax.yaxis.label.set_color(INK)
    return fig, axes[0]


def _png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buffer.getvalue()


def _legend(ax) -> None:
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)


def survival_curve(summary: dict[str, Any]) -> bytes:
    fig, (ax,) = _figure()
    for arm, result in summary["critical_rate"].items():
        color = ARM_COLOR.get(arm, SERIES[2])
        curve = result["curve"]
        rates = np.array([p["rate"] for p in curve])
        p = np.array([p["p"] for p in curve])
        low = np.clip(p - np.array([q["wilson_lo"] for q in curve]), 0, None)
        high = np.clip(np.array([q["wilson_hi"] for q in curve]) - p, 0, None)
        ax.errorbar(rates, p, yerr=[low, high], fmt="o", ms=5, color=color, capsize=3,
                    lw=1.5, label=f"{ARM_LABEL.get(arm, arm)} (Wilson 95 %)")
        if result.get("logistic"):
            grid = np.linspace(0, rates.max(), 200)
            z = result["logistic"]["b0"] + result["logistic"]["b1"] * grid
            ax.plot(grid, 1 / (1 + np.exp(-z)), color=color, lw=2)
        if result.get("estimate") is not None:
            ax.axvline(result["estimate"], color=color, lw=1, ls="--")
    ax.set_xlabel("Warming rate (°C per generation)")
    ax.set_ylabel("Fraction of seeds surviving")
    ax.set_ylim(-0.05, 1.05)
    _legend(ax)
    return _png(fig)


def shift_vs_rate(summary: dict[str, Any]) -> bytes:
    fig, (ax,) = _figure()
    warming_generations = summary.get("warming_generations", 20.0)
    top = 0.0
    for arm, rows in summary["shift"].items():
        points = [(r["rate"], r["mean_shift_c"]) for r in rows if r["mean_shift_c"] is not None]
        if points:
            x, y = np.array(points).T
            top = max(top, x.max())
            ax.plot(x, y, "-o", ms=5, lw=2, color=ARM_COLOR.get(arm, SERIES[2]),
                    label=ARM_LABEL.get(arm, arm))
    grid = np.linspace(0, top or 1, 50)
    ax.plot(grid, grid * warming_generations, color=MUTED, lw=1, ls=":",
            label="Total warming (perfect tracking)")
    ax.set_xlabel("Warming rate (°C per generation)")
    ax.set_ylabel("Shift in mean thermal optimum (°C)")
    _legend(ax)
    return _png(fig)


def lag_vs_rate(summary: dict[str, Any], rows: list[dict[str, Any]]) -> bytes:
    fig, (ax,) = _figure()
    points = [(r["meta"]["rate_c_per_gen"], r["lag_c"]) for r in rows
              if r.get("status") == "ok" and r["meta"]["arm"] == "heritable" and r["survived"]
              and r.get("lag_c") is not None]
    if points:
        x, y = np.array(points).T
        ax.scatter(x, y, s=28, color=SERIES[0], edgecolor=SURFACE, linewidth=1,
                   label="Surviving heritable runs")
    lag = summary.get("lag") or {}
    if lag.get("slope") is not None and points:
        grid = np.linspace(0, max(x), 50)
        ax.plot(grid, lag["intercept"] + lag["slope"] * grid, color=INK, lw=1.5,
                label=f"Linear fit (r = {lag['pearson_r']:.2f})" if lag.get("pearson_r")
                is not None else "Linear fit")
    ax.set_xlabel("Warming rate (°C per generation)")
    ax.set_ylabel("Adaptation lag (°C behind optimum)")
    _legend(ax)
    return _png(fig)


def trajectories(rows: list[dict[str, Any]], rates: list[float]) -> bytes:
    fig, (left, right) = _figure(width=9.0, ncols=2)
    for index, rate in enumerate(rates[:4]):
        chosen = sorted((r for r in rows if r.get("status") == "ok"
                         and r["meta"]["arm"] == "heritable"
                         and r["meta"]["rate_c_per_gen"] == rate and r.get("trajectory")),
                        key=lambda r: r["meta"]["seed"])
        if not chosen:
            continue
        run = chosen[0]
        generation = [p["generation"] for p in run["trajectory"]]
        population = [p["population"] / max(run["n_pre"], 1e-9) for p in run["trajectory"]]
        lag = [p["anomaly_c"] - (p["mean_optimum_c"] - run["trajectory"][0]["mean_optimum_c"])
               if p.get("mean_optimum_c") is not None and run["trajectory"][0].get(
                   "mean_optimum_c") is not None else math.nan for p in run["trajectory"]]
        color = SERIES[index]
        left.plot(generation, population, color=color, lw=2, label=f"{rate:g} °C/gen")
        right.plot(generation, lag, color=color, lw=2, label=f"{rate:g} °C/gen")
    left.set_xlabel("Generation")
    left.set_ylabel("Population ÷ pre-warming size")
    left.set_ylim(bottom=0)
    right.set_xlabel("Generation")
    right.set_ylabel("Lag behind warming (°C)")
    _legend(left)
    return _png(fig)


def sobol_bars(names: list[str], indices: dict[str, Any]) -> bytes:
    fig, (ax,) = _figure(height=3.6)
    y = np.arange(len(names))
    for offset, key, color, label in ((-0.18, "S1", SERIES[0], "First-order S1"),
                                      (0.18, "ST", SERIES[1], "Total-order ST")):
        values = np.array(indices[key])
        ci = np.array(indices[f"{key}_ci"], dtype=float)
        error = np.vstack([np.clip(values - ci[:, 0], 0, None),
                           np.clip(ci[:, 1] - values, 0, None)])
        ax.barh(y + offset, values, height=0.34, color=color, label=label, xerr=error,
                error_kw={"ecolor": MUTED, "lw": 1, "capsize": 2})
    ax.set_yticks(y, [name.replace("_", " ") for name in names])
    ax.invert_yaxis()
    ax.set_xlabel("Share of outcome variance explained")
    _legend(ax)
    return _png(fig)


def surrogate_parity(validation: dict[str, Any]) -> bytes:
    fig, (ax,) = _figure(width=4.6, height=4.2)
    holdout = validation["holdout"]
    observed, predicted = holdout["observed_ratio"], holdout["predicted_ratio"]
    ax.errorbar(observed, predicted, yerr=holdout.get("predicted_sd"), fmt="o", ms=5,
                color=SERIES[0], ecolor=GRID, capsize=0, label="Held-out simulations")
    top = max([*observed, *predicted, 1.0]) * 1.05
    ax.plot([0, top], [0, top], color=MUTED, lw=1, ls=":", label="Perfect prediction")
    ax.set_xlabel("Simulated population ratio")
    ax.set_ylabel("Surrogate prediction")
    _legend(ax)
    return _png(fig)


def assessment_panel(assessment: dict[str, Any]) -> bytes:
    fig, (ax,) = _figure(height=3.4)
    entries = assessment["ssps"]
    x = np.arange(len(entries))
    p = np.array([e["direct"]["p"] if e["direct"]["p"] is not None else np.nan for e in entries])
    low = np.clip(p - np.array([e["direct"]["wilson"][0] for e in entries]), 0, None)
    high = np.clip(np.array([e["direct"]["wilson"][1] for e in entries]) - p, 0, None)
    ax.errorbar(x, p, yerr=[low, high], fmt="o", ms=7, color=SERIES[0], capsize=4, lw=1.5,
                label="Direct simulation (Wilson 95 %)")
    for key, color, marker, label in (("surrogate", SERIES[2], "D", "Surrogate"),
                                      ("sweep", SERIES[3], "s", "Reference sweep curve")):
        values = [(i, e[key]["p"]) for i, e in enumerate(entries)
                  if isinstance(e.get(key), dict) and "p" in e[key]]
        if values:
            xi, yi = np.array(values).T
            ax.scatter(xi + 0.12, yi, marker=marker, s=40, color=color, label=label,
                       edgecolor=SURFACE, linewidth=1, zorder=3)
    for threshold in (0.2, 0.8):
        ax.axhline(threshold, color=GRID, lw=1, ls="--")
    ax.set_xticks(x, [e["ssp"] for e in entries])
    ax.set_ylim(-0.05, 1.05)
    ax.set_ylabel("Survival probability to end of run")
    _legend(ax)
    return _png(fig)


def build_figures(context: dict[str, Any]) -> dict[str, bytes]:
    figures: dict[str, bytes] = {}
    sweep = context.get("sweep")
    if sweep:
        summary, rows = sweep["summary"], sweep.get("rows", [])
        figures["survival_curve"] = survival_curve(summary)
        figures["shift_vs_rate"] = shift_vs_rate(summary)
        figures["lag_vs_rate"] = lag_vs_rate(summary, rows)
        heritable = summary["critical_rate"].get("heritable")
        if heritable and rows:
            rates = [p["rate"] for p in heritable["curve"]]
            kc = heritable.get("estimate") or max(rates)
            # Representative rates: none, slow, near-critical, beyond critical.
            picks = sorted({min(rates, key=lambda r, t=t: abs(r - t))
                            for t in (0.0, kc / 3, kc * 0.8, kc * 1.3)})
            figures["trajectories"] = trajectories(rows, picks)
    sensitivity = context.get("sensitivity")
    if sensitivity:
        figures["sobol_bars"] = sobol_bars(sensitivity["names"],
                                           sensitivity["sobol"]["survival"])
    validation = context.get("surrogate_validation")
    if validation and validation.get("holdout", {}).get("observed_ratio"):
        figures["surrogate_parity"] = surrogate_parity(validation)
    for assessment in context.get("assessments") or []:
        figures[f"assessment_{assessment['request']['region']}"] = assessment_panel(assessment)
    return figures
