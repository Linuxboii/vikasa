# Spatial plant-water ecology

![Actual spatial-biome data and interactive cell map](images/spatial-ecology.png)

Screenshot: a real seed-2026 run with rainfall coefficient 0.004; no fixture
population, trend data or field values were used. It was captured while the
independent study and regression suite also used the machine, not as a benchmark.

The research profile `config/spatial-biome.json` introduces a finite 24 by 16
plant-energy field coupled to soil-water buckets. It is an inspectable conceptual
model, not a calibrated species, hydrological solver or closed thermodynamic
model. The sustained showcase remains the default while this profile undergoes
longitudinal and sensitivity tests.

## Run and inspect

From the repository root after the README installation steps:

```powershell
.\.venv\Scripts\python.exe -m evolution_sim.cli godot --config config/spatial-biome.json --seed 2026
.\.venv\Scripts\python.exe -m evolution_sim.cli study --config config/spatial-biome.json --seeds 2026 7 41 --ticks 12000 --output exports/spatial-biome-study.json
```

macOS/Linux use `.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.
Close an existing GUI instance before starting another on the default bridge port.
Open **Ecology**: the three graphs report plant/water fractions, finite plant
reserves, and cumulative growth/harvest/weather losses. Scroll down for the
interactive cell map: green means plant reserves, blue bars mean soil water;
hover reports the actual cell values. Legacy runs explicitly show no spatial field.

## Equations and units

Every tick is one simulation-time unit. Each cell carries plant energy
`B in [0,K]` and dimensionless bucket water `W in [0,1]`.
The variables are not kilograms, millimetres, days or measured animal physiology.
Rain first fills available bucket space; evaporation removes only available water.

Local growth uses an exact logistic reaction step:

```
r_local = r * food_pressure * seasonal_productivity
          * exp(-((temperature - 0.6)/0.35)^2) * W/(h + W)
B_growth = K*B / (B + (K-B)*exp(-r_local)) - B
water_used = transpiration_rate * B_growth / K
```

At `h=W=0`, the moisture response is defined as zero. Growth is limited to what
available water can support. Dead cells have zero growth; they recover only by
transport from neighboring living cells. Weather removes a fraction
`1-exp(-resource_decay)` of plant energy. Growth is an explicit external
photosynthetic energy input, not creation inside a closed energy budget.

Water and plant reserves then undergo a conservative five-point transport step:

```
X_next = (1-4d)*X + d*(X_north + X_south + X_east + X_west)
```

The dimensionless per-step neighbor-exchange coefficient satisfies `0<=d<=1/4`.
This convex-combination bound preserves nonnegativity and maximum values. It is
not a physical diffusivity: converting to physical units requires cell spacing
and a defined time scale. Collision worlds have no-flux edge replication; wrap
worlds have periodic neighbors. Both preserve total transported mass.

## Resource transfer and accounting

Natural food-patch placement chooses an eligible cell weighted by available plant
energy, subtracts exactly the patch energy, and places that patch inside the cell.
Low-density vegetation yields a smaller patch instead of becoming inaccessible
until it can fill a maximum-sized patch. Patch energy is the amount actually
withdrawn, never the requested maximum. A one-energy-unit minimum transfer bounds
the rendering of negligible fragments; this numerical cutoff is not plant biology.
Cells retain a one-percent seed reservoir. No eligible cell means no patch and no
random food refill. `resources.spawn_rate` limits patch presentation/transfer
attempts; it is not a supply of energy. Weather affects the plant field rather
than being applied twice to these attempt rates. Already harvested patches retain
their existing weather-decay mechanics.

Two audited identities hold for the plant and bucket reservoirs:

```
initial plants + growth - plant weather loss - harvest = current plants
initial water + actual infiltrated rain - evaporation - transpiration = current water
```

These ledgers do not account for all animal metabolism or energy already moved
into food patches. They are reservoir balances, not a whole-ecosystem energy proof.
Intentional food placement is recorded separately as `external_food_energy` and
an intervention entry; it is never described as plant growth. The latest 256
interventions persist, while the cumulative input counter retains earlier totals.

Checkpoints store both grids and ledgers and reproduce subsequent seeded dynamics.
Malformed grids, impossible initialization totals, unadvanced dynamic fluxes and
unbalanced ledgers are rejected. `habitat.json` exports grids, ledgers and current
summary and is included in the export hash manifest. CSV history retains habitat
measurements; absent legacy measurements remain unavailable.

## Evidence and limitations

The corrected living profile was tested for 6,000 ticks with seeds 2026, 7 and
41, without rescue or restart. The [complete report](results/spatial-biome-study-6000-2026-10-08.json)
includes each run's sampled trajectory, aggregated death causes, invariant-failure
summary and source/config hashes.
Its Python source hash matches the published spatial implementation.

| Seed | Living at tick 6,000 | Births | Deaths | Deepest living generation |
|---|---:|---:|---:|---:|
| 2026 | 131 | 448 | 381 | 16 |
| 7 | 130 | 374 | 308 | 11 |
| 41 | 129 | 362 | 297 | 12 |

All three runs survived with no recorded invariant failures. Deaths included
starvation, senescence and fight injuries; stable population does not mean that
individual animals are immortal. The 95% Wilson survival interval is
[0.4385, 1.0000], conditional on independent seed outcomes. These three selected
exploratory seeds do not establish indefinite survival, adaptation or a causal
weather effect. A longer horizon and controlled weather comparisons remain open.

Reproduce this exact protocol from the repository root:

```powershell
.\.venv\Scripts\python.exe -m evolution_sim.cli study --config config/spatial-biome.json --seeds 2026 7 41 --ticks 6000 --sample-interval 500 --output exports/spatial-biome-study-6000.json
```

On macOS/Linux use `.venv/bin/python` in place of the Windows interpreter path.

The first seed-2026, 1,000-tick pilot had 175 living animals, 130 births and living
generation depth 5, with no invariant failures. That short exploratory run does
not establish long-term persistence, adaptation or resistance to perturbations.
It used rainfall coefficient 0.003 and predates subsequent fixes. Live inspection
showed that this coefficient imposes net soil drying over every seasonal cycle.
The living profile now uses 0.004: with no plant transpiration or saturation,
one 384-tick seasonal cycle adds exactly 0.05952 water per cell. The arid 0.003
setting instead loses 0.15936 per cycle. Neither setting has a hidden refill.
Do not substitute it for larger predeclared replicated studies.

Tests check hand-derived logistic growth, diffusion conservation and positivity,
exact harvesting, drought response, corrupted budgets, JSON integer parameters,
checkpoint continuation and explicit external feeding. The grids are bounded to
64 by 64 cells to keep observation and vectorized dynamics practical.

This model is inspired by coupled vegetation/water modeling, but does not reproduce
the equations, calibration or ecological findings of a published model. Relevant
primary research includes [spatial vegetation and hydrology coupling](https://pmc.ncbi.nlm.nih.gov/articles/PMC4877523/)
and [water-limited vegetation with bucket soil moisture](https://pmc.ncbi.nlm.nih.gov/articles/PMC6030654/).
Nutrient cycles, terrain-driven runoff, localized storms, root feedbacks, real
plant species and empirical calibration remain open work.
