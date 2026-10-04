# 3–5 minute demonstration script

## Prepare

```powershell
.\.venv\Scripts\python.exe main.py ui --config config/showcase.json --seed 2026
```

Keep `examples/results/environmental-shift/` open in File Explorer for the final evidence reveal.

## 0:00–0:40 — Establish the model

On the setup screen, state that the run begins with 100 randomly initialized organisms and a deterministic seed. Press `Enter`. Point out food diamonds, organism genome glyphs, movement trails, and the live evidence trace.

Say: “No score chooses winners. Food, energy, reproduction, and death create selection pressure.”

## 0:40–1:30 — Accelerate and inspect

Press `4` or `5` briefly, then `Space`. Click a successful organism. Explain size, speed hue, energy center, perception ring, six trait bars, parents, offspring, and food acquired.

## 1:30–2:30 — Show environmental pressure

Open `docs/images/pressure.png` or launch the environmental-shift scenario headlessly:

```powershell
.\.venv\Scripts\python.exe main.py run --scenario experiments/environmental_shift.json --output exports/demo-shift
```

Explain drought reducing food regeneration and heat increasing basal cost. Point to population, food, births/deaths, and normalized trait charts.

## 2:30–3:30 — Prove lineage and reproducibility

Show `lineage.csv`, the selected organism's parents, and `events.json`. Save with `Ctrl+S`, resume for a moment, then load with `Ctrl+O` to demonstrate exact continuation.

State that the checkpoint contains RNG state and fractional food remainder—not only visible entities.

## 3:30–4:30 — Open the evidence package

Open `population.png`, `traits.png`, `distributions.png`, and `summary.json` from `examples/results/environmental-shift/`. Call out the empty `invariant_errors` list and distinguish a single demonstration from replicate evidence.

## 4:30–5:00 — Close

Summarize the proof: object-oriented state, probability, vector math, spatial optimization, evolutionary trade-offs, reproducibility, visualization, statistics, persistence, and automated tests all operate in one coherent system.

