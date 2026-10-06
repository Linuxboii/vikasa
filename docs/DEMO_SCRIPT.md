# 3–5 minute demonstration

## Prepare

Install the package and Godot 4, then run from the repo root:

```powershell
.\.venv\Scripts\vikasa.exe godot --config config\showcase.json --seed 2026
```

The Python process owns the simulation; the Godot window is its live 3D observer. If Godot is unavailable, use `vikasa ui --config config/showcase.json --seed 2026` for the 2D lab.

## 0:00–0:45 — Read the habitat

Point out the seasonal indicator, animal count and weather status. Say: “The world is three-dimensional in presentation; the underlying ecological engine is a deterministic two-dimensional model. It tracks explicit resources, needs and ancestry.”

Right-drag to orbit and use the wheel to zoom. Click a creature. The bottom observation dock should immediately explain its current action and reason; identify the energy, hunger, health and dominant-instinct meters.

## 0:45–1:40 — Inspect needs, not a black-box score

Select **Inspect**, expand **Instincts**, then **Action choices**. Explain that survival, foraging, mating, offspring care, danger avoidance and territory compete. The top candidate utilities are model scores, not probabilities; emergencies and persistence can override them. Expand **Encounters** to distinguish a past victory/alpha marker from a guaranteed future win.

Select **Follow** and show the creature close-up. Use **Reset view** to return to the whole habitat.

## 1:40–2:40 — Apply environmental pressure

Open **World tools** and schedule a storm or drought, using a moderate duration/intensity. Keep the animal selected if it remains alive; observe the changed season/weather, behavior reason, and needs. Use **Space** to pause and **Step** once to show that one deterministic tick advances while paused. **Natural**, **Fast**, and **Very fast** choose 8/24/60 ticks per second.

Say: “The model represents these events as coarse multipliers and pressure signals. It is not a weather forecast or a terrain-physics simulation.”

## 2:40–3:30 — Show a controlled command-line experiment

In a terminal, run the bundled hazard protocol:

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\environmental_shift.json --output exports\demo-shift --seed 4404 --ticks 8000
```

Open the generated `summary.json` and charts. Call out the seed, event schedule and empty invariant-error list. A single run is an illustration; comparisons need replicate seeds.

## 3:30–4:20 — Explain inherited outcomes and culture carefully

Show a selected animal’s genome, parents, offspring, hunger and encounter history. Explain that offspring inherit bounded body genes and temperament, while survival and reproduction create selection. Repeated shared cues may form a named belief/ritual group under a small probabilistic rule; that is not a claim of language, theology or human religion.

## Close

Summarize: “The presentation makes the simulation legible: what the animal did, why the available model says it did so, and which needs competed. The model is deterministic for a fixed run, inspectable, and deliberately simpler than a real ecosystem.”
