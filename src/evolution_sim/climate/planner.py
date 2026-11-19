"""Conservation Planner: from "is this species at risk?" to "what do we do about it?".

The Species Risk Checker answers one question for one species. Conservation teams
work from a *watchlist*: dozens of species, limited money, and a need to decide
which ones to act on first and how. The planner turns Vikasa's measured
evolutionary-rescue results into that decision support:

* **Timeline.** A first-order adaptation-lag model gives the year in which hot
  season heat stress first crosses the model's breeding limit, with and without
  evolution, under every IPCC pathway. Evolution tracks warming up to the
  measured critical rate per generation; warming beyond that accumulates as lag.
* **Assisted gene flow.** The smallest heat-tolerance shift (°C) that keeps the
  population breeding to 2100, and surveyed populations warm enough to supply it.
* **Assisted migration.** Every surveyed site is scored as a climate refuge for
  the translocated stock, from today to 2100, with great-circle distances.
* **Triage.** A 0-100 priority score, a tier and an ordered action list for each
  species, written as JSON, CSV and a self-contained HTML report.

Climate inputs are real (NASA POWER, IPCC AR6). The organism is Vikasa's generic
model; species parameters you enter are assumptions, and every output is a
screening estimate to prioritise field work, not a substitute for it.
"""

from __future__ import annotations

import csv
import html
import io
import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evolution_sim.climate.data import (
    BUNDLED_REGIONS,
    CITY_REGIONS,
    SSP_REFERENCE_YEAR,
    SSP_WARMING,
    SURVEY_REGIONS,
    RegionClimate,
    resolve_region,
    ssp_anomaly_c,
    ssp_rate_c_per_year,
)
from evolution_sim.climate.risk import (
    BORDERLINE_BAND,
    instant_estimate,
    load_reference,
    resolve_breadth,
)
from evolution_sim.climate.thermal import thermal_stress

WARM_SIDE_RATIO = 0.6
BREEDING_LIMIT = 0.7
# A population fails once peak stress is clearly past the breeding limit: the same
# band the seasonal screen uses for "not viable", so borderline places are not
# reported as failing in the first year.
FAIL_STRESS = BREEDING_LIMIT + BORDERLINE_BAND
START_YEAR, END_YEAR = 2025, 2100
TRANSLOCATION_YEAR = 2030
MAX_SHIFT_C = 15.0
SCHEMA = "vikasa-conservation-plan-v1"
PLANNER_NOTE = ("Screening estimate for prioritising field work. Climate is observed "
                "(NASA POWER grid cells, IPCC AR6 pathways); the organism is Vikasa's generic "
                "model with the generation time and tolerance you entered. Translocation and "
                "gene flow need species-specific ecology, disease and genetic checks.")
TIERS = (("critical", 70), ("high", 45), ("watch", 20), ("low", 0))
TIER_LABELS = {"critical": "Critical", "high": "High", "watch": "Watch", "low": "Low"}

# Broad habitat of each bundled site, so refuges and donors respect where a species
# can live at all: a sea turtle needs a coast, a tahr needs mountains. Places
# fetched by the user have no tag and are offered for every habitat.
SITE_HABITAT: dict[str, str] = {
    "chennai": "coastal", "mumbai": "coastal", "kolkata": "coastal", "kochi": "coastal",
    "sundarbans": "coastal",
    "shimla": "montane", "ooty": "montane", "munnar": "montane", "darjeeling": "montane",
    "shillong": "montane", "srinagar": "montane", "leh": "montane", "dehradun": "montane",
    "western-ghats": "montane",
    "hyderabad": "inland", "bengaluru": "inland", "jaipur": "inland", "delhi-ncr": "inland",
    "pune": "inland", "nagpur": "inland", "bhopal": "inland", "ahmedabad": "inland",
    "lucknow": "inland", "guwahati": "inland",
}
HABITATS = ("any", "coastal", "montane", "inland")


def habitat_sites(sites: list[RegionClimate], habitat: str) -> list[RegionClimate]:
    habitat = (habitat or "any").lower()
    if habitat not in HABITATS:
        raise ValueError(f"habitat must be one of {', '.join(HABITATS)}")
    if habitat == "any":
        return sites
    return [site for site in sites if SITE_HABITAT.get(site.key, habitat) == habitat]


# --------------------------------------------------------------------------- places

def all_place_keys() -> list[str]:
    return [*CITY_REGIONS, *BUNDLED_REGIONS, *SURVEY_REGIONS]


def find_place(spec: str, extra: Iterable[RegionClimate] = (), *,
               allow_paths: bool = True) -> RegionClimate:
    """A bundled key, a place name (case-insensitive), or a region JSON path.

    ``allow_paths=False`` (used for watchlists arriving over HTTP) refuses file paths,
    so a request can only name bundled places or places already fetched.
    """
    text = str(spec).strip()
    lowered = text.lower()
    for region in extra:
        if lowered in (region.key.lower(), region.name.lower()):
            return region
    if lowered in (*CITY_REGIONS, *BUNDLED_REGIONS, *SURVEY_REGIONS):
        return resolve_region(lowered)
    for table in (CITY_REGIONS, BUNDLED_REGIONS, SURVEY_REGIONS):
        for key, (name, _, _) in table.items():
            short = name.split(" (")[0].lower()
            if lowered in (name.lower(), short):
                return resolve_region(key)
    if not allow_paths:
        raise ValueError(f"Unknown place {text!r}: use a bundled place key or name, or "
                         "fetch it first in the Species Risk Checker")
    return resolve_region(text)


def candidate_sites(extra: Iterable[RegionClimate] = ()) -> list[RegionClimate]:
    seen: dict[str, RegionClimate] = {key: resolve_region(key) for key in all_place_keys()}
    for region in extra:
        seen.setdefault(region.key, region)
    return list(seen.values())


def distance_km(a: RegionClimate, b: RegionClimate) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a.latitude, a.longitude,
                                                b.latitude, b.longitude))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


# --------------------------------------------------------------------------- physiology

def peak_stress(monthly_c: Iterable[float], optimum_c: float, breadth_c: float) -> float:
    """Worst monthly heat or cold stress under Vikasa's thermal-performance rule."""
    return max(thermal_stress(t, optimum_c, breadth_c, WARM_SIDE_RATIO) for t in monthly_c)


def tracking_rate(generation_years: float, ssp: str, critical: float, *,
                  evolving: bool = True) -> float:
    """°C per year the population's optimum can follow: capped at the critical rate."""
    if not evolving:
        return 0.0
    return min(ssp_rate_c_per_year(ssp), critical / generation_years)


def _optimum(home_mean: float, track: float, year: float) -> float:
    return home_mean + track * max(0.0, year - SSP_REFERENCE_YEAR)


def stress_at(region: RegionClimate, year: float, ssp: str, optimum: float,
              breadth: float) -> float:
    anomaly = ssp_anomaly_c(ssp, year)
    return peak_stress((t + anomaly for t in region.monthly_c), optimum, breadth)


def trajectory(region: RegionClimate, *, generation_years: float, breadth_c: float,
               ssp: str, critical: float, evolving: bool = True, shift_c: float = 0.0,
               home_mean_c: float | None = None) -> list[float]:
    """Peak seasonal stress for every year 2025-2100."""
    mean = region.annual_mean_c if home_mean_c is None else home_mean_c
    track = tracking_rate(generation_years, ssp, critical, evolving=evolving)
    return [stress_at(region, year, ssp, _optimum(mean, track, year) + shift_c, breadth_c)
            for year in range(START_YEAR, END_YEAR + 1)]


def breeding_fails(series: list[float]) -> int | None:
    """First year stress crosses the breeding limit; None if it never does by 2100."""
    for offset, value in enumerate(series):
        if value > FAIL_STRESS:
            return START_YEAR + offset
    return None


def gene_flow_needed(region: RegionClimate, *, generation_years: float, breadth_c: float,
                     ssp: str, critical: float) -> float | None:
    """Smallest optimum shift (°C) that keeps stress under the limit every year to 2100.

    0 when no help is needed; None when no shift works (the seasonal swing is too
    wide for this tolerance once warming is added, so cold or heat always binds).
    """
    def ok(shift: float) -> bool:
        series = trajectory(region, generation_years=generation_years, breadth_c=breadth_c,
                            ssp=ssp, critical=critical, shift_c=shift)
        return breeding_fails(series) is None

    if ok(0.0):
        return 0.0
    grid = [step * 0.25 for step in range(1, int(MAX_SHIFT_C / 0.25) + 1)]
    upper = next((value for value in grid if ok(value)), None)
    if upper is None:
        return None
    low, high = upper - 0.25, upper
    for _ in range(18):
        middle = (low + high) / 2
        if ok(middle):
            high = middle
        else:
            low = middle
    return math.ceil(high * 100) / 100  # round up: never report a shift that falls short


def score_refuge(home: RegionClimate, site: RegionClimate, *, generation_years: float,
                 breadth_c: float, ssp: str, critical: float) -> dict[str, Any]:
    """How the home-adapted stock would fare if moved to ``site`` in 2030.

    Conservative: the stock keeps its home optimum (tracking warming as before) and
    is not credited with further adaptation to the new site's seasons.
    """
    track = tracking_rate(generation_years, ssp, critical)
    years = range(TRANSLOCATION_YEAR, END_YEAR + 1)
    stresses = [stress_at(site, year, ssp, _optimum(home.annual_mean_c, track, year),
                          breadth_c) for year in years]
    worst, final = max(stresses), stresses[-1]
    if worst <= FAIL_STRESS:
        status = "refuge"
    elif final <= FAIL_STRESS:
        status = "future refuge"
    else:
        status = "unsuitable"
    viable_from = next((year for year, value in zip(years, stresses, strict=True)
                        if value <= FAIL_STRESS
                        and all(v <= FAIL_STRESS for v in stresses[year - TRANSLOCATION_YEAR:])),
                       None)
    return {"key": site.key, "name": site.name, "latitude": site.latitude,
            "longitude": site.longitude, "distance_km": round(distance_km(home, site)),
            "status": status, "worst_stress": round(worst, 4),
            "stress_2100": round(final, 4), "margin": round(FAIL_STRESS - final, 4),
            "viable_from": viable_from,
            "mean_2100_c": round(site.annual_mean_c + ssp_anomaly_c(ssp, END_YEAR), 2)}


def find_refuges(home: RegionClimate, sites: list[RegionClimate], **kwargs: Any
                 ) -> list[dict[str, Any]]:
    scored = [score_refuge(home, site, **kwargs) for site in sites if site.key != home.key]
    order = {"refuge": 0, "future refuge": 1, "unsuitable": 2}
    return sorted(scored, key=lambda row: (order[row["status"]], row["distance_km"]))


def find_donors(home: RegionClimate, sites: list[RegionClimate], shift_c: float,
                limit: int = 3) -> list[dict[str, Any]]:
    """Surveyed places whose local climate is warmer by at least the needed shift.

    A locally adapted population there would carry an optimum near that place's mean.
    Useful only where the species actually occurs: verify before moving genes.
    """
    rows = []
    for site in sites:
        if site.key == home.key:
            continue
        warmer = site.annual_mean_c - home.annual_mean_c
        if shift_c <= warmer <= shift_c + 4.0:
            rows.append({"key": site.key, "name": site.name,
                         "warmer_by_c": round(warmer, 2),
                         "distance_km": round(distance_km(home, site))})
    return sorted(rows, key=lambda row: row["distance_km"])[:limit]


# --------------------------------------------------------------------------- one species

def _priority(viable_today: bool, p_survive: float, fails: int | None) -> tuple[int, str]:
    if not viable_today:
        return 100, "critical"
    risk_part = 1.0 - p_survive
    urgency = 0.0 if fails is None else max(0.0, min(1.0, (END_YEAR - fails)
                                                     / (END_YEAR - START_YEAR)))
    score = round(100 * (0.55 * risk_part + 0.45 * urgency))
    if fails is not None and fails <= 2050:
        score = max(score, 70)
    tier = next(name for name, floor in TIERS if score >= floor)
    return score, tier


def _shift(value: float) -> str:
    return f"{value:.2f}" if value < 1 else f"{value:.1f}"


def _actions(plan: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    timeline = plan["timeline"]
    fails = timeline["breeding_fails_with_evolution"]
    refuges = [row for row in plan["refuges"] if row["status"] == "refuge"]
    future = [row for row in plan["refuges"] if row["status"] == "future refuge"]
    if not plan["viable_today"]:
        actions.append({"kind": "emergency", "title": "Verify in the field now",
                        "detail": "Today's hot season already exceeds the model's breeding "
                                  "limit for this tolerance. Check breeding success on site; "
                                  "if confirmed, start an ex-situ insurance population."})
    lenses_disagree = (plan["viable_today"] and fails is None
                       and plan["survival_probability"] < 0.5)
    if lenses_disagree:
        actions.append({"kind": "verify", "title": "Confirm with the live simulation",
                        "detail": "The measured survival curve says this generation time "
                                  "falls behind, but this tolerance still has seasonal "
                                  "headroom in 2100. Run 'vikasa risk check --live' before "
                                  "committing funds; plan the refuge below as a contingency."})
    if fails is not None or not plan["viable_today"] or lenses_disagree:
        shift = plan["gene_flow"]["shift_c"]
        if shift is not None and shift > 0:
            donors = plan["gene_flow"]["donors"]
            where = (", ".join(f"{d['name']} (+{d['warmer_by_c']:.1f} °C, "
                               f"{d['distance_km']} km)" for d in donors)
                     if donors else "no surveyed site is warm enough; look further afield")
            actions.append({"kind": "gene-flow",
                            "title": f"Assisted gene flow: +{_shift(shift)} °C heat tolerance",
                            "detail": f"Raising the population's thermal optimum by "
                                      f"{_shift(shift)} °C keeps it breeding to {END_YEAR}. "
                                      f"Candidate source populations: {where}."})
        elif shift is None:
            actions.append({"kind": "gene-flow", "title": "Gene flow alone cannot rescue it",
                            "detail": "No heat-tolerance shift keeps both hot and cold "
                                      "seasons inside this tolerance once warming is added."})
        if refuges:
            best = refuges[0]
            actions.append({"kind": "migration",
                            "title": f"Assisted migration: {best['name']}",
                            "detail": f"{best['distance_km']} km away; the stock stays below the "
                                      f"breeding limit from {TRANSLOCATION_YEAR} to {END_YEAR} "
                                      f"(2100 stress {best['stress_2100']:.2f}). "
                                      f"{len(refuges)} refuge site(s) found."})
        elif future:
            best = future[0]
            actions.append({"kind": "migration",
                            "title": f"Future refuge: {best['name']} from {best['viable_from']}",
                            "detail": f"Too cold for the stock today but suitable from "
                                      f"{best['viable_from']}; protect the corridor "
                                      f"({best['distance_km']} km) now."})
        else:
            actions.append({"kind": "ex-situ", "title": "No climate refuge surveyed",
                            "detail": "None of the surveyed sites stays inside the tolerance "
                                      "to 2100. Prioritise captive or seed-bank insurance."})
    if plan["scenario"]["pressure"] >= 0.7 and plan["viable_today"]:
        actions.append({"kind": "habitat", "title": "Protect microrefugia and corridors",
                        "detail": f"Warming runs at {plan['scenario']['pressure'] * 100:.0f}% "
                                  "of the evolutionary speed limit. Shade, water and connected "
                                  "habitat buy time for adaptation."})
    if not plan["in_reference_domain"] and not lenses_disagree:
        actions.append({"kind": "verify", "title": "Run the live simulation check",
                        "detail": "This organism or climate lies outside the measured "
                                  "reference; confirm with 'vikasa risk check --live'."})
    if not actions or (fails is None and plan["tier"] == "low"):
        actions.append({"kind": "monitor", "title": "Routine monitoring",
                        "detail": "Keeps pace under this pathway. Re-run the plan every five "
                                  "years with new climate data."})
    return actions


def plan_species(place: str | RegionClimate, *, generation_years: float,
                 tolerance: str | float = "local", ssp: str = "SSP5-8.5",
                 name: str = "", habitat: str = "any",
                 sites: list[RegionClimate] | None = None,
                 reference: dict[str, Any] | None = None) -> dict[str, Any]:
    """Full conservation plan for one species at one place."""
    region = place if isinstance(place, RegionClimate) else find_place(place)
    reference = reference or load_reference()
    critical = reference["heritable"]["critical_rate"]
    breadth = resolve_breadth(region, tolerance)
    estimate = instant_estimate(region, generation_years=generation_years,
                                tolerance=breadth, ssp=ssp, reference=reference)
    sites = habitat_sites(sites if sites is not None else candidate_sites(), habitat)
    common = {"generation_years": generation_years, "breadth_c": breadth, "critical": critical}
    with_evo = trajectory(region, ssp=ssp, **common)
    without = trajectory(region, ssp=ssp, evolving=False, **common)
    pathways = {}
    for name_ssp in SSP_WARMING:
        series = trajectory(region, ssp=name_ssp, **common)
        pathways[name_ssp] = {
            "breeding_fails": breeding_fails(series),
            "p_with_evolution": estimate["scenarios"][name_ssp]["p_with_evolution"],
            "pressure": estimate["scenarios"][name_ssp]["pressure"]}
    shift = gene_flow_needed(region, ssp=ssp, **common)
    viable_today = estimate["seasonal"]["status"] != "not viable"
    p_survive = estimate["survival_probability"]
    fails = breeding_fails(with_evo)
    score, tier = _priority(viable_today, p_survive, fails)
    plan: dict[str, Any] = {
        "species": name or f"{generation_years:g}-year species",
        "place": {"key": region.key, "name": region.name, "latitude": region.latitude,
                  "longitude": region.longitude, "annual_mean_c": region.annual_mean_c,
                  "seasonal_amplitude_c": region.seasonal_amplitude_c},
        "organism": {"generation_years": generation_years, "tolerance": tolerance,
                     "breadth_c": round(breadth, 3), "habitat": (habitat or "any").lower()},
        "ssp": ssp,
        "verdict": estimate["verdict"],
        "survival_probability": p_survive,
        "p_without_evolution": estimate["scenario"]["p_without_evolution"],
        "viable_today": viable_today,
        "scenario": {key: estimate["scenario"][key] for key in (
            "rate_c_per_generation", "pressure", "critical_generation_years")},
        "in_reference_domain": estimate["in_reference_domain"],
        "timeline": {
            "years": [START_YEAR, END_YEAR],
            "stress_with_evolution": [round(v, 4) for v in with_evo],
            "stress_without_evolution": [round(v, 4) for v in without],
            "breeding_fails_with_evolution": None if not viable_today else fails,
            "breeding_fails_without_evolution": None if not viable_today
            else breeding_fails(without),
            "years_bought_by_evolution": _years_bought(with_evo, without),
        },
        "pathways": pathways,
        "gene_flow": {"shift_c": shift,
                      "donors": find_donors(region, sites, shift) if shift else []},
        "refuges": find_refuges(region, sites, ssp=ssp, **common),
        "priority": score, "tier": tier,
    }
    plan["actions"] = _actions(plan)
    return plan


def _years_bought(with_evo: list[float], without: list[float]) -> int | None:
    a, b = breeding_fails(with_evo), breeding_fails(without)
    if b is None:
        return 0
    return (END_YEAR + 1 if a is None else a) - b


# --------------------------------------------------------------------------- watchlist

WATCHLIST_COLUMNS = ("species", "place", "generation_years", "tolerance", "habitat", "ssp",
                     "notes")


def read_watchlist(text: str) -> list[dict[str, str]]:
    """Parse watchlist CSV text; header names are case-insensitive."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames is None:
        raise ValueError("The watchlist is empty")
    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [col for col in ("species", "place", "generation_years") if col not in fields]
    if missing:
        raise ValueError(f"Watchlist CSV needs the columns: {', '.join(missing)} "
                         f"(optional: tolerance, habitat, ssp, notes)")
    rows = []
    for raw in reader:
        row = {col: (raw.get(fields[col]) or "").strip() for col in WATCHLIST_COLUMNS
               if col in fields}
        if row.get("species") or row.get("place"):
            rows.append(row)
    if not rows:
        raise ValueError("The watchlist has a header but no species")
    if len(rows) > 200:
        raise ValueError("At most 200 species per watchlist")
    return rows


def _tolerance(value: str) -> str | float:
    if not value:
        return "local"
    try:
        return float(value)
    except ValueError:
        return value.lower()


def triage(rows: list[dict[str, str]], *, ssp: str = "SSP5-8.5",
           extra_places: Iterable[RegionClimate] = (),
           allow_paths: bool = True) -> dict[str, Any]:
    """Assess every watchlist row and rank them by conservation priority."""
    if ssp not in SSP_WARMING:
        raise ValueError(f"Unknown SSP {ssp!r}; use one of {', '.join(SSP_WARMING)}")
    extra = list(extra_places)
    sites = candidate_sites(extra)
    reference = load_reference()
    plans, errors = [], []
    for index, row in enumerate(rows, start=1):
        label = row.get("species") or f"Row {index}"
        try:
            plan = plan_species(find_place(row.get("place", ""), extra,
                                           allow_paths=allow_paths),
                                generation_years=float(row.get("generation_years") or "nan"),
                                tolerance=_tolerance(row.get("tolerance", "")),
                                ssp=row.get("ssp") or ssp, name=label, sites=sites,
                                habitat=row.get("habitat") or "any",
                                reference=reference)
            plan["notes"] = row.get("notes", "")
            plans.append(plan)
        except (ValueError, KeyError) as exc:
            errors.append({"row": index, "species": label, "error": str(exc)})
    plans.sort(key=lambda p: (-p["priority"], p["species"].lower()))
    for rank, plan in enumerate(plans, start=1):
        plan["rank"] = rank
    counts = {tier: sum(1 for p in plans if p["tier"] == tier) for tier, _ in TIERS}
    fails = sorted(p["timeline"]["breeding_fails_with_evolution"] for p in plans
                   if p["timeline"]["breeding_fails_with_evolution"])
    return {
        "schema": SCHEMA, "ssp": ssp, "species_count": len(plans), "tiers": counts,
        "earliest_failure": fails[0] if fails else None,
        "with_refuge": sum(1 for p in plans if any(r["status"] == "refuge"
                                                   for r in p["refuges"])),
        "needs_action": sum(1 for p in plans if p["tier"] in ("critical", "high")),
        "sites_surveyed": len(sites),
        "sites": [{"key": s.key, "name": s.name, "latitude": s.latitude,
                   "longitude": s.longitude, "annual_mean_c": round(s.annual_mean_c, 2)}
                  for s in sites],
        "plans": plans, "errors": errors, "note": PLANNER_NOTE,
        "source": load_reference()["source"],
    }


def to_csv(result: dict[str, Any]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["rank", "species", "place", "tier", "priority", "verdict",
                     "survival_probability", "breeding_fails_with_evolution",
                     "breeding_fails_without_evolution", "gene_flow_shift_c",
                     "best_refuge", "refuge_distance_km", "first_action"])
    for plan in result["plans"]:
        refuge = next((r for r in plan["refuges"] if r["status"] == "refuge"), None)
        timeline = plan["timeline"]
        writer.writerow([
            plan["rank"], plan["species"], plan["place"]["name"], plan["tier"],
            plan["priority"], plan["verdict"], f"{plan['survival_probability']:.3f}",
            timeline["breeding_fails_with_evolution"] or "",
            timeline["breeding_fails_without_evolution"] or "",
            "" if plan["gene_flow"]["shift_c"] is None else plan["gene_flow"]["shift_c"],
            refuge["name"] if refuge else "", refuge["distance_km"] if refuge else "",
            plan["actions"][0]["title"] if plan["actions"] else ""])
    return out.getvalue()


# --------------------------------------------------------------------------- report

def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


SPARK_FLOOR = 0.2


def _y(value: float, height: int, pad: int) -> float:
    """Stress to a y coordinate; the axis starts at 0.2 so trends are visible."""
    fraction = (min(1.0, max(SPARK_FLOOR, value)) - SPARK_FLOOR) / (1.0 - SPARK_FLOOR)
    return height - pad - fraction * (height - 2 * pad)


def _spark(plan: dict[str, Any], width: int = 240, height: int = 60) -> str:
    timeline = plan["timeline"]
    pad = 4

    def path(values: list[float]) -> str:
        n = len(values) - 1
        return " ".join(f"{'M' if i == 0 else 'L'}{pad + i * (width - 2 * pad) / n:.1f},"
                        f"{_y(v, height, pad):.1f}"
                        for i, v in enumerate(values))

    limit_y = _y(FAIL_STRESS, height, pad)
    marks = ""
    fails = timeline["breeding_fails_with_evolution"]
    if fails:
        x = pad + (fails - START_YEAR) * (width - 2 * pad) / (END_YEAR - START_YEAR)
        marks = (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pad}" y2="{height - pad}" '
                 f'class="fail"/>')
    return (f'<svg viewBox="0 0 {width} {height}" class="spark" role="img" '
            f'aria-label="Heat stress 2025 to 2100">'
            f'<rect x="{pad}" y="{pad}" width="{width - 2 * pad}" '
            f'height="{limit_y - pad:.1f}" class="danger"/>'
            f'<line x1="{pad}" x2="{width - pad}" y1="{limit_y:.1f}" y2="{limit_y:.1f}" '
            f'class="limit"/>{marks}'
            f'<path d="{path(timeline["stress_without_evolution"])}" class="noevo"/>'
            f'<path d="{path(timeline["stress_with_evolution"])}" class="evo"/></svg>')


def _map(result: dict[str, Any], width: int = 520, height: int = 600) -> str:
    sites = result["sites"]
    lats = [s["latitude"] for s in sites]
    lons = [s["longitude"] for s in sites]
    lat0, lat1 = min(lats) - 1.5, max(lats) + 1.5
    lon0, lon1 = min(lons) - 1.5, max(lons) + 1.5
    scale = min((width - 40) / (lon1 - lon0), (height - 40) / (lat1 - lat0))

    def xy(lat: float, lon: float) -> tuple[float, float]:
        return 20 + (lon - lon0) * scale, 20 + (lat1 - lat) * scale

    temps = [s["annual_mean_c"] for s in sites]
    t0, t1 = min(temps), max(temps)
    parts = []
    for plan in result["plans"]:
        refuge = next((r for r in plan["refuges"] if r["status"] == "refuge"), None)
        if refuge:
            x1, y1 = xy(plan["place"]["latitude"], plan["place"]["longitude"])
            x2, y2 = xy(refuge["latitude"], refuge["longitude"])
            parts.append(f'<path d="M{x1:.1f},{y1:.1f} Q{(x1 + x2) / 2 - (y2 - y1) * .25:.1f},'
                         f'{(y1 + y2) / 2 + (x2 - x1) * .25:.1f} {x2:.1f},{y2:.1f}" '
                         f'class="route t-{plan["tier"]}"><title>{_e(plan["species"])}: '
                         f'{_e(plan["place"]["name"])} → {_e(refuge["name"])}</title></path>')
    homes = {p["place"]["key"] for p in result["plans"]}
    for site in sites:
        x, y = xy(site["latitude"], site["longitude"])
        f = 0.0 if t1 == t0 else (site["annual_mean_c"] - t0) / (t1 - t0)
        hue = round(210 - 200 * f)
        ring = ' class="home"' if site["key"] in homes else ""
        parts.append(f'<g{ring}><circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" '
                     f'fill="hsl({hue} 70% 58%)"><title>{_e(site["name"])}: '
                     f'{site["annual_mean_c"]:.1f} °C today</title></circle>'
                     f'<text x="{x + 9:.1f}" y="{y + 4:.1f}">{_e(site["name"].split(" (")[0])}'
                     f'</text></g>')
    return (f'<svg viewBox="0 0 {width} {height}" class="map" role="img" '
            f'aria-label="Surveyed sites and assisted-migration routes">{"".join(parts)}</svg>')


REPORT_CSS = """
:root{--bg:#061015;--card:#0e222b;--edge:#7be0c22e;--ink:#eef4ef;--muted:#9db9b8;--dim:#6f8b88;
--accent:#f0cd8a;--teal:#7be0c2;--rose:#f1a07c;--crit:#ff6b6b;--high:#f1a07c;--watch:#f0cd8a;--low:#8fdc8a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 "Segoe UI",system-ui,sans-serif}
main{max-width:1180px;margin:0 auto;padding:30px 24px 60px}
h1{font-size:30px;margin:0 0 4px;letter-spacing:-.3px}h2{font-size:19px;margin:34px 0 12px}
.sub{color:var(--muted)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:12px;margin:22px 0}.kpi{background:var(--card);border:1px solid var(--edge);border-radius:14px;
padding:14px 16px}.kpi b{display:block;font-size:28px}.kpi span{color:var(--muted);font-size:13px}
.split{display:grid;grid-template-columns:minmax(300px,520px) 1fr;gap:20px;align-items:start}
@media(max-width:900px){.split{grid-template-columns:1fr}}
.routes{display:grid;gap:8px}.route-row{background:var(--card);border:1px solid var(--edge);
border-radius:12px;padding:10px 14px;display:grid;grid-template-columns:1fr auto;gap:2px 12px}
.route-row b{font-size:14.5px}.route-row .sub{font-size:13px}.route-row .km{color:var(--accent);
font-weight:700;align-self:center;grid-row:span 2;font-size:15px}
.wrap{overflow-x:auto;border-radius:14px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:14px;overflow:hidden}
th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--edge);font-size:14px;
vertical-align:middle}th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;
letter-spacing:.6px}.tier{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;
font-weight:700;color:#071318;white-space:nowrap}.t-critical{background:var(--crit)}
.t-high{background:var(--high)}
.t-watch{background:var(--watch)}.t-low{background:var(--low)}
.spark{width:240px;height:60px;display:block}.spark .danger{fill:#ff6b6b14}
.spark .limit{stroke:#ff6b6b88;
stroke-dasharray:3 3}.spark .fail{stroke:#ff6b6b;stroke-width:1.5}.spark path{fill:none;
stroke-width:2}.spark .evo{stroke:var(--teal)}.spark .noevo{stroke:var(--rose);opacity:.7;
stroke-dasharray:4 3}
.map{width:100%;background:var(--card);border:1px solid var(--edge);border-radius:14px}
.map text{fill:var(--muted);font-size:10.5px}.map .home circle{stroke:#fff;stroke-width:2}
.map .route{fill:none;stroke-width:2.2;opacity:.85}.map path.t-critical{stroke:var(--crit)}
.map path.t-high{stroke:var(--high)}.map path.t-watch{stroke:var(--watch)}
.map path.t-low{stroke:var(--low)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--edge);border-radius:16px;padding:16px 18px}
.card h3{margin:0;font-size:17px;display:flex;gap:10px;align-items:center;
justify-content:space-between}
.card .meta{color:var(--muted);font-size:13px;margin:2px 0 10px}
.card ol{margin:8px 0 0;padding-left:20px}.card li{margin:6px 0}.card li b{display:block}
.card li span{color:var(--muted);font-size:13.5px}
.paths{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:10px 0}
.paths div{background:#ffffff08;border-radius:9px;padding:6px 8px;font-size:12px;color:var(--muted)}
.paths div b{display:block;color:var(--ink);font-size:13.5px}
.map text{paint-order:stroke;stroke:#0e222b;stroke-width:3px}
.legend{color:var(--muted);font-size:13px;margin:8px 0}.legend i{display:inline-block;width:18px;
height:3px;vertical-align:middle;margin:0 6px 0 12px}.note{color:var(--dim);font-size:13px;
margin-top:30px;border-top:1px solid var(--edge);padding-top:14px}
.errors{background:#ff6b6b18;border:1px solid #ff6b6b55;border-radius:12px;padding:10px 14px}
@media print{body{background:#fff;color:#000}
.card,.kpi,table,.map{background:#fff;border-color:#ccc}}
"""


def _fmt_year(value: int | None, viable: bool = True) -> str:
    if not viable:
        return "already"
    return "beyond 2100" if value is None else str(value)


def render_html(result: dict[str, Any]) -> str:
    """A self-contained conservation plan report (no network, no scripts)."""
    plans = result["plans"]
    rows = []
    for plan in plans:
        t = plan["timeline"]
        refuge = next((r for r in plan["refuges"] if r["status"] == "refuge"), None)
        rows.append(
            f'<tr><td>{plan["rank"]}</td><td><b>{_e(plan["species"])}</b><br>'
            f'<span class="sub">{_e(plan["place"]["name"])} · '
            f'{plan["organism"]["generation_years"]:g} y generation</span></td>'
            f'<td><span class="tier t-{plan["tier"]}">{TIER_LABELS[plan["tier"]]} '
            f'{plan["priority"]}</span></td>'
            f'<td>{plan["survival_probability"] * 100:.0f}%</td>'
            f'<td>{_fmt_year(t["breeding_fails_with_evolution"], plan["viable_today"])}</td>'
            f'<td>{_spark(plan)}</td>'
            f'<td>{_e(refuge["name"]) + f" · {refuge["distance_km"]} km" if refuge else "—"}</td>'
            f'</tr>')
    routes = []
    for plan in plans:
        refuge = next((r for r in plan["refuges"] if r["status"] == "refuge"), None)
        if refuge and plan["tier"] in ("critical", "high", "watch"):
            routes.append(
                f'<div class="route-row"><b>{_e(plan["species"])} '
                f'<span class="tier t-{plan["tier"]}">{TIER_LABELS[plan["tier"]]}</span></b>'
                f'<span class="km">{refuge["distance_km"]} km</span>'
                f'<span class="sub">{_e(plan["place"]["name"])} → {_e(refuge["name"])} · '
                f'2100 stress {refuge["stress_2100"]:.2f} · {refuge["mean_2100_c"]:.1f} °C mean '
                f'in 2100</span></div>')
    cards = []
    for plan in plans:
        t = plan["timeline"]
        paths = "".join(
            f'<div>{_e(name)}<b>{info["p_with_evolution"] * 100:.0f}% · '
            f'{_fmt_year(info["breeding_fails"], plan["viable_today"])}</b></div>'
            for name, info in plan["pathways"].items())
        actions = "".join(f'<li><b>{_e(a["title"])}</b><span>{_e(a["detail"])}</span></li>'
                          for a in plan["actions"])
        bought = t["years_bought_by_evolution"]
        bought_text = ("" if not bought else
                       f" Evolution buys <b>{bought if bought <= 75 else '75+'} years</b>.")
        cards.append(
            f'<section class="card"><h3>#{plan["rank"]} {_e(plan["species"])}'
            f'<span class="tier t-{plan["tier"]}">{TIER_LABELS[plan["tier"]]}</span></h3>'
            f'<div class="meta">{_e(plan["place"]["name"])} · generation '
            f'{plan["organism"]["generation_years"]:g} y · tolerance '
            f'{plan["organism"]["breadth_c"]:.1f} °C · {_e(plan["ssp"])} · verdict '
            f'<b>{_e(plan["verdict"])}</b></div>'
            f'{_spark(plan, 320, 80)}'
            f'<div class="meta">Breeding fails: '
            f'<b>{_fmt_year(t["breeding_fails_with_evolution"], plan["viable_today"])}</b> '
            f'with evolution, '
            f'<b>{_fmt_year(t["breeding_fails_without_evolution"], plan["viable_today"])}</b>'
            f' without.{bought_text}</div>'
            f'<div class="paths">{paths}</div>'
            f'<ol>{actions}</ol>'
            + (f'<div class="meta">{_e(plan["notes"])}</div>' if plan.get("notes") else "")
            + '</section>')
    errors = ""
    if result["errors"]:
        errors = ('<div class="errors"><b>Rows skipped</b><ul>' + "".join(
            f'<li>Row {e["row"]} ({_e(e["species"])}): {_e(e["error"])}</li>'
            for e in result["errors"]) + "</ul></div>")
    tiers = result["tiers"]
    route_html = "".join(routes) or '<div class="sub">No refuge routes in this plan.</div>'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vikasa Conservation Plan</title><style>{REPORT_CSS}</style></head>
<body><main>
<h1>Conservation Plan</h1>
<div class="sub">{result["species_count"]} species · {_e(result["ssp"])} ·
{result["sites_surveyed"]} surveyed sites · generated by Vikasa</div>
<div class="kpis">
<div class="kpi"><b style="color:var(--crit)">{tiers["critical"]}</b>
<span>critical priority</span></div>
<div class="kpi"><b style="color:var(--high)">{tiers["high"]}</b><span>high priority</span></div>
<div class="kpi"><b>{result["earliest_failure"] or "none"}</b>
<span>earliest breeding failure</span></div>
<div class="kpi"><b style="color:var(--teal)">{result["with_refuge"]}</b>
<span>species with a climate refuge</span></div>
</div>
{errors}
<h2>Priority list</h2>
<div class="legend">Heat stress 2025→2100:<i style="background:var(--teal)"></i>with evolution
<i style="background:var(--rose)"></i>without · red band = above the breeding limit</div>
<div class="wrap"><table><thead><tr><th>#</th><th>Species</th><th>Priority</th><th>Survives</th>
<th>Breeding fails</th><th>Stress to 2100</th><th>Best refuge</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<h2>Sites and migration routes</h2>
<div class="split"><div>{_map(result)}
<div class="legend">Dots coloured by today's mean temperature (blue cool → red hot); white ring =
a watchlist home; arcs = recommended assisted-migration routes, coloured by tier.</div></div>
<div class="routes">{route_html}</div></div>
<h2>Action plans</h2>
<div class="legend">Pathway tiles: survival probability with evolution · year breeding fails.</div>
<div class="cards">{"".join(cards)}</div>
<p class="note">{_e(result["note"])} Reference curve: {_e(result["source"])}.</p>
</main></body></html>
"""


def write_outputs(result: dict[str, Any], output: Path) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = {"json": output / "plan.json", "csv": output / "plan.csv",
             "html": output / "report.html"}
    paths["json"].write_text(json.dumps(result, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
    paths["csv"].write_text(to_csv(result), encoding="utf-8")
    paths["html"].write_text(render_html(result), encoding="utf-8")
    return paths


def describe(plan: dict[str, Any]) -> str:
    """Plain-text rescue plan for the command line."""
    t = plan["timeline"]
    lines = [
        f"Conservation plan · {plan['species']} · {plan['place']['name']} · {plan['ssp']}",
        f"  Priority    {TIER_LABELS[plan['tier']].upper()} ({plan['priority']}/100), "
        f"verdict {plan['verdict']}",
        f"  Survival    {plan['survival_probability'] * 100:.0f}% with evolution, "
        f"{plan['p_without_evolution'] * 100:.0f}% without",
        f"  Breeding    fails {_fmt_year(t['breeding_fails_with_evolution'], plan['viable_today'])}"
        f" with evolution, "
        f"{_fmt_year(t['breeding_fails_without_evolution'], plan['viable_today'])} without",
        "  Pathways    " + "  ".join(
            f"{name}: {_fmt_year(info['breeding_fails'], plan['viable_today'])}"
            for name, info in plan["pathways"].items()),
    ]
    shift = plan["gene_flow"]["shift_c"]
    lines.append("  Gene flow   " + ("not needed" if shift == 0 else
                                     "cannot rescue alone" if shift is None else
                                     f"+{_shift(shift)} °C heat tolerance needed"))
    refuges = [r for r in plan["refuges"] if r["status"] == "refuge"][:3]
    lines.append("  Refuges     " + (", ".join(f"{r['name']} ({r['distance_km']} km)"
                                               for r in refuges) or "none surveyed"))
    lines.append("  ACTIONS")
    lines.extend(f"   {i}. {a['title']}: {a['detail']}"
                 for i, a in enumerate(plan["actions"], start=1))
    return "\n".join(lines)


__all__ = ["PLANNER_NOTE", "breeding_fails", "candidate_sites", "describe", "distance_km",
           "find_place", "find_refuges", "gene_flow_needed", "peak_stress", "plan_species",
           "read_watchlist", "render_html", "to_csv", "trajectory", "triage", "write_outputs"]
