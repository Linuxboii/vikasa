"""Publication-quality static experiment charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from evolution_sim.analytics.metrics import MetricsRecorder
from evolution_sim.model.genome import TRAITS
from evolution_sim.simulation.engine import SimulationEngine

BACKGROUND = "#08101e"
PANEL = "#101c2f"
TEXT = "#dce9f5"
CYAN = "#4de4e8"
AMBER = "#ffbd66"
MAGENTA = "#d980fa"
GRID = "#27405a"


def _style(axis: plt.Axes, title: str) -> None:
    axis.set_facecolor(PANEL)
    axis.set_title(title, color=TEXT, fontsize=13, loc="left", fontweight="bold")
    axis.tick_params(colors="#9ab2c8")
    axis.grid(color=GRID, alpha=0.35, linewidth=0.7)
    for spine in axis.spines.values():
        spine.set_color(GRID)


def _save(figure: plt.Figure, path: Path) -> Path:
    figure.patch.set_facecolor(BACKGROUND)
    figure.tight_layout()
    figure.savefig(path, dpi=150, facecolor=BACKGROUND, bbox_inches="tight")
    plt.close(figure)
    return path


def _rows(engine: SimulationEngine) -> list[dict]:
    if engine.metrics.samples:
        return engine.metrics.rows()
    recorder = MetricsRecorder()
    recorder.record(engine)
    return recorder.rows()


def export_charts(engine: SimulationEngine, directory: str | Path) -> tuple[Path, ...]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    rows = _rows(engine)
    ticks = [row["tick"] for row in rows]

    figure, axis = plt.subplots(figsize=(10, 4.6))
    _style(axis, "Population and resources")
    axis.plot(ticks, [row["population"] for row in rows], color=CYAN, label="Population")
    axis.plot(ticks, [row["food"] for row in rows], color=AMBER, label="Food", alpha=0.85)
    axis.set_xlabel("Simulation tick", color=TEXT)
    axis.set_ylabel("Count", color=TEXT)
    axis.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    population_path = _save(figure, root / "population.png")

    figure, axis = plt.subplots(figsize=(10, 5.2))
    _style(axis, "Mean inheritable traits (normalized)")
    colors = [CYAN, AMBER, MAGENTA, "#7ee787", "#8ab4f8", "#f28b82"]
    for trait, color in zip(TRAITS, colors, strict=True):
        bounds = engine.config.genome.traits[trait.value]
        span = bounds.maximum - bounds.minimum
        values = [(row[f"{trait.value}_mean"] - bounds.minimum) / span for row in rows]
        axis.plot(ticks, values, label=trait.value.replace("_", " ").title(), color=color)
    axis.set_ylim(0, 1)
    axis.set_xlabel("Simulation tick", color=TEXT)
    axis.set_ylabel("Normalized mean", color=TEXT)
    axis.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, ncol=2)
    traits_path = _save(figure, root / "traits.png")

    figure, axis = plt.subplots(figsize=(10, 4.6))
    _style(axis, "Births and deaths per sample")
    axis.plot(ticks, [row["births"] for row in rows], color=CYAN, label="Births")
    axis.plot(ticks, [row["deaths"] for row in rows], color="#f28b82", label="Deaths")
    axis.fill_between(ticks, [row["births"] for row in rows], color=CYAN, alpha=0.12)
    axis.fill_between(ticks, [row["deaths"] for row in rows], color="#f28b82", alpha=0.12)
    axis.set_xlabel("Simulation tick", color=TEXT)
    axis.set_ylabel("Events", color=TEXT)
    axis.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT)
    vital_path = _save(figure, root / "births_deaths.png")

    figure, axes = plt.subplots(2, 3, figsize=(11, 6.5))
    figure.suptitle("Final trait distributions", color=TEXT, fontsize=15, fontweight="bold")
    for axis, trait, color in zip(axes.flat, TRAITS, colors, strict=True):
        _style(axis, trait.value.replace("_", " ").title())
        values = [
            creature.genome[trait]
            for creature in (engine.creatures[key] for key in sorted(engine.creatures))
        ]
        if values:
            bins = min(18, max(5, round(np.sqrt(len(values)))))
            axis.hist(values, bins=bins, color=color, alpha=0.85, edgecolor=BACKGROUND)
        else:
            axis.text(0.5, 0.5, "Population extinct", color=TEXT, ha="center", va="center")
        axis.set_ylabel("Creatures", color=TEXT)
    distributions_path = _save(figure, root / "distributions.png")
    return population_path, traits_path, vital_path, distributions_path

