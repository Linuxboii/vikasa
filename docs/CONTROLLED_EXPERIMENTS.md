# Controlled experiment laboratory

Vikasa can now compare predeclared conditions across complete seed blocks and
export a self-contained, interactive evidence viewer. The laboratory measures
model counterfactuals, not real-species predictions or proof of adaptation.
It does not change, rescue or restart the separate live GUI world.

![Actual replicated weather trajectories and paired effects](images/controlled-experiments.jpg)

## Measured preview, 2026-10-08

The [complete frozen evidence package](results/weather-laboratory-2026-10-08/report.json)
contains nine completed runs: three conditions for each of seeds 2026, 7 and 41.
All reached the declared 800-tick observation horizon with zero recorded execution
or invariant failures. Extinction was retained, not rescued or dropped. The
[offline viewer](results/weather-laboratory-2026-10-08/index.html) and
[byte-hash manifest](results/weather-laboratory-2026-10-08/manifest.json) are archived alongside it.

| Seed | Condition | Final population | Deaths | Deepest living generation | Extinction tick |
|---|---|---:|---:|---:|---:|
| 2026 | Baseline | 175 | 6 | 6 | Not extinct |
| 2026 | Drought | 24 | 71 | 1 | Not extinct |
| 2026 | Storm | 0 | 82 | 0 | 369 |
| 7 | Baseline | 160 | 3 | 4 | Not extinct |
| 7 | Drought | 24 | 59 | 1 | Not extinct |
| 7 | Storm | 0 | 78 | 0 | 370 |
| 41 | Baseline | 171 | 4 | 5 | Not extinct |
| 41 | Drought | 22 | 71 | 1 | Not extinct |
| 41 | Storm | 0 | 84 | 0 | 348 |

Relative to control, mean population over every tick changed by -46.026 animals
for drought and -88.481 for storm. Exploratory paired percentile intervals were
[-49.208, -40.832] and [-94.803, -81.078], respectively. Three selected demonstration
seeds and a short horizon provide weak uncertainty coverage and no species-level
inference. Storm intensity 1.8 here denotes a severe *model parameter bundle*, not
a measured physical storm category. The planned return to seasonal conditions
does not resurrect extinct animals. The larger protocol below remains unexecuted.

## Run and inspect

From the repository root, choose a **new** output directory for each run.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m evolution_sim.cli contrast --protocol experiments/weather-contrast-preview.json --output exports/weather-preview
Start-Process (Resolve-Path exports/weather-preview/index.html).Path
```

macOS:

```bash
.venv/bin/python -m evolution_sim.cli contrast --protocol experiments/weather-contrast-preview.json --output exports/weather-preview
open exports/weather-preview/index.html
```

Linux:

```bash
.venv/bin/python -m evolution_sim.cli contrast --protocol experiments/weather-contrast-preview.json --output exports/weather-preview
xdg-open exports/weather-preview/index.html
```

The preview is three seed blocks, three conditions and 800 ticks per run. This is
a short exploratory demonstration, not a long-horizon validation study. The
larger, prospectively declared protocol uses eight seed blocks and 3,000 ticks:

```powershell
.\.venv\Scripts\python.exe -m evolution_sim.cli contrast --protocol experiments/weather-contrast.json --output exports/weather-study
Start-Process (Resolve-Path exports/weather-study/index.html).Path
```

On macOS/Linux substitute `.venv/bin/python`. The larger study may take tens of
minutes or longer on a busy laptop. Progress is printed after each seed/condition
run. Copy the generated `index.html` to another device to inspect its embedded
evidence offline; generating the experiment still requires the desktop Python
environment. The viewer is not a mobile version of the 3D simulation.

## What the viewer shows

- Select population, deepest living generation, plant energy, soil water or animal
  energy fraction. Lines are condition means; ribbons are between-seed quartiles,
  **not confidence intervals**. Intervention starts are marked on the time axis.
- Hide individual conditions, hover the graph, or use the keyboard/touch tick slider
  to inspect actual stored sample times. No invented intermediate observations
  are reported. Long drawn paths are visually thinned to roughly 600 regular
  points plus event boundaries; the slider and hover retain every stored sample.
- Select a condition and outcome to inspect each seed-pair difference, their mean,
  standard error and exploratory bootstrap interval. A positive effect means
  *more*, not automatically *better*.
- The replicate table retains extinction, births, deaths, generation and failures.
  Protocol, resolved configurations, hashes and methodological caveats are embedded.

There are no network requests, CDN dependencies or background animation. Report
text is inserted as text, not interpreted HTML. JSON embedding escapes script
terminators. On narrow screens charts and the replicate table can be panned;
the tick slider also offers a non-hover inspection route.

Some embedded browsers suppress or do not expose download events. If the viewer's
JSON download is unavailable, use the adjacent `report.json` supplied in the
package, or open the HTML in a normal desktop browser. The in-app browser checks
verified graph/filter/keyboard interactions but could not confirm its download event.

## Declared protocol and interpretation

Each JSON protocol declares a base configuration path relative to the protocol,
the complete unique seed list, horizon, sample interval, control identifier,
bootstrap seed/resample count and all condition overrides/events. Every resolved
configuration and event is validated before simulation starts. Unknown fields,
fractional/boolean seed and event times, duplicate identifiers and out-of-horizon
events are rejected instead of silently coerced.

The weather protocols share their initial configuration and seed labels. Drought
changes rainfall, productivity, resource decay, metabolism and exposure together;
storm changes movement cost, exposure, patch/plant loss and rainfall together.
Thus the comparison estimates the **configured weather bundle**, not the isolated
effect of rainfall or a particular biological mechanism. Config-override protocols
may also change initial conditions; label that distinction explicitly. Equal seed
labels do not ensure identical subsequent random draws after branches diverge.

There is no rescue, external feeding or restart. Extinction is absorbing, but
plant/water processes continue to the same declared horizon. This prevents
comparing one condition's final water at extinction with another's water thousands
of ticks later. Population is integrated every tick, independently of graph sampling.

## Mathematics

For condition `a`, control `c`, seed block `s` and fixed horizon `T`, let `N_as(t)`
be the living population after `t` engine transitions. The initial population at
tick zero is displayed but not included in this discrete post-transition integral:

```text
I_as = sum(t=1..T) N_as(t)        [animal-ticks]
M_as = I_as / T                  [animals]
D_s(Y) = Y_as - Y_cs             [units of the selected outcome]
mean_D = sum(s=1..n) D_s / n
sample_variance = sum(s=1..n) (D_s - mean_D)^2 / (n - 1)
SE(mean_D) = sqrt(sample_variance / n)
```

Extinct runs contribute zero population on subsequent ticks, not missing data.
For the hand-checked one-founder fixture that dies on transition 3, population at
ticks 1..20 is `1, 1, 0, ..., 0`; its integral is 2 and mean population is 0.1.
For differences `[-2, 0, 2]`, the mean is zero, sample variance is 4 and standard
error is `sqrt(4/3)`. The seed block—not a time point or individual animal—is the
unit of replication. Serial correlation within trajectories cannot inflate `n`.

The bootstrap draws `n` seed indices with replacement and applies those same
indices to the paired outcomes. For each draw it computes a mean difference;
the 2.5th and 97.5th percentiles of these means form the reported interval. A
separate NumPy generator with the declared bootstrap seed cannot change biology.
Index batches of 256 bound temporary bootstrap memory. Standard error above is
the analytical between-seed estimate, not the bootstrap standard deviation.
See [SciPy's primary bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)
for paired resampling and percentile-method context. Vikasa implements this small
observer calculation with NumPy and does not require SciPy.

These are marginal, unadjusted, exploratory percentile intervals. Their nominal
coverage assumes appropriate independent seed sampling and may be poor with small,
selected, skewed or extinction-heavy samples. No p-value or significance declaration
is generated. Identical observed differences can produce a collapsed interval;
this does **not** demonstrate universal certainty. With a single seed, variance,
standard error and interval are unavailable. If any pair lacks an outcome, the
entire outcome comparison is unavailable—no complete-case exclusion is hidden.

## Failures, bounded observation and provenance

Initialization, simulation or measurement failures retain their condition, seed,
stage, tick, exception type/message and any already recorded history. Remaining
declared runs continue. A failed run's endpoint outcomes are unavailable and its
condition's aggregate curves/effects are invalidated rather than treating a failed
run as zero population or omitting it. Invariant failures are also retained and
invalidate that run's outcomes. CLI exit status is 1 when either failure occurs.
Non-finite scalar observations are stored as unavailable with field/tick diagnostics,
so numerical failures do not prevent JSON failure evidence from being published.
Unexpected process termination or source/protocol edits abort publication; they
cannot be certified as a coherent completed experiment.

The protocol is bounded to 128 seeds, eight conditions, one million ticks per run,
64 events per condition, 50,000 bootstrap resamples and 250,000 stored trajectory
records. These limits do not promise a particular runtime. Automatic engine metric
history is trimmed to its latest observation in this runner; the package owns the
sampled trajectories. Lineage storage still grows with real births.

Each package contains:

- `report.json`: all replicates, sampled histories, pair effects, spread bands,
  exact extinction times, resolved protocol and software/configuration hashes.
- `index.html`: offline interactive viewer with the report embedded.
- `manifest.json`: SHA-256 hashes of the exact JSON and HTML file bytes.

Output directories are exclusively claimed and existing ones are refused. Files
are also created exclusively. `INCOMPLETE.txt` remains until publication finishes;
interrupted or partially written packages must not be treated as complete. Verify
the manifest hashes before reusing results. Preserve source and numerical platform
versions: the package source digest covers Python files, while the HTML artifact
has its own manifest hash. This fresh-process guard does not certify already
imported code or edits changed and reverted between checks.

Tracked evidence packages preserve LF line endings through `.gitattributes` so
Windows checkout conversion cannot silently invalidate their byte-hash manifests.

Broader sensitivity analysis, mechanism-isolating ablations, empirical calibration
and larger prospective validation remain part of the active research upgrade.
