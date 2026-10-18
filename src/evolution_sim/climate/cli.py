"""`vikasa climate ...`: fetch data, run the rescue pipeline and render its report."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from evolution_sim.climate.analysis import summarize_sweep
from evolution_sim.climate.assess import AssessmentRequest, assess
from evolution_sim.climate.data import (
    BUNDLED_REGIONS,
    POWER_URL,
    SSP_SOURCE,
    SSP_WARMING,
    fetch_power_monthly,
    region_from_power,
    resolve_region,
    save_region,
)
from evolution_sim.climate.protocol import (
    RescuePhases,
    calibrate_generation_ticks,
    make_task,
    run_tasks,
    sweep_tasks,
)
from evolution_sim.climate.sensitivity import (
    design_conditions,
    latin_hypercube,
    parameters,
    scale,
    sobol_indices,
)
from evolution_sim.climate.surrogate import Surrogate, cross_validate, holdout_metrics
from evolution_sim.config import ConfigError

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = ROOT / "config" / "climate-rescue.json"

PROFILES: dict[str, dict[str, Any]] = {
    "quick": {
        "rates": (0.0, 0.3, 1.2), "seeds": 3,
        "phases": {"burn_in": 2.0, "warming": 4.0, "hold": 2.0},
        "calibration": {"seeds": [901], "burn_in_ticks": 500, "measure_ticks": 1500},
        "design_points": 24, "holdout_points": 8, "sobol_n": 1024, "n_boot": 200,
        "regions": ("western-ghats",), "ssps": ("SSP2-4.5", "SSP5-8.5"),
        "assess_seeds": 3, "generation_years": 1.0, "breadth_c": 4.0,
        "max_warming_generations": 4.0,
    },
    "full": {
        "rates": (0.0, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4), "seeds": 12,
        "phases": {"burn_in": 5.0, "warming": 20.0, "hold": 5.0},
        "calibration": {"seeds": [901, 902, 903], "burn_in_ticks": 1500,
                        "measure_ticks": 6000},
        "design_points": 192, "holdout_points": 48, "sobol_n": 4096, "n_boot": 2000,
        "regions": tuple(BUNDLED_REGIONS), "ssps": tuple(SSP_WARMING),
        "assess_seeds": 12, "generation_years": 1.0, "breadth_c": 4.0,
        "max_warming_generations": 40.0,
    },
}
DESIGN_SEED, HOLDOUT_SEED = 2026, 2027
DESIGN_SEED0, HOLDOUT_SEED0 = 10_000, 20_000


class _Progress:
    def __init__(self, stage: str, total: int) -> None:
        self.stage, self.total, self.done = stage, total, 0

    def __call__(self, row: dict[str, Any]) -> None:
        self.done += 1
        meta = row.get("meta", {})
        status = ("error: " + row["error"] if row.get("status") != "ok"
                  else "survived" if row.get("survived") else "extinct")
        print(f"[{self.stage} {self.done}/{self.total}] {meta.get('arm', '')} "
              f"rate={meta.get('rate_c_per_gen', 0):.3g} seed={meta.get('seed')} {status}",
              flush=True)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _base(config: Path) -> dict[str, Any]:
    from evolution_sim.config import SimulationConfig

    data = _read_json(config)
    if not SimulationConfig.from_dict(data).climate.enabled:
        raise ConfigError(f"{config} must enable the climate section")
    return data


def _phases(profile: dict[str, Any]) -> RescuePhases:
    return RescuePhases.from_dict(profile["phases"])


def stage_calibrate(root: Path, base: dict[str, Any], profile: dict[str, Any],
                    workers: int) -> dict[str, Any]:
    path = root / "calibration.json"
    if path.exists():
        return _read_json(path)
    options = profile["calibration"]
    print(f"Calibrating generation interval with seeds {options['seeds']} ...", flush=True)
    result = calibrate_generation_ticks(base, options["seeds"], workers=workers,
                                        burn_in_ticks=options["burn_in_ticks"],
                                        measure_ticks=options["measure_ticks"])
    _write_json(path, result)
    print(f"Generation interval: {result['generation_ticks']} ticks", flush=True)
    return result


def stage_sweep(root: Path, base: dict[str, Any], profile: dict[str, Any], workers: int,
                generation_ticks: int) -> dict[str, Any]:
    tasks = sweep_tasks(base, rates=profile["rates"], seeds=range(1, profile["seeds"] + 1),
                        generation_ticks=generation_ticks, phases=_phases(profile))
    rows = run_tasks(tasks, root / "sweep" / "results.jsonl", workers=workers,
                     progress=_Progress("sweep", len(tasks)))
    summary = summarize_sweep(rows, n_boot=profile["n_boot"], seed=0,
                              warming_generations=profile["phases"]["warming"])
    _write_json(root / "sweep" / "summary.json", summary)
    return {"summary": summary, "rows": rows}


def _rate_high(summary: dict[str, Any], profile: dict[str, Any]) -> float:
    estimate = (summary["critical_rate"].get("heritable") or {}).get("estimate")
    if estimate is None:
        return float(max(profile["rates"]))
    limit = 30.0 / profile["phases"]["warming"]
    return min(limit, math.ceil(1.5 * estimate / 0.05) * 0.05)


def _design_rows(root: Path, name: str, base: dict[str, Any], params, unit: np.ndarray,
                 seed0: int, generation_ticks: int, profile: dict[str, Any],
                 workers: int) -> list[dict[str, Any]]:
    conditions = design_conditions(scale(unit, params), params, seed0=seed0)
    tasks = [make_task(base, condition, generation_ticks, _phases(profile))
             for condition in conditions]
    return run_tasks(tasks, root / "sensitivity" / f"{name}.jsonl", workers=workers,
                     progress=_Progress(name, len(tasks)))


def _xy(rows: list[dict[str, Any]], params) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ok = [row for row in rows if row.get("status") == "ok"]
    x = np.array([[row["meta"][p.name] for p in params] for row in ok], dtype=float)
    return x, np.array([row["ratio"] for row in ok]), np.array([row["survived"] for row in ok])


def stage_sensitivity(root: Path, base: dict[str, Any], profile: dict[str, Any], workers: int,
                      generation_ticks: int, sweep_summary: dict[str, Any]) -> dict[str, Any]:
    params_path = root / "sensitivity" / "params.json"
    if params_path.exists():
        rate_high = _read_json(params_path)["rate_high"]
    else:
        rate_high = _rate_high(sweep_summary, profile)
        _write_json(params_path, {"rate_high": rate_high})
    params = parameters(rate_high)
    design = _design_rows(root, "design", base, params,
                          latin_hypercube(profile["design_points"], len(params), DESIGN_SEED),
                          DESIGN_SEED0, generation_ticks, profile, workers)
    holdout = _design_rows(root, "holdout", base, params,
                           latin_hypercube(profile["holdout_points"], len(params),
                                           HOLDOUT_SEED),
                           HOLDOUT_SEED0, generation_ticks, profile, workers)
    x, ratio, survived = _xy(design, params)
    xh, ratio_h, survived_h = _xy(holdout, params)
    model = Surrogate(params, seed=0).fit(x, ratio, survived)
    model.save(root / "sensitivity" / "surrogate")
    validation = {"cv": cross_validate(params, x, ratio, survived, folds=5, seed=0),
                  "holdout": holdout_metrics(model, xh, ratio_h, survived_h),
                  "design_rows": len(design), "holdout_rows": len(holdout),
                  "error_rows": sum(row.get("status") != "ok" for row in design + holdout)}
    _write_json(root / "sensitivity" / "validation.json", validation)

    def survival(unit: np.ndarray) -> np.ndarray:
        return model.predict(scale(unit, params))["survival_probability"]

    def population(unit: np.ndarray) -> np.ndarray:
        return model.predict(scale(unit, params))["ratio_mean"]

    sobol = {"survival": sobol_indices(survival, len(params), n=profile["sobol_n"], seed=0),
             "ratio": sobol_indices(population, len(params), n=profile["sobol_n"], seed=0)}
    sensitivity = {"names": [p.name for p in params],
                   "params": [asdict(p) for p in params], "rate_high": rate_high,
                   "sobol": sobol, "design_points": len(design)}
    _write_json(root / "sensitivity" / "sobol.json", sensitivity)
    return {"sensitivity": sensitivity, "validation": validation, "surrogate": model}


def stage_assess(root: Path, base: dict[str, Any], profile: dict[str, Any], workers: int, *,
                 region_specs: Sequence[str], ssps: Sequence[str], generation_years: float,
                 breadth_c: float, seeds: int, regional_factor: float,
                 sweep_summary: dict[str, Any] | None,
                 surrogate: Surrogate | None) -> list[dict[str, Any]]:
    climate = base["climate"]
    monthly = climate["monthly_c"]
    domain = {"amplitude_c": (max(monthly) - min(monthly)) / 2,
              "breadth_c": float(climate.get("tolerance_breadth_c", 4.0))}
    results = []
    for spec in region_specs:
        region = resolve_region(spec)
        request = AssessmentRequest(
            region=region, generation_years=generation_years, breadth_c=breadth_c,
            ssps=tuple(ssps), regional_factor=regional_factor, seeds=tuple(range(1, seeds + 1)),
            max_warming_generations=profile["max_warming_generations"],
            burn_in_generations=profile["phases"]["burn_in"],
            hold_generations=profile["phases"]["hold"])
        print(f"Assessing {region.name} ({', '.join(ssps)}) ...", flush=True)
        results.append(assess(request, base, results_dir=root / "assess" / region.key,
                              workers=workers, sweep_summary=sweep_summary,
                              sweep_domain=domain, surrogate=surrogate,
                              calibration_kwargs={"seeds": [101, 102],
                                                  **{k: v for k, v in
                                                     profile["calibration"].items()
                                                     if k != "seeds"}}))
    return results


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _provenance(config: Path, regions: Sequence[str]) -> dict[str, Any]:
    import scipy
    import sklearn

    from evolution_sim.experiments.runner import _source_digest

    config_json = json.dumps(_read_json(config), sort_keys=True, separators=(",", ":"))
    provenance = {"config": str(config.name),
                  "config_sha256": hashlib.sha256(config_json.encode()).hexdigest(),
                  "source_sha256": _source_digest(), "git_commit": _git_commit(),
                  "python": platform.python_version(), "numpy": np.__version__,
                  "scipy": scipy.__version__, "scikit_learn": sklearn.__version__,
                  "warming_pathways": SSP_SOURCE,
                  "climate_data": "NASA POWER monthly T2M (MERRA-2): " + POWER_URL.split("?")[0]}
    for spec in regions:
        region = resolve_region(spec)
        provenance[f"data_{region.key}_sha256"] = region.provenance.get("sha256")
        provenance[f"data_{region.key}_retrieved"] = region.provenance.get("retrieved_utc")
    return provenance


def _extra_criteria(validation: dict[str, Any] | None,
                    sensitivity: dict[str, Any] | None) -> list[dict[str, Any]]:
    criteria = []
    if validation:
        holdout = validation["holdout"]
        r2, auc = holdout.get("r2"), holdout.get("auc")
        criteria.append({"id": "S9", "statement": "Surrogate predicts held-out simulations",
                         "value": {"r2": r2, "auc": auc}, "threshold": "R² ≥ 0.7 and AUC ≥ 0.85",
                         "passed": bool(r2 is not None and auc is not None
                                        and r2 >= 0.7 and auc >= 0.85)})
    if sensitivity:
        total = sensitivity["sobol"]["survival"]["ST"]
        ranking = [sensitivity["names"][i] for i in np.argsort(total)[::-1]]
        criteria.append({"id": "S10", "statement": "Warming rate is a top-2 driver of survival",
                         "value": ranking[:3], "threshold": "rate_c_per_gen in top 2 by ST",
                         "passed": "rate_c_per_gen" in ranking[:2]})
    return criteria


def stage_report(root: Path, config: Path, profile: dict[str, Any]) -> tuple[int, Path]:
    from evolution_sim.climate.figures import build_figures
    from evolution_sim.climate.report import write_report

    context: dict[str, Any] = {"title": "Can evolution outrun warming? Vikasa climate rescue",
                               "generated_utc": dt.datetime.now(dt.UTC).strftime(
                                   "%Y-%m-%dT%H:%M:%SZ")}
    if (root / "calibration.json").exists():
        context["calibration"] = _read_json(root / "calibration.json")
    results = root / "sweep" / "results.jsonl"
    if results.exists():
        rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        rows.sort(key=lambda row: row["key"])
        summary = (_read_json(root / "sweep" / "summary.json")
                   if (root / "sweep" / "summary.json").exists()
                   else summarize_sweep(rows, n_boot=profile["n_boot"]))
        context["sweep"] = {"summary": summary, "rows": rows}
    if (root / "sensitivity" / "sobol.json").exists():
        context["sensitivity"] = _read_json(root / "sensitivity" / "sobol.json")
    if (root / "sensitivity" / "validation.json").exists():
        context["surrogate_validation"] = _read_json(root / "sensitivity" / "validation.json")
    assessments = sorted((root / "assess").glob("*/assessment.json")) \
        if (root / "assess").exists() else []
    context["assessments"] = [_read_json(path) for path in assessments]
    context["criteria"] = ((context.get("sweep") or {}).get("summary", {}).get("criteria", [])
                           + _extra_criteria(context.get("surrogate_validation"),
                                             context.get("sensitivity")))
    context["provenance"] = _provenance(config, [a["request"]["region"]
                                                 for a in context["assessments"]])
    write_report(root / "report", context, build_figures(context))
    _print_criteria(context["criteria"])
    failures = [c for c in context["criteria"] if not c["passed"]]
    integrity = next((c for c in context["criteria"] if c["id"] == "C6"), None)
    code = 1 if integrity and not integrity["passed"] else (3 if failures else 0)
    return code, root / "report" / "index.html"


def _print_criteria(criteria: list[dict[str, Any]]) -> None:
    if not criteria:
        return
    print("\nSuccess criteria")
    for criterion in criteria:
        mark = "PASS" if criterion["passed"] else "FAIL"
        print(f"  {criterion['id']:<4} {mark}  {criterion['statement']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vikasa climate",
        description="Evolutionary rescue under climate warming: real regional temperature, "
                    "replicated simulations, sensitivity analysis and an offline report.")
    commands = parser.add_subparsers(dest="command", required=True)
    workers = max(1, (os.cpu_count() or 2) - 1)

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--root", type=Path, default=Path("exports/climate/full"),
                         help="Evidence directory (resumable; reused across stages)")
        sub.add_argument("--profile", choices=sorted(PROFILES), default="full")
        sub.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        sub.add_argument("--workers", type=int, default=workers)

    fetch = commands.add_parser("fetch", help="Download a region's monthly temperature")
    fetch.add_argument("--lat", type=float, required=True)
    fetch.add_argument("--lon", type=float, required=True)
    fetch.add_argument("--name", required=True, help="Human-readable region name")
    fetch.add_argument("--key", required=True, help="Short identifier, e.g. 'pune'")
    fetch.add_argument("--output", type=Path, required=True, help="Region JSON to write")
    fetch.add_argument("--start", type=int, default=1981)
    fetch.add_argument("--end", type=int, default=dt.date.today().year - 1)
    for name, text in (("calibrate", "Measure the generation interval (ticks)"),
                       ("sweep", "Survival across warming rates, with and without heritability"),
                       ("sensitivity", "Latin-hypercube design, GP surrogate and Sobol indices"),
                       ("report", "Render the offline HTML report from existing results"),
                       ("pipeline", "Run every stage end to end (resumable)")):
        common(commands.add_parser(name, help=text))
    assess_parser = commands.add_parser("assess", help="Survival per SSP for a real region")
    common(assess_parser)
    assess_parser.add_argument("--region", action="append",
                               help=f"Bundled key ({', '.join(BUNDLED_REGIONS)}) or region JSON;"
                                    " repeatable")
    assess_parser.add_argument("--ssp", action="append", choices=sorted(SSP_WARMING))
    assess_parser.add_argument("--generation-years", type=float,
                               help="Generation time of the organism, years")
    assess_parser.add_argument("--breadth", type=float, help="Tolerance breadth, °C")
    assess_parser.add_argument("--seeds-count", type=int)
    assess_parser.add_argument("--regional-factor", type=float, default=1.0)
    return parser


def _stage_inputs(args) -> tuple[dict[str, Any], dict[str, Any]]:
    if args.workers < 1:
        raise ValueError("--workers must be at least 1")
    return _base(args.config), PROFILES[args.profile]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch":
            raw, url = fetch_power_monthly(args.lat, args.lon, args.start, args.end)
            region = region_from_power(args.key, args.name, args.lat, args.lon, raw, url,
                                       dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            save_region(region, args.output)
            print(f"{region.name}: {region.first_year}-{region.last_year}, annual mean "
                  f"{region.annual_mean_c:.2f} °C, seasonal amplitude "
                  f"{region.seasonal_amplitude_c:.2f} °C, trend {region.trend_c_per_decade:+.3f}"
                  f" ± {region.trend_se_c_per_decade:.3f} °C/decade -> {args.output}")
            return 0
        base, profile = _stage_inputs(args)
        root = Path(args.root)
        if args.command == "report":
            code, path = stage_report(root, args.config, profile)
            print(f"Report: {path}")
            return code
        if args.command == "assess":
            regions = args.region or list(profile["regions"])
            for spec in regions:
                resolve_region(spec)
            summary = (_read_json(root / "sweep" / "summary.json")
                       if (root / "sweep" / "summary.json").exists() else None)
            surrogate_dir = root / "sensitivity" / "surrogate"
            surrogate = Surrogate.load(surrogate_dir) if surrogate_dir.exists() else None
            stage_assess(root, base, profile, args.workers, region_specs=regions,
                         ssps=args.ssp or profile["ssps"],
                         generation_years=args.generation_years or profile["generation_years"],
                         breadth_c=args.breadth or profile["breadth_c"],
                         seeds=args.seeds_count or profile["assess_seeds"],
                         regional_factor=args.regional_factor, sweep_summary=summary,
                         surrogate=surrogate)
            print(f"Assessments written under {root / 'assess'}")
            return 0
        calibration = stage_calibrate(root, base, profile, args.workers)
        if args.command == "calibrate":
            return 0
        generation_ticks = int(calibration["generation_ticks"])
        sweep = stage_sweep(root, base, profile, args.workers, generation_ticks)
        if args.command == "sweep":
            _print_criteria(sweep["summary"]["criteria"])
            return 0
        sensitivity = stage_sensitivity(root, base, profile, args.workers, generation_ticks,
                                        sweep["summary"])
        if args.command == "sensitivity":
            return 0
        stage_assess(root, base, profile, args.workers, region_specs=profile["regions"],
                     ssps=profile["ssps"], generation_years=profile["generation_years"],
                     breadth_c=profile["breadth_c"], seeds=profile["assess_seeds"],
                     regional_factor=1.0, sweep_summary=sweep["summary"],
                     surrogate=sensitivity["surrogate"])
        code, path = stage_report(root, args.config, profile)
        print(f"Report: {path}")
        return code
    except (ConfigError, OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
