# 3–5 minute demonstration

## Prepare

Install the package and Godot 4, then run from the repo root:

```powershell
.\.venv\Scripts\vikasa.exe godot --config config\showcase.json --seed 2026
```

The Python process owns the simulation; the Godot window is its live 3D observer. If Godot is unavailable, use `vikasa ui --config config/showcase.json --seed 2026` for the 2D lab.

## 0:00–0:45 — Read the habitat

Choose **Present · 48**. Point out the actual tick rate, animal count and Observatory graphs: population/food, cumulative births/deaths and reserves/injury. Hover to inspect sampled values. The world is three-dimensional in presentation with a deterministic two-dimensional ecological engine.

Right-drag to orbit and use the wheel to zoom. Click a creature. The bottom observation dock should immediately explain its current action and reason; identify the energy, hunger, health and dominant-instinct meters.

## 0:45–1:40 — Inspect needs, not a black-box score

Select **Inspect**, expand **Instincts**, then **Action choices**. Explain that survival, foraging, mating, offspring care, danger avoidance and territory compete. The top candidate utilities are model scores, not probabilities; emergencies and persistence can override them. Expand **Encounters** to distinguish a past victory/alpha marker from a guaranteed future win.

Select **Follow** and show the creature close-up. Use **Reset view** to return to the whole habitat.

## 1:40–2:40 — Apply environmental pressure

Open **World tools**, choose **Storm**, pressure **1.4×**, duration **160 ticks**, then **Apply weather**. Watch rain appear, exposure shading enter the graphs, injury rise and vulnerable animals die. Switch to **Survival** to compare reserves, rainfall and metabolic pressure. Outcomes depend on the current state; severe sustained weather can cause extinction. Use **Restart biome** to recover.

For drought choose **25% food growth retained** and **320–480 ticks**. It erodes existing food and suppresses growth, so starvation takes time. A food bloom illustrates recovery while survivors remain. **Observe · 16**, **Present · 48**, and **Accelerate · 120** request those rates; the HUD displays the actual rate. **Space** pauses and **Step** isolates one tick.

Say: “The model represents these events as coarse multipliers and pressure signals. It is not a weather forecast or a terrain-physics simulation.”

## 2:40–3:30 — Show a controlled command-line experiment

In a terminal, run the bundled hazard protocol:

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\environmental_shift.json --output exports\demo-shift --seed 4404 --ticks 8000
```

Open the generated `summary.json` and charts. Call out the seed, event schedule and empty invariant-error list. A single run is an illustration; comparisons need replicate seeds.

## 3:30–4:20 — Explain inherited outcomes and culture carefully

Open **Genetics** to show mean inherited size/speed, perception and normalized diversity. Population means alone do not prove adaptation; inheritance and replicated comparisons matter.

Show a selected animal’s genome, parents, offspring, hunger and encounter history. Explain that offspring inherit bounded body genes and temperament, while survival and reproduction create selection. Repeated shared cues may form a named belief/ritual group under a small probabilistic rule; that is not a claim of language, theology or human religion.

## Close

Summarize: “The presentation makes the simulation legible: what the animal did, why the available model says it did so, and which needs competed. The model is deterministic for a fixed run, inspectable, and deliberately simpler than a real ecosystem.”
