"""Species Risk Checker: will a species keep up with warming in a real place?

Two answers, clearly separated:

* **Instant estimate** (milliseconds). A mechanistic seasonal screen built from
  the model's own thermal-stress rule, followed by the survival-versus-warming
  curve measured in the full climate-rescue run. Inputs outside the conditions
  that curve was measured in are flagged, never silently extrapolated.
* **Live check** (about a minute). Direct individual-based simulation of the
  chosen place, organism and scenario, using :func:`evolution_sim.climate.assess.assess`.

The climate is real (NASA POWER, IPCC AR6). The organism is a generic model whose
generation time and tolerance breadth you choose; species presets are
illustrative orders of magnitude, not measured species data.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evolution_sim.climate.assess import (
    BIOLOGY_DISCLAIMER,
    AssessmentRequest,
    assess,
    verdict,
)
from evolution_sim.climate.data import (
    BUNDLED_REGIONS,
    CITY_REGIONS,
    DATA_DIR,
    SSP_WARMING,
    SURVEY_REGIONS,
    RegionClimate,
    resolve_region,
    ssp_anomaly_c,
    ssp_rate_c_per_year,
)

ROOT = Path(__file__).resolve().parents[3]
REFERENCE_PATH = DATA_DIR / "risk-reference.json"
RESCUE_CONFIG = ROOT / "config" / "climate-rescue.json"
DEMO_CONFIG = ROOT / "config" / "climate-demo.json"

START_YEAR, END_YEAR = 2025, 2100
BORDERLINE_BAND = 0.05
DOMAIN_TOLERANCE = 0.25

SPECIES_PRESETS: tuple[dict[str, Any], ...] = (
    {"key": "insect", "label": "Short-lived insect", "icon": "🦗", "generation_years": 0.25},
    {"key": "frog", "label": "Frog", "icon": "🐸", "generation_years": 1.0},
    {"key": "reference", "label": "Reference organism", "icon": "🧬", "generation_years": 1.0,
     "breadth_c": 4.0, "note": "The organism measured in the published full run."},
    {"key": "lizard", "label": "Lizard", "icon": "🦎", "generation_years": 2.0},
    {"key": "fish", "label": "Freshwater fish", "icon": "🐟", "generation_years": 3.0},
    {"key": "turtle", "label": "Pond turtle", "icon": "🐢", "generation_years": 10.0},
    {"key": "tortoise", "label": "Giant tortoise", "icon": "🪨", "generation_years": 25.0},
)
PRESET_NOTE = ("Preset generation times are illustrative orders of magnitude, not measured "
               "species data. Enter a species' own values for a specific assessment.")

TOLERANCE_MODES: dict[str, tuple[str, float]] = {
    "specialist": ("Specialist: tolerance matches the local seasonal swing", 1.0),
    "local": ("Locally adapted: 1.5 x the local seasonal swing", 1.5),
    "generalist": ("Generalist: 2.5 x the local seasonal swing", 2.5),
}


def load_reference() -> dict[str, Any]:
    return json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))


def places() -> list[dict[str, Any]]:
    """Every place the checker can assess without a network connection."""
    rows = []
    for key in (*CITY_REGIONS, *BUNDLED_REGIONS, *SURVEY_REGIONS):
        region = resolve_region(key)
        rows.append({"key": key, "name": region.name, "latitude": region.latitude,
                     "longitude": region.longitude, "annual_mean_c": region.annual_mean_c,
                     "seasonal_amplitude_c": region.seasonal_amplitude_c,
                     "trend_c_per_decade": region.trend_c_per_decade,
                     "monthly_c": list(region.monthly_c),
                     "kind": ("city" if key in CITY_REGIONS else "survey site"
                              if key in SURVEY_REGIONS else "study region")})
    return rows


def resolve_breadth(region: RegionClimate, tolerance: str | float) -> float:
    """Tolerance breadth in °C: a number, or a mode scaled to local seasonality.

    Modes follow the climatic-variability hypothesis used by the published
    pipeline's locally adapted organism: breadth widens with the seasonal swing
    a species lives with. Never narrower than 2 °C.
    """
    if isinstance(tolerance, (int, float)) or str(tolerance).replace(".", "", 1).isdigit():
        value = float(tolerance)
        if not 0.5 <= value <= 50:
            raise ValueError("tolerance breadth must be between 0.5 and 50 °C")
        return value
    if tolerance not in TOLERANCE_MODES:
        raise ValueError(f"tolerance must be a number or one of {', '.join(TOLERANCE_MODES)}")
    return max(2.0, TOLERANCE_MODES[str(tolerance)][1] * region.seasonal_amplitude_c)


def seasonal_screen(region: RegionClimate, breadth_c: float, *,
                    warm_side_ratio: float = 0.6, breeding_limit: float = 0.7) -> dict[str, Any]:
    """Can the organism live through today's seasons with no warming at all?

    Founders start with an optimum at the annual mean. Peak-season stress uses the
    model's own asymmetric thermal-performance rule; above ``breeding_limit``
    (heat-induced sterility in the model) the population cannot replace itself.
    This reproduces all five baseline verdicts recorded in the published run.
    """
    mean = region.annual_mean_c
    warm_gap = max(region.monthly_c) - mean
    cold_gap = mean - min(region.monthly_c)
    warm = 1.0 - math.exp(-(warm_gap ** 2) / (2.0 * (breadth_c * warm_side_ratio) ** 2))
    cold = 1.0 - math.exp(-(cold_gap ** 2) / (2.0 * breadth_c ** 2))
    peak = max(warm, cold)
    if peak > breeding_limit + BORDERLINE_BAND:
        status = "not viable"
    elif peak >= breeding_limit - BORDERLINE_BAND:
        status = "borderline"
    else:
        status = "viable"
    return {"status": status, "peak_stress": peak, "warm_stress": warm, "cold_stress": cold,
            "warm_gap_c": warm_gap, "cold_gap_c": cold_gap, "breeding_limit": breeding_limit,
            "limiting_season": "hot season" if warm >= cold else "cold season"}


def _logistic(logistic: dict[str, float], rate: float) -> float:
    z = logistic["b0"] + logistic["b1"] * rate
    return 1.0 / (1.0 + math.exp(-z)) if z > -700 else 0.0


def scenario_estimate(region: RegionClimate, generation_years: float, ssp: str,
                      reference: dict[str, Any], *, regional_factor: float = 1.0
                      ) -> dict[str, Any]:
    heritable = reference["heritable"]
    critical = heritable["critical_rate"]
    rate_year = ssp_rate_c_per_year(ssp, regional_factor)
    rate_generation = rate_year * generation_years
    generations = (END_YEAR - START_YEAR) / generation_years
    return {
        "ssp": ssp,
        "rate_c_per_year": rate_year,
        "rate_c_per_generation": rate_generation,
        "warming_2025_2100_c": rate_year * (END_YEAR - START_YEAR),
        "anomaly_2100_c": ssp_anomaly_c(ssp, END_YEAR, regional_factor),
        "generations_to_2100": generations,
        "pressure": rate_generation / critical,
        "critical_generation_years": critical / rate_year,
        "critical_generation_years_ci": [low / rate_year for low in heritable["ci95"]],
        "p_with_evolution": _logistic(heritable["logistic"], rate_generation),
        "p_without_evolution": _logistic(reference["control"]["logistic"], rate_generation),
        "beyond_measured_rates": rate_generation > reference["max_rate_c_per_generation"],
    }


def instant_estimate(place: str | RegionClimate, *, generation_years: float,
                     tolerance: str | float = "local", ssp: str = "SSP5-8.5",
                     regional_factor: float = 1.0,
                     reference: dict[str, Any] | None = None) -> dict[str, Any]:
    """Seasonal screen + reference rescue curve for every SSP; milliseconds."""
    if not 0.05 <= generation_years <= 50:
        raise ValueError("generation time must be between 0.05 and 50 years")
    if ssp not in SSP_WARMING:
        raise ValueError(f"Unknown SSP {ssp!r}; use one of {', '.join(SSP_WARMING)}")
    region = place if isinstance(place, RegionClimate) else resolve_region(place)
    reference = reference or load_reference()
    breadth = resolve_breadth(region, tolerance)
    screen = seasonal_screen(region, breadth)
    scenarios = {name: scenario_estimate(region, generation_years, name, reference,
                                         regional_factor=regional_factor)
                 for name in SSP_WARMING}
    chosen = scenarios[ssp]
    in_domain = (abs(region.seasonal_amplitude_c - reference["amplitude_c"])
                 <= DOMAIN_TOLERANCE * reference["amplitude_c"]
                 and abs(breadth - reference["breadth_c"])
                 <= DOMAIN_TOLERANCE * reference["breadth_c"])
    if screen["status"] == "not viable":
        headline, p = "not viable in today's climate", 0.0
    else:
        p = chosen["p_with_evolution"]
        headline = verdict(p)
    notes = [BIOLOGY_DISCLAIMER]
    if screen["status"] == "borderline":
        notes.append("Today's seasons are close to the breeding limit; run the live check.")
    if not in_domain:
        notes.append(f"The reference curve was measured for a {reference['breadth_c']:g} °C "
                     f"tolerance and ±{reference['amplitude_c']:.1f} °C seasons; this place "
                     "and organism differ, so treat the probability as indicative and run "
                     "the live check for a direct answer.")
    if chosen["beyond_measured_rates"]:
        notes.append("Warming per generation exceeds the fastest rate measured "
                     f"({reference['max_rate_c_per_generation']:g} °C); the curve is "
                     "extrapolated.")
    return {
        "schema": "vikasa-risk-estimate-v1",
        "place": {"key": region.key, "name": region.name, "latitude": region.latitude,
                  "longitude": region.longitude, "annual_mean_c": region.annual_mean_c,
                  "seasonal_amplitude_c": region.seasonal_amplitude_c,
                  "trend_c_per_decade": region.trend_c_per_decade,
                  "monthly_c": list(region.monthly_c)},
        "organism": {"generation_years": generation_years, "tolerance": tolerance,
                     "breadth_c": breadth},
        "ssp": ssp, "regional_factor": regional_factor,
        "verdict": headline, "survival_probability": p, "seasonal": screen,
        "scenario": chosen, "scenarios": scenarios, "in_reference_domain": in_domain,
        "reference": {"critical_rate": reference["heritable"]["critical_rate"],
                      "critical_rate_ci95": reference["heritable"]["ci95"],
                      "control_critical_rate": reference["control"]["critical_rate"],
                      "source": reference["source"]},
        "notes": notes,
    }


# --------------------------------------------------------------------------- live check

@dataclass
class LiveJob:
    id: str
    place: str
    generation_years: float
    breadth_c: float
    ssp: str
    seeds: int
    root: Path
    total_runs: int
    status: str = "queued"
    stage: str = "Waiting to start"
    started: float = 0.0
    finished: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        done = 0
        results = self.root / "results.jsonl"
        if results.exists():
            done = sum(1 for line in results.read_text(encoding="utf-8").splitlines()
                       if line.strip())
        elapsed = (self.finished or time.time()) - self.started if self.started else 0.0
        stage = self.stage
        if self.status == "running" and done:
            stage = f"Simulating populations: {done} of {self.total_runs} complete"
        return {"id": self.id, "status": self.status, "stage": stage,
                "done": min(done, self.total_runs), "total": self.total_runs,
                "elapsed_seconds": round(elapsed, 1), "result": self.result,
                "error": self.error}


class LiveChecks:
    """Background direct simulations, one thread per request, results cached on disk."""

    def __init__(self, root: Path | None = None, workers: int | None = None) -> None:
        self.root = Path(root) if root is not None else ROOT / "exports" / "risk"
        self.workers = workers or max(1, (os.cpu_count() or 2) - 1)
        self.jobs: dict[str, LiveJob] = {}
        self.lock = threading.Lock()

    def start(self, place: str, *, generation_years: float, tolerance: str | float,
              ssp: str, seeds: int = 4, max_warming_generations: float = 25.0,
              run_inline: bool = False) -> LiveJob:
        if not 1 <= seeds <= 24:
            raise ValueError("seeds must be between 1 and 24")
        region = resolve_region(place)
        breadth = resolve_breadth(region, tolerance)
        if ssp not in SSP_WARMING:
            raise ValueError(f"Unknown SSP {ssp!r}")
        if not 0.05 <= generation_years <= 50:
            raise ValueError("generation time must be between 0.05 and 50 years")
        identity = json.dumps([region.key, generation_years, round(breadth, 4), ssp, seeds,
                               max_warming_generations], sort_keys=True)
        digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
        job = LiveJob(id=uuid.uuid4().hex[:10], place=region.key,
                      generation_years=generation_years, breadth_c=breadth, ssp=ssp,
                      seeds=seeds, root=self.root / f"{region.key}-{digest}",
                      total_runs=seeds)
        request = AssessmentRequest(
            region=region, generation_years=generation_years, breadth_c=breadth,
            ssps=(ssp,), seeds=tuple(range(1, seeds + 1)),
            max_warming_generations=max_warming_generations)
        with self.lock:
            self.jobs[job.id] = job
        if run_inline:
            self._run(job, request)
        else:
            threading.Thread(target=self._run, args=(job, request), daemon=True).start()
        return job

    def _run(self, job: LiveJob, request: AssessmentRequest) -> None:
        job.status, job.started = "running", time.time()
        job.stage = "Measuring this organism's generation time in today's climate"
        try:
            base = json.loads(RESCUE_CONFIG.read_text(encoding="utf-8"))
            reference = load_reference()
            outcome = assess(
                request, base, results_dir=job.root, workers=self.workers,
                calibration_kwargs={"seeds": [101, 102], "burn_in_ticks": 1500,
                                    "measure_ticks": 6000,
                                    "reference_generation_ticks":
                                        reference["generation_ticks"]},
                assessment_id=f"risk-{job.place}", label=f"Species Risk Checker: {job.place}")
            entry = outcome["ssps"][0]
            job.result = {"verdict": entry["verdict"], "direct": entry["direct"],
                          "plan": {key: entry["plan"][key] for key in (
                              "rate_c_per_generation", "span_years", "truncated",
                              "simulated_end_year", "warming_c")},
                          "baseline_viable": outcome["baseline_viable"],
                          "caveats": outcome["caveats"],
                          "evidence": str(job.root / "assessment.json")}
            job.status, job.stage = "done", "Complete"
        except Exception as exc:  # reported to the user, never hidden
            job.status, job.error, job.stage = "error", f"{type(exc).__name__}: {exc}", "Failed"
        finally:
            job.finished = time.time()

    def get(self, job_id: str) -> LiveJob:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return self.jobs[job_id]


# --------------------------------------------------------------------------- 3D scenario

def watch_config(place: str | RegionClimate, *, generation_years: float,
                 tolerance: str | float, ssp: str, generations: float = 20.0) -> dict[str, Any]:
    """A Living Biome config that replays this place and scenario in fast-forward.

    One climate year of the demo world is roughly one model generation, so the
    warming per generation the species would face is applied per year for
    ``generations`` years after a three-year settling period.
    """
    region = place if isinstance(place, RegionClimate) else resolve_region(place)
    data = json.loads(DEMO_CONFIG.read_text(encoding="utf-8"))
    breadth = resolve_breadth(region, tolerance)
    rate = ssp_rate_c_per_year(ssp) * generation_years
    warming = min(25.0, rate * generations)
    data["climate"] = {**data["climate"], "monthly_c": list(region.monthly_c),
                       "tolerance_breadth_c": breadth,
                       "anomaly_c": [[0, 0.0], [3, 0.0], [3 + generations, round(warming, 4)]]}
    return data


def write_watch_config(target: Path, place: str, **kwargs: Any) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(watch_config(place, **kwargs), indent=2) + "\n",
                      encoding="utf-8")
    return target


def describe(estimate: dict[str, Any]) -> str:
    """Plain-text rendering for the command line."""
    place, organism = estimate["place"], estimate["organism"]
    scenario, screen = estimate["scenario"], estimate["seasonal"]
    lines = [
        f"Species Risk Checker · {place['name']} · {estimate['ssp']}",
        f"  Climate     mean {place['annual_mean_c']:.1f} °C, seasons ±"
        f"{place['seasonal_amplitude_c']:.1f} °C (NASA POWER 1991-2020)",
        f"  Organism    generation {organism['generation_years']:g} years, tolerance "
        f"{organism['breadth_c']:.1f} °C ({organism['tolerance']})",
        f"  Today       {screen['status']} (peak {screen['limiting_season']} stress "
        f"{screen['peak_stress']:.2f}; breeding stops above {screen['breeding_limit']:.1f})",
        f"  Warming     {scenario['rate_c_per_generation']:.3f} °C per generation "
        f"({scenario['pressure'] * 100:.0f}% of the critical rate)",
        f"  Danger line generations longer than {scenario['critical_generation_years']:.1f} "
        f"years fall behind under {estimate['ssp']}",
        f"  Survival    {estimate['survival_probability'] * 100:.0f}% with evolution, "
        f"{scenario['p_without_evolution'] * 100:.0f}% without",
        f"  VERDICT     {estimate['verdict'].upper()}",
    ]
    lines.extend(f"  · {note}" for note in estimate["notes"])
    return "\n".join(lines)


__all__ = ["PRESET_NOTE", "SPECIES_PRESETS", "TOLERANCE_MODES", "LiveChecks", "describe",
           "instant_estimate", "load_reference", "places", "resolve_breadth",
           "seasonal_screen", "watch_config", "write_watch_config"]

