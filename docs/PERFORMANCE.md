# Performance: measured work, preserved biology

The spatial index now validates each rebuilt position cloud with one NumPy
finite reduction instead of one per entity. It stores copied scalar coordinate
pairs and computes radius checks without repeatedly converting each candidate.
Sorted IDs, inclusive squared-radius comparisons and float64 coordinate values
are preserved. This changes computational overhead, not feeding, decision
frequency, reproduction, hazard, mortality, population caps or random draws.

A pre-change profile of spatial-biome seed 2026, after 150 warm-up ticks, measured
13.724 profiled seconds for the next 150 ticks. Spatial rebuilding accounted for
2.539 seconds, individual insertion 2.422 seconds, and radius queries 1.806
seconds. Profiling adds overhead: these are attribution measurements, not GUI
tick-rate predictions. Movement and decision work remain substantial bottlenecks.

## Reproduce the correctness/performance comparison

From a Git checkout with the editable environment installed, on Windows:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_spatial.py --config config\spatial-biome.json --baseline 5874e01 --seeds 2026 7 41 --warmup 150 --ticks 300 --output exports\spatial-performance-new.json
```

On macOS/Linux:

```bash
.venv/bin/python tools/benchmark_spatial.py --config config/spatial-biome.json --baseline 5874e01 --seeds 2026 7 41 --warmup 150 --ticks 300 --output exports/spatial-performance-new.json
```

Use a fresh output filename. The script loads only the old `SpatialHash` from Git
into an isolated Python namespace. All other simulation code is current for
both runs. It never checks out old files or changes the live bridge. Order
alternates between seeds to reduce simple order bias; this is not a randomized
performance experiment. Each engine starts independently from the same seed.

Reports include complete checkpoint hashes at the warm-up boundary and the final
boundary, including engine RNG, creatures, ecology, lineage and recorder state.
Matching digests test exact equality at those boundaries, not every intermediate
tick or every possible input. Invariant errors are retained and cause a failed
exit even if both implementations match. Source/config changes during measurement
reject publication. Reports record current Python source hashes, Python/NumPy
versions, platform, config, seeds, timings and execution order.

Local throughput depends on hardware, population, age/generation structure,
resource count, weather, renderer and competing processes. This benchmark does
not promise 120 ticks/s, smooth FPS on every device, or late-run performance.
Rendering fewer animals does not remove engine animals. Requested and measured
tick rates are separate values in the live bridge.

## Verified local sample, 2026-10-08

[Archived report](results/spatial-performance-2026-10-08.json), using the protocol
above on Python 3.12.14 / NumPy 2.5.3 with the existing Godot world left running:

| Seed | Historical index ticks/s | Optimized index ticks/s | Speed ratio |
|---|---:|---:|---:|
| 2026 | 20.03 | 23.97 | 1.197 |
| 7 | 21.72 | 24.94 | 1.148 |
| 41 | 20.85 | 23.83 | 1.143 |

All three pairs matched complete checkpoint digests at both boundaries; all
six runs reported no invariant errors. These selected short-run timings under
shared load indicate a local 14–20% improvement, not a confidence interval or a
universal device guarantee. The initial exploratory timing run is not this
guarded evidence package. The source hashes identify precisely measured code;
subsequent code changes make these results historical rather than current.

The already-running bridge keeps the code it imported at launch. Do not silently
restart an ongoing field study to activate an optimization: its state would be
lost. New launches load the current implementation. Preserving and restoring a
live Godot world across upgrades still requires bridge checkpoint integration.
