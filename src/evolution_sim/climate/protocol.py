"""Evolutionary-rescue protocol: configs, replicates, calibration and parallel runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.experiments.scenarios import deep_merge
from evolution_sim.simulation.engine import SimulationEngine

LAG_WINDOW_GENERATIONS = 5.0


class CalibrationExtinct(Exception):
    """Every calibration seed died out with no warming: the climate itself is lethal.

    Deliberately not a RuntimeError, so a crashed worker (BrokenProcessPool) can
    never be mistaken for this biological result.
    """


@dataclass(frozen=True)
class RescuePhases:
    """Protocol lengths in generations: burn-in, warming, hold."""

    burn_in: float = 5.0
    warming: float = 20.0
    hold: float = 5.0

    def to_dict(self) -> dict[str, float]:
        return {"burn_in": self.burn_in, "warming": self.warming, "hold": self.hold}

    @classmethod
    def from_dict(cls, raw: dict[str, float]) -> RescuePhases:
        return cls(float(raw["burn_in"]), float(raw["warming"]), float(raw["hold"]))


@dataclass(frozen=True)
class RescueCondition:
    arm: str
    rate_c_per_gen: float
    seed: int
    breadth_c: float | None = None
    amplitude_c: float | None = None
    founder_sd_c: float | None = None
    segregation_sd_c: float | None = None
    capacity_scale: float = 1.0

    def key(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


def sinusoid_monthly(annual_mean_c: float, amplitude_c: float) -> list[float]:
    """Monthly means whose (max - min) / 2 equals amplitude_c exactly."""
    scale = amplitude_c / math.cos(math.pi / 12)
    return [annual_mean_c + scale * math.sin(2 * math.pi * (month + 0.5) / 12)
            for month in range(12)]


def build_config(base: dict[str, Any], condition: RescueCondition, generation_ticks: int,
                 phases: RescuePhases, *, ticks_per_year: int | None = None,
                 anomaly_knots: list[tuple[float, float]] | None = None,
                 founder_mean_c: float | None = None,
                 monthly_c: list[float] | None = None) -> SimulationConfig:
    if condition.arm not in {"heritable", "none"}:
        raise ValueError("arm must be 'heritable' or 'none'")
    data = json.loads(json.dumps(base))
    climate = data.setdefault("climate", {})
    climate["enabled"] = True
    climate["ticks_per_year"] = int(ticks_per_year or generation_ticks)
    if monthly_c is not None:
        climate["monthly_c"] = list(monthly_c)
    if condition.amplitude_c is not None:
        mean = sum(climate["monthly_c"]) / 12
        climate["monthly_c"] = sinusoid_monthly(mean, condition.amplitude_c)
    if anomaly_knots is None:
        b, w = phases.burn_in, phases.warming
        anomaly_knots = [(0.0, 0.0), (b, 0.0), (b + w, condition.rate_c_per_gen * w)]
    climate["anomaly_c"] = [[float(y), float(v)] for y, v in anomaly_knots]
    climate["inheritance"] = condition.arm
    for field, value in (("tolerance_breadth_c", condition.breadth_c),
                         ("founder_sd_c", condition.founder_sd_c),
                         ("segregation_sd_c", condition.segregation_sd_c),
                         ("founder_mean_c", founder_mean_c)):
        if value is not None:
            climate[field] = float(value)
    if condition.capacity_scale != 1.0:
        scale = condition.capacity_scale
        data = deep_merge(data, {
            "reproduction": {"population_cap": max(
                2, round(data["reproduction"]["population_cap"] * scale))},
            "resources": {
                "spawn_rate": data["resources"]["spawn_rate"] * scale,
                "maximum_count": max(1, round(data["resources"]["maximum_count"] * scale)),
                "initial_count": max(1, round(data["resources"]["initial_count"] * scale)),
            }})
        data["initial_population"] = min(data["initial_population"],
                                         data["reproduction"]["population_cap"])
    return SimulationConfig.from_dict(data)


def _sample(engine: SimulationEngine, generation_ticks: int) -> dict[str, Any]:
    climate = engine.climate
    optima = [item.thermal_optimum for item in engine.creatures.values()]
    stress = [item.thermal_stress for item in engine.creatures.values()]
    year = climate.year(engine.tick)
    return {
        "tick": engine.tick,
        "generation": engine.tick / generation_ticks,
        "population": len(optima),
        "annual_temperature_c": climate.annual_temperature_c(engine.tick),
        "anomaly_c": climate.anomaly_c(year),
        "mean_optimum_c": float(np.mean(optima)) if optima else None,
        "sd_optimum_c": float(np.std(optima)) if optima else None,
        "mean_stress": float(np.mean(stress)) if stress else None,
    }


def _mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return float(np.mean(items)) if items else None


def run_replicate(config: SimulationConfig, seed: int, generation_ticks: int,
                  phases: RescuePhases) -> dict[str, Any]:
    """Run one burn-in / warming / hold replicate and summarise its outcome."""
    if config.climate.ticks_per_year <= 0 or not config.climate.enabled:
        raise ValueError("Rescue replicates require an enabled climate configuration")
    if generation_ticks <= 0:
        raise ValueError("generation_ticks must be positive")
    started = time.perf_counter()
    engine = SimulationEngine(config, seed)
    burn_end = round(phases.burn_in * generation_ticks)
    warm_end = round((phases.burn_in + phases.warming) * generation_ticks)
    total = round((phases.burn_in + phases.warming + phases.hold) * generation_ticks)
    interval = max(1, generation_ticks // 4)
    boundaries = sorted({burn_end, warm_end, total})
    trajectory = [_sample(engine, generation_ticks)]
    errors: list[str] = []
    snapshots: dict[int, dict[str, Any]] = {}
    while engine.tick < total and not engine.extinct:
        target = min(total, (engine.tick // interval + 1) * interval,
                     *(b for b in boundaries if b > engine.tick))
        engine.step(target - engine.tick)
        sample = _sample(engine, generation_ticks)
        trajectory.append(sample)
        if engine.tick in boundaries:
            snapshots[engine.tick] = sample
        if engine.tick % generation_ticks == 0 or engine.extinct or engine.tick == total:
            errors.extend(engine.audit_invariants())
    survived = not engine.extinct
    pre_window = [row["population"] for row in trajectory
                  if phases.burn_in - 1 <= row["generation"] <= phases.burn_in]
    n_pre = _mean(pre_window) or float(trajectory[0]["population"])
    after = [row["population"] for row in trajectory if row["tick"] > burn_end]
    theta0 = snapshots.get(burn_end, {}).get("mean_optimum_c")
    warm_sample = snapshots.get(warm_end)
    shift = (warm_sample["mean_optimum_c"] - theta0
             if warm_sample and theta0 is not None and warm_sample["mean_optimum_c"] is not None
             else None)
    lag = None
    if warm_sample and warm_sample["population"] > 0 and theta0 is not None:
        start = max(phases.burn_in, phases.burn_in + phases.warming - LAG_WINDOW_GENERATIONS)
        lag = _mean(row["anomaly_c"] - (row["mean_optimum_c"] - theta0) for row in trajectory
                    if start <= row["generation"] < phases.burn_in + phases.warming
                    and row["mean_optimum_c"] is not None)
    n_min = min(after) if after else trajectory[-1]["population"]
    n_final = len(engine.creatures)
    return {
        "status": "ok",
        "seed": seed,
        "survived": survived,
        "extinction_generation": None if survived else engine.tick / generation_ticks,
        "n_pre": n_pre,
        "n_min": n_min,
        "n_final": n_final,
        "ratio": n_final / n_pre if n_pre > 0 else 0.0,
        "theta0": theta0,
        "evolved_shift_c": shift,
        "lag_c": lag,
        "rescue_signature": bool(survived and n_min < 0.5 * n_pre and n_final >= 0.8 * n_pre),
        "death_causes": dict(sorted(engine.death_causes.items())),
        "invariant_errors": sorted(set(errors)),
        "ticks": engine.tick,
        "generation_ticks": generation_ticks,
        "elapsed_seconds": time.perf_counter() - started,
        "trajectory": trajectory,
    }


def _calibrate_one(args: tuple[dict[str, Any], int, int, int]) -> tuple[float | None, float]:
    data, seed, burn_in_ticks, measure_ticks = args
    engine = SimulationEngine(SimulationConfig.from_dict(data), seed)
    started = time.perf_counter()
    ticks, depth = [], []
    while engine.tick < burn_in_ticks + measure_ticks and not engine.extinct:
        engine.step(100)
        if engine.tick >= burn_in_ticks and engine.creatures:
            ticks.append(engine.tick)
            depth.append(float(np.mean([engine.lineage.generation_of(key)
                                        for key in engine.creatures])))
    rate = engine.tick / (time.perf_counter() - started)
    if len(ticks) < 3:
        return None, rate  # extinct before measurement
    return float(np.polyfit(ticks, depth, 1)[0]), rate


def calibrate_generation_ticks(base: dict[str, Any], seeds: list[int], *,
                               provisional_ticks_per_year: int = 300,
                               burn_in_ticks: int = 1500, measure_ticks: int = 6000,
                               breadth_c: float | None = None,
                               monthly_c: list[float] | None = None,
                               workers: int = 1) -> dict[str, Any]:
    """Generation interval = 1 / slope of mean living ancestry depth per tick, at rate 0."""
    condition = RescueCondition("heritable", 0.0, 0, breadth_c=breadth_c)
    config = build_config(base, condition, provisional_ticks_per_year, RescuePhases(),
                          anomaly_knots=[], monthly_c=monthly_c).to_dict()
    jobs = [(config, seed, burn_in_ticks, measure_ticks) for seed in seeds]
    if workers > 1:
        with ProcessPoolExecutor(min(workers, len(jobs))) as pool:
            results = list(pool.map(_calibrate_one, jobs))
    else:
        results = [_calibrate_one(job) for job in jobs]
    slopes = [slope for slope, _ in results if slope is not None]
    if not slopes:
        raise CalibrationExtinct(f"0 of {len(seeds)} calibration seeds survived "
                                 f"{burn_in_ticks + measure_ticks} ticks without warming")
    mean_slope = float(np.mean(slopes))
    if mean_slope <= 0:
        raise RuntimeError("Calibration measured no generational turnover")
    return {"generation_ticks": round(1.0 / mean_slope), "slopes": slopes,
            "seeds": list(seeds), "viable_seeds": len(slopes),
            "provisional_ticks_per_year": provisional_ticks_per_year,
            "ticks_per_second": [rate for _, rate in results],
            "burn_in_ticks": burn_in_ticks, "measure_ticks": measure_ticks,
            "breadth_c": breadth_c, "monthly_c": monthly_c}


def _execute(task: dict[str, Any]) -> dict[str, Any]:
    try:
        outcome = run_replicate(SimulationConfig.from_dict(task["config"]), int(task["seed"]),
                                int(task["generation_ticks"]),
                                RescuePhases.from_dict(task["phases"]))
    except Exception as exc:  # recorded, never silently retried
        outcome = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"key": task["key"], "meta": task["meta"],
            "fingerprint": task.get("fingerprint") or task_fingerprint(task), **outcome}


def _load_completed(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows, valid_lines = {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # a partially written line from an interrupted run
        if isinstance(row, dict) and "key" in row:
            rows[row["key"]] = row
            valid_lines.append(line)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("".join(f"{line}\n" for line in valid_lines), encoding="utf-8",
                         newline="\n")
    temporary.replace(path)
    return rows


def run_tasks(tasks: list[dict[str, Any]], results_path: Path, *, workers: int,
              progress: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Run tasks once each, appending rows as they finish; reruns skip finished keys."""
    results_path = Path(results_path)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    keys = [task["key"] for task in tasks]
    if len(set(keys)) != len(keys):
        raise ValueError("task keys must be unique")
    done = _load_completed(results_path)
    for task in tasks:
        row = done.get(task["key"])
        expected = task.get("fingerprint") or task_fingerprint(task)
        if row is not None and row.get("fingerprint") != expected:
            raise ValueError(
                f"{results_path} already holds results for {task['key']} made with different "
                "settings (profile, phases, calibration or climate). Use a new --root, or "
                "delete that file to recompute.")
    pending = [task for task in tasks if task["key"] not in done]
    with results_path.open("a", encoding="utf-8", newline="\n") as stream:
        def record(row: dict[str, Any]) -> None:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            done[row["key"]] = row
            if progress is not None:
                progress(row)

        if workers > 1 and len(pending) > 1:
            with ProcessPoolExecutor(min(workers, len(pending))) as pool:
                futures = [pool.submit(_execute, task) for task in pending]
                for future in as_completed(futures):
                    record(future.result())
        else:
            for task in pending:
                record(_execute(task))
    wanted = set(keys)
    return [done[key] for key in sorted(done) if key in wanted]


def make_task(base: dict[str, Any], condition: RescueCondition, generation_ticks: int,
              phases: RescuePhases, **build_kwargs: Any) -> dict[str, Any]:
    config = build_config(base, condition, generation_ticks, phases, **build_kwargs)
    task = {"key": condition.key(), "config": config.to_dict(), "seed": condition.seed,
            "generation_ticks": generation_ticks, "phases": phases.to_dict(),
            "meta": asdict(condition)}
    task["fingerprint"] = task_fingerprint(task)
    return task


def task_fingerprint(task: dict[str, Any]) -> str:
    """Hash of everything that determines a replicate besides its key."""
    settings = {name: task[name] for name in ("config", "seed", "generation_ticks", "phases")}
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def sweep_tasks(base: dict[str, Any], *, rates: Iterable[float],
                arms: Iterable[str] = ("heritable", "none"), seeds: Iterable[int],
                generation_ticks: int, phases: RescuePhases) -> list[dict[str, Any]]:
    return [make_task(base, RescueCondition(arm, float(rate), int(seed)), generation_ticks,
                      phases)
            for arm in arms for rate in rates for seed in seeds]
