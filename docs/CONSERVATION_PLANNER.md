# Conservation Planner

The Species Risk Checker answers *"is this species at risk here?"* for one species.
Conservation teams (forest departments, NGOs, zoo breeding programmes, research
groups writing grant proposals) work from a **watchlist** of dozens of species and a
fixed budget. They need to know **which species to act on first, by when, and how**.
The Conservation Planner turns Vikasa's measured evolutionary-rescue results into
that decision support.

```powershell
.\.venv\Scripts\vikasa.exe plan                                         # browser app
.\.venv\Scripts\vikasa.exe plan triage examples\watchlist-india.csv --open
.\.venv\Scripts\vikasa.exe plan species --name "Olive ridley" --place Chennai `
    --generation-years 20 --habitat coastal --ssp SSP5-8.5
```

```text
Conservation plan · Olive ridley · Chennai · SSP5-8.5
  Priority    HIGH (69/100), verdict likely lost
  Survival    0% with evolution, 0% without
  Breeding    fails 2077 with evolution, 2054 without
  Pathways    SSP1-2.6: beyond 2100  SSP2-4.5: beyond 2100  SSP3-7.0: beyond 2100  SSP5-8.5: 2077
  Gene flow   +0.66 °C heat tolerance needed
  Refuges     Kochi (559 km), Sundarbans (1344 km)
  ACTIONS
   1. Assisted gene flow: +0.66 °C heat tolerance: ...
   2. Assisted migration: Kochi: 559 km away; ...
```

## What it computes

| Output | Question it answers | How |
|---|---|---|
| **Breeding-failure year** | *When* does it stop replacing itself, with and without evolution? | First-order adaptation-lag model (below), yearly 2025–2100 |
| **Pathway table** | How much does the emissions pathway matter for this species? | The same timeline and survival probability under SSP1-2.6 … SSP5-8.5 |
| **Assisted gene flow** | How much extra heat tolerance would keep it breeding to 2100, and where could it come from? | Bisection for the smallest optimum shift; donor sites warmer by at least that much |
| **Climate refuges** | Where could the stock be moved (assisted migration)? | Every surveyed site in the same habitat, scored 2030–2100 |
| **Priority and tier** | Which species first? | 0–100 score from survival probability and failure year |
| **Action list** | What to do, in order | Rules over the results above |

### The adaptation-lag model

* Climate: NASA POWER 1991–2020 monthly climatology (centred on 2005) plus the IPCC
  AR6 linear warming pathway from 2005, the same forcing the Risk Checker uses.
* The population's thermal optimum starts at the local annual mean. With evolution
  it follows warming at up to **k<sub>c</sub> / generation time** °C per year, where
  k<sub>c</sub> = 0.262 °C per generation is the critical rate measured across 216
  simulations. Warming faster than that accumulates as lag.
* Each year the worst month's stress is computed with Vikasa's own asymmetric
  thermal-performance rule (`thermal_stress`, warm side 0.6 × breadth).
* **Breeding fails** in the first year that stress exceeds 0.75: the model's breeding
  limit (0.7) plus the same ±0.05 band the seasonal screen uses for *borderline*, so a
  place that is borderline today is not reported as failing in 2025.

### Two lenses, both shown

The **survival probability** comes from the measured survival curve, which was
measured for a 4 °C tolerance and ±2.4 °C seasons. The **timeline** uses the place's
real seasons and the species' tolerance. For wide-tolerance species the two can
disagree (the curve says "likely lost", the timeline still has headroom in 2100).
The planner never hides this: it ranks the species by both, puts **"Confirm with the
live simulation"** first in its action list, and plans a refuge as a contingency. The
live check (`vikasa risk check --live`) simulates that exact place, organism and
pathway directly and is the authority.

### Refuges and donors

The translocated stock keeps its home optimum (tracking warming as before) and is
**not credited with adapting to the new site**, which makes the refuge test
conservative. A site is a:

* **refuge** if stress stays under the failure line every year 2030–2100;
* **future refuge** if it is too cold today but suitable by 2100 (protect the corridor);
* **unsuitable** otherwise.

The optional `habitat` column (`coastal`, `montane`, `inland`, `any`) limits refuges
and donors to sites of that kind, so a sea turtle is not sent inland. Donor sites
are places whose mean temperature is 0–4 °C warmer than home *plus* the needed shift:
locally adapted populations there carry roughly that optimum. They help only where
the species actually occurs.

### Priority

```
priority = 100 × (0.55 × (1 − P(survive with evolution)) + 0.45 × urgency)
urgency  = (2100 − failure year) / 75,   0 if it never fails
```

Not viable today → 100. Failure by 2050 → at least 70. Tiers: **Critical** ≥ 70,
**High** ≥ 45, **Watch** ≥ 20, **Low** below.

## Survey sites

24 places across India's thermal gradient, all real NASA POWER monthly T2M with
SHA-256 provenance: the 7 Risk Checker cities, the 3 published study regions, and 14
survey sites added for the planner (Ooty, Munnar, Kochi, Pune, Nagpur, Bhopal,
Ahmedabad, Lucknow, Guwahati, Shillong, Darjeeling, Dehradun, Srinagar, Leh) fetched
by `tools/build_survey_regions.py`. Places you fetch in the Risk Checker (any latitude
and longitude) are added to the planner automatically.

Values are for the ~50 km reanalysis grid cell, not a weather station: hill stations
read warmer than their town centre (the Ooty cell averages 23.4 °C).

## Watchlist format

| Column | Required | Meaning |
|---|---|---|
| `species` | yes | Any name |
| `place` | yes | Key (`western-ghats`), name (`Hyderabad`, `Ooty`) or region JSON path |
| `generation_years` | yes | Average parent age, 0.05–50 |
| `tolerance` | no | `specialist`, `local` (default), `generalist`, or breadth in °C |
| `habitat` | no | `coastal`, `montane`, `inland`, `any` (default) |
| `ssp` | no | Per-row pathway; otherwise the one chosen |
| `notes` | no | Carried into the report |

Up to 200 rows. Bad rows are reported and skipped, never silently dropped.

`examples/watchlist-india.csv` holds 14 Indian species. **Their generation times and
tolerances are illustrative orders of magnitude, not measured values**; replace them
with your own data before acting on the output. The resulting plan is archived in
[`docs/results/conservation-plan-india/`](results/conservation-plan-india/report.html).

## Outputs

`vikasa plan triage` writes three files to `--output` (default `exports/plan`):

* `report.html`: self-contained (no scripts, no network) report: KPIs, ranked table
  with stress sparklines, a site map with migration routes, and an action card per
  species. Prints cleanly.
* `plan.csv`: one row per species for spreadsheets.
* `plan.json`: everything, schema `vikasa-conservation-plan-v1`.

The browser app (`vikasa plan`, or the **Conservation Planner** tile on the home
screen) accepts pasted or uploaded CSV, switches pathway instantly, and downloads
all three.

## Limits

This is a **screening tool for prioritising field work**, not a substitute for it.
The organism is Vikasa's generic model; real translocation and gene flow need
species-specific ecology, disease screening, genetic compatibility checks and
permits. Rainfall, habitat loss and species interactions are not modelled.
