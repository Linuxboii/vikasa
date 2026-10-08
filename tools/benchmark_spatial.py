"""Compare spatial implementations in isolated seeded engines, never the live bridge.

Run from the checkout with its editable environment. The historical implementation
is loaded from Git into a separate namespace, not checked out over working files.
Timing is a local observation; exact checkpoint equality is the correctness gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.io.checkpoints import checkpoint_payload
from evolution_sim.model.spatial import SpatialHash
from evolution_sim.simulation import engine as engine_module


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def source_identity() -> dict:
    files = [*sorted(Path("src/evolution_sim").rglob("*.py")), Path(__file__)]
    return {str(path).replace("\\", "/"): hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for path in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/spatial-biome.json"))
    parser.add_argument("--baseline", default="5874e01")
    parser.add_argument("--seeds", type=int, nargs="+", default=[2026, 7, 41])
    parser.add_argument("--warmup", type=int, default=150)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.warmup < 0 or args.ticks < 1:
        parser.error("warmup must be non-negative and ticks positive")
    baseline_sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.baseline + "^{commit}"], text=True).strip()
    source = subprocess.check_output(
        ["git", "show", baseline_sha + ":src/evolution_sim/model/spatial.py"], text=True)
    namespace = {"__name__": "vikasa_benchmark_baseline"}
    exec(compile(source, "historical_spatial.py", "exec"), namespace)
    config = SimulationConfig.from_json(args.config)
    before = source_identity()
    config_before = args.config.read_bytes()
    runs = []
    try:
        for i, seed in enumerate(args.seeds):
            order = [("baseline", namespace["SpatialHash"]), ("optimized", SpatialHash)]
            if i % 2:
                order.reverse()
            results = {}
            for label, implementation in order:
                engine_module.SpatialHash = implementation
                engine = engine_module.SimulationEngine(config, seed)
                engine.step(args.warmup)
                checkpoints = [digest(checkpoint_payload(engine))]
                begin = time.perf_counter()
                for _ in range(args.ticks):
                    engine.step()
                elapsed = time.perf_counter() - begin
                checkpoints.append(digest(checkpoint_payload(engine)))
                results[label] = {"seconds": elapsed, "ticks_per_second": args.ticks / elapsed,
                                  "checkpoint_hashes": checkpoints,
                                  "population": len(engine.creatures),
                                  "births": engine.total_births, "deaths": engine.total_deaths,
                                  "invariant_errors": engine.audit_invariants()}
                print(f"seed {seed} {label}: {args.ticks / elapsed:.2f} ticks/s", flush=True)
            identical = results["baseline"]["checkpoint_hashes"] == results["optimized"][
                "checkpoint_hashes"]
            runs.append({"seed": seed, "order": [label for label, _ in order],
                         "results": results, "exact_checkpoint_match": identical,
                         "speedup": results["baseline"]["seconds"] /
                         results["optimized"]["seconds"]})
    finally:
        engine_module.SpatialHash = SpatialHash
    if source_identity() != before or args.config.read_bytes() != config_before:
        raise SystemExit("Source/config changed during measurement; results not published")
    report = {"baseline_commit": baseline_sha, "config": config.to_dict(),
              "warmup": args.warmup, "measured_ticks": args.ticks, "runs": runs,
              "source_hashes": before, "python": platform.python_version(),
              "platform": platform.platform(), "numpy": np.__version__,
              "comparison": "Only SpatialHash differs; all other engine modules are current.",
              "caveat": "Sequential local timings under shared system load; not a universal "
                        "FPS guarantee. Digests cover complete checkpoint state including RNG."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    if not all(run["exact_checkpoint_match"] for run in runs):
        raise SystemExit("Spatial optimization changed seeded state")
    if any(result["invariant_errors"] for run in runs for result in run["results"].values()):
        raise SystemExit("Invariant failures in benchmarked engine")


if __name__ == "__main__":
    main()
