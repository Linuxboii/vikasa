# Observatory presentation validation

The live UI exposes real histories from the deterministic engine: population/food,
cumulative births/deaths, mean energy/injury, temperature/rainfall, food/metabolic
pressure, inherited mean traits and genetic diversity. Weather intervals are shaded.
Graphs retain at most 180 samples and HTTP history payloads at most 240 samples.
No placeholder trend data is used.

## Runtime evidence, 2026-10-06

- Host: Intel Iris Xe integrated graphics, Windows, Godot 4.7.2 Compatibility renderer.
- `config/showcase.json`, seed 2026, complete 1600×900 3D client open.
- Accelerate requested 120 ticks/second; 526 ticks completed in 12.14 seconds:
  **43.3 actual ticks/second**, with 75 living creatures and 11 births.
- A storm at intensity 1.4 for 160 ticks started at tick 537. At tick 684,
  24 animals remained, with 48 environmental-exposure deaths and 3 starvation deaths.
  The event was still active in the screenshot. This is a controlled intervention,
  not a claim that all runs naturally experience that storm.
- Real screenshots cover overview, genetics, selected-creature information, active
  storm and a 960×600 layout. Layout capture asserts panels remain within the viewport.
- Dedicated regression tests compare a seeded wildfire treatment with an unexposed
  control, verify existing-food erosion and confirm published HTTP states remain
  available even while the simulation lock is held.
- Final verification: 269 Python tests passed; Ruff passed; Godot editor parsing,
  scene-contract smoke checks and the creature-view harness passed.

Requested and achieved tick rates are distinct; slower machines automatically skip
catch-up debt. Rendering stays bounded at 180 animals and 240 food patches, with one
simple body shadow per animal and shared geometry. Above 40 animals, cognition is
deterministically staggered over six ticks. The 30 FPS drawing ceiling, batched
vegetation and vectorized diversity calculation preserve CPU/GPU headroom.

## Presentation walkthrough

Use Present (48 requested ticks/second), then pause to explain the charts. Apply a
160-tick storm at 1.4×, inspect survival trends and cause-of-death totals, and use
Restart biome to repeat with the same seed. See [DEMO_SCRIPT.md](DEMO_SCRIPT.md).
The numerical model and its assumptions are in [SCIENTIFIC_MODEL.md](SCIENTIFIC_MODEL.md)
and [MATHEMATICS.md](MATHEMATICS.md).

Chart drawing and batched vegetation follow Godot's official
[custom drawing](https://docs.godotengine.org/en/stable/tutorials/2d/custom_drawing_in_2d.html)
and [MultiMesh guidance](https://docs.godotengine.org/en/stable/tutorials/performance/using_multimesh.html).
