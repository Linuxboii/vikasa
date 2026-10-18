"""Regional SSP assessment: can a population with given biology keep up locally?"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.climate.analysis import wilson_interval
from evolution_sim.climate.data import (
    SSP_SOURCE,
    SSP_WARMING,
    RegionClimate,
    ssp_anomaly_c,
    ssp_rate_c_per_year,
)
from evolution_sim.climate.protocol import (
    CalibrationExtinct,
    RescueCondition,
    RescuePhases,
    calibrate_generation_ticks,
    make_task,
    run_tasks,
)
from evolution_sim.climate.surrogate import Surrogate

DOMAIN_TOLERANCE = 0.25
CALIBRATION_SEEDS = (101, 102, 103, 104)
BIOLOGY_DISCLAIMER = ("Climate forcing is observed data; the organism is a generic model, "
                      "not a calibrated real species.")


@dataclass(frozen=True)
class AssessmentRequest:
    region: RegionClimate
    generation_years: float
    breadth_c: float
    ssps: tuple[str, ...]
    regional_factor: float = 1.0
    seeds: tuple[int, ...] = field(default_factory=lambda: tuple(range(12)))
    start_year: int = 2025
    end_year: int = 2100
    max_warming_generations: float = 40.0
    founder_sd_c: float | None = None
    segregation_sd_c: float | None = None
    burn_in_generations: float = 5.0
    hold_generations: float = 5.0

    def __post_init__(self) -> None:
        if not 0.05 <= self.generation_years <= 50:
            raise ValueError("generation_years must be between 0.05 and 50")
        if not 0.1 <= self.breadth_c <= 50:
            raise ValueError("breadth_c must be between 0.1 and 50 °C")
        if not self.ssps:
            raise ValueError("at least one SSP is required")
        for ssp in self.ssps:
            if ssp not in SSP_WARMING:
                raise ValueError(f"Unknown SSP {ssp!r}; use one of {', '.join(SSP_WARMING)}")
        if not 0 < self.regional_factor <= 5:
            raise ValueError("regional_factor must be in (0, 5]")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be non-empty and unique")
        if self.end_year <= self.start_year:
            raise ValueError("end_year must be after start_year")
        if self.max_warming_generations <= 0:
            raise ValueError("max_warming_generations must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {"region": self.region.key, "region_name": self.region.name,
                "generation_years": self.generation_years, "breadth_c": self.breadth_c,
                "ssps": list(self.ssps), "regional_factor": self.regional_factor,
                "seeds": list(self.seeds), "start_year": self.start_year,
                "end_year": self.end_year,
                "max_warming_generations": self.max_warming_generations,
                "founder_sd_c": self.founder_sd_c, "segregation_sd_c": self.segregation_sd_c}


def verdict(p: float) -> str:
    if p >= 0.8:
        return "likely persists"
    if p >= 0.2:
        return "at risk"
    return "likely lost"


def plan_ssp(request: AssessmentRequest, ssp: str, generation_ticks: int) -> dict[str, Any]:
    g = request.generation_years
    rate = ssp_rate_c_per_year(ssp, request.regional_factor)
    start = ssp_anomaly_c(ssp, request.start_year, request.regional_factor)
    full_span = request.end_year - request.start_year
    span = min(full_span, request.max_warming_generations * g)
    burn_years = request.burn_in_generations * g
    return {
        "ssp": ssp, "rate_c_per_year": rate, "rate_c_per_generation": rate * g,
        "start_anomaly_c": start, "span_years": span, "truncated": span < full_span,
        "simulated_end_year": request.start_year + span,
        "ticks_per_year": max(4, round(generation_ticks / g)),
        "knots": [(0.0, start), (burn_years, start), (burn_years + span, start + rate * span)],
        "phases": RescuePhases(request.burn_in_generations, span / g,
                               request.hold_generations).to_dict(),
        "founder_mean_c": request.region.annual_mean_c + start,
        "warming_c": rate * span,
    }


def _in_sweep_domain(request: AssessmentRequest, domain: dict[str, float], rate: float,
                     founder_sd: float, segregation_sd: float) -> bool:
    """The sweep curve applies only to conditions like the ones it was measured in."""
    if not (abs(request.region.seasonal_amplitude_c - domain["amplitude_c"])
            <= DOMAIN_TOLERANCE * domain["amplitude_c"]
            and abs(request.breadth_c - domain["breadth_c"])
            <= DOMAIN_TOLERANCE * domain["breadth_c"]):
        return False
    if "max_rate" in domain and not 0.0 <= rate <= domain["max_rate"]:
        return False
    return all(math.isclose(value, domain[key]) for key, value in
               (("founder_sd_c", founder_sd), ("segregation_sd_c", segregation_sd))
               if key in domain)


def _cached_calibration(path: Path, base: dict[str, Any], request: AssessmentRequest,
                        workers: int, options: dict[str, Any]) -> dict[str, Any]:
    """Re-measure the generation interval for this region and breadth, once.

    Calibration runs on the assessment's own seasonal clock: one reference
    generation spans generation_years climate years.
    """
    reference = options.get("reference_generation_ticks")
    settings = {"seeds": list(options.get("seeds", CALIBRATION_SEEDS)),
                "burn_in_ticks": int(options.get("burn_in_ticks", 1500)),
                "measure_ticks": int(options.get("measure_ticks", 6000)),
                "provisional_ticks_per_year": (max(4, round(reference / request.generation_years))
                                               if reference else 300)}
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        same_climate = (cached.get("breadth_c") == request.breadth_c
                        and cached.get("monthly_c") == list(request.region.monthly_c))
        if same_climate and "provisional_ticks_per_year" not in cached:
            # Written before calibration followed the assessment's seasonal clock;
            # reused so finished assessments stay valid, and flagged in the result.
            return {**cached, "legacy": True}
        if same_climate and all(cached.get(key) == value for key, value in settings.items()):
            return cached
    calibration = calibrate_generation_ticks(
        base, settings["seeds"], breadth_c=request.breadth_c,
        monthly_c=list(request.region.monthly_c), workers=min(len(settings["seeds"]), workers),
        burn_in_ticks=settings["burn_in_ticks"], measure_ticks=settings["measure_ticks"],
        provisional_ticks_per_year=settings["provisional_ticks_per_year"])
    _write_json_atomic(path, calibration)
    return calibration


BASELINE_FAILURE_VERDICT = "not viable in present-day climate"


def _write_json_atomic(target: Path, value: dict[str, Any]) -> None:
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(target)


def _write_assessment(results_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    _write_json_atomic(results_dir / "assessment.json", result)
    return result


def _identity(request: AssessmentRequest, assessment_id: str | None,
              label: str | None) -> dict[str, Any]:
    return {"id": assessment_id or request.region.key,
            "label": label or f"{request.region.name}: tolerance breadth "
                              f"{request.breadth_c:g} °C"}


def _baseline_failure(request: AssessmentRequest, results_dir: Path, reason: str,
                      identity: dict[str, Any], seeds: int) -> dict[str, Any]:
    entries = []
    for ssp in request.ssps:
        plan = plan_ssp(request, ssp, generation_ticks=1)
        entries.append({"ssp": ssp, "plan": plan,
                        "direct": {"survived": 0, "n": 0, "p": None, "wilson": [0.0, 1.0],
                                   "errors": 0, "mean_ratio": None},
                        "verdict": BASELINE_FAILURE_VERDICT,
                        "observed_trend_c_per_decade": request.region.trend_c_per_decade,
                        "sweep": None, "surrogate": None})
    caveats = [BIOLOGY_DISCLAIMER,
               f"With a tolerance breadth of {request.breadth_c:g} °C, 0 of {seeds} populations "
               f"survived the region's present-day seasonal cycle (seasonal amplitude "
               f"{request.region.seasonal_amplitude_c:.1f} °C) with no warming at all, so no "
               "warming scenario was simulated. Try a broader tolerance breadth.",
               f"Calibration detail: {reason}"]
    return _write_assessment(results_dir, {
        "schema": "vikasa-climate-assessment-v1", **identity, "request": request.to_dict(),
        "calibration": None, "baseline_viable": False,
        "baseline_viability": {"survived": 0, "n": seeds}, "ssps": entries,
        "caveats": caveats})


def assess(request: AssessmentRequest, base: dict[str, Any], *, results_dir: Path,
           workers: int, sweep_summary: dict[str, Any] | None = None,
           sweep_domain: dict[str, float] | None = None, surrogate: Surrogate | None = None,
           calibration_override: dict[str, Any] | None = None,
           calibration_kwargs: dict[str, Any] | None = None, assessment_id: str | None = None,
           label: str | None = None) -> dict[str, Any]:
    identity = _identity(request, assessment_id, label)
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    try:
        calibration = calibration_override or _cached_calibration(
            results_dir / "calibration.json", base, request, workers, calibration_kwargs or {})
    except CalibrationExtinct as exc:
        # Every population died under today's seasonal cycle with zero warming:
        # a real answer for this region and tolerance, not a tool failure.
        seeds = len((calibration_kwargs or {}).get("seeds", CALIBRATION_SEEDS))
        return _baseline_failure(request, results_dir, str(exc), identity, seeds)
    generation_ticks = int(calibration["generation_ticks"])
    climate = base.get("climate", {})
    founder_sd = request.founder_sd_c if request.founder_sd_c is not None else float(
        climate.get("founder_sd_c", 1.0))
    segregation_sd = (request.segregation_sd_c if request.segregation_sd_c is not None
                      else float(climate.get("segregation_sd_c", 0.4)))
    plans = {ssp: plan_ssp(request, ssp, generation_ticks) for ssp in request.ssps}
    tasks = []
    for ssp, plan in plans.items():
        for seed in request.seeds:
            condition = RescueCondition("heritable", plan["rate_c_per_generation"], seed,
                                        breadth_c=request.breadth_c, founder_sd_c=founder_sd,
                                        segregation_sd_c=segregation_sd)
            task = make_task(base, condition, generation_ticks,
                             RescuePhases.from_dict(plan["phases"]),
                             ticks_per_year=plan["ticks_per_year"],
                             anomaly_knots=plan["knots"], founder_mean_c=plan["founder_mean_c"],
                             monthly_c=list(request.region.monthly_c))
            task["key"] = f"{request.region.key}|{ssp}|{task['key']}"
            task["meta"] = {**task["meta"], "ssp": ssp, "region": request.region.key}
            tasks.append(task)
    rows = run_tasks(tasks, results_dir / "results.jsonl", workers=workers)
    logistic = (((sweep_summary or {}).get("critical_rate") or {}).get("heritable") or {}).get(
        "logistic")
    entries = []
    for ssp, plan in plans.items():
        mine = [row for row in rows if row["meta"].get("ssp") == ssp]
        ok = [row for row in mine if row.get("status") == "ok"]
        survived = sum(bool(row["survived"]) for row in ok)
        p = survived / len(ok) if ok else float("nan")
        entry = {"ssp": ssp, "plan": plan,
                 "direct": {"survived": survived, "n": len(ok), "p": p if ok else None,
                            "wilson": list(wilson_interval(survived, len(ok))),
                            "errors": len(mine) - len(ok),
                            "mean_ratio": (float(np.mean([r["ratio"] for r in ok]))
                                           if ok else None)},
                 "verdict": verdict(p) if ok else "no completed runs",
                 "observed_trend_c_per_decade": request.region.trend_c_per_decade,
                 "sweep": None, "surrogate": None}
        if logistic and sweep_domain:
            if _in_sweep_domain(request, sweep_domain, plan["rate_c_per_generation"],
                                founder_sd, segregation_sd):
                z = logistic["b0"] + logistic["b1"] * plan["rate_c_per_generation"]
                entry["sweep"] = {"p": 1.0 / (1.0 + math.exp(-z))}
            else:
                entry["sweep"] = {"status": "outside sweep domain"}
        if surrogate is not None:
            x = np.array([[plan["rate_c_per_generation"], request.breadth_c,
                           request.region.seasonal_amplitude_c, founder_sd, segregation_sd,
                           1.0]])
            if bool(surrogate.in_domain(x)[0]):
                prediction = surrogate.predict(x)
                entry["surrogate"] = {"p": float(prediction["survival_probability"][0]),
                                      "ratio_mean": float(prediction["ratio_mean"][0]),
                                      "ratio_sd": float(prediction["ratio_sd"][0])}
            else:
                entry["surrogate"] = {"status": "outside surrogate domain"}
        entries.append(entry)
    caveats = [BIOLOGY_DISCLAIMER,
               f"Warming pathway: {SSP_SOURCE}; regional factor {request.regional_factor:g}.",
               "Direct simulation is authoritative; sweep and surrogate values are references "
               "from the fixed 20-generation protocol."]
    if calibration.get("legacy"):
        caveats.append("Generation interval reused from an earlier calibration run on a "
                       "300-ticks-per-year seasonal clock and 2 seeds, not this assessment's "
                       "own clock.")
    if any(plan["truncated"] for plan in plans.values()):
        caveats.append(f"Warming capped at {request.max_warming_generations:g} generations: "
                       "only the first part of the 2025-2100 pathway was simulated.")
    return _write_assessment(results_dir, {
        "schema": "vikasa-climate-assessment-v1", **identity, "request": request.to_dict(),
        "calibration": calibration, "calibration_legacy": bool(calibration.get("legacy")),
        "baseline_viable": True,
        "baseline_viability": {"survived": calibration.get(
                                   "viable_seeds", len(calibration.get("seeds", []))),
                               "n": len(calibration.get("seeds", []))},
        "ssps": entries, "caveats": caveats})
