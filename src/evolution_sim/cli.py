"""Command-line interface for interactive and headless operation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evolution_sim.config import ConfigError, SimulationConfig
from evolution_sim.experiments.runner import (
    ExperimentSpec,
    run_batch,
    run_experiment,
    run_stress,
)
from evolution_sim.experiments.scenarios import ScenarioError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evolution-simulator",
        description="Explore, measure, and reproduce evolution in a 2D artificial-life laboratory.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a simulation configuration")
    validate.add_argument("--config", type=Path, required=True)

    run = commands.add_parser("run", help="Run one headless scenario")
    run.add_argument("--scenario", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--ticks", type=int)
    run.add_argument("--seed", type=int)

    batch = commands.add_parser("batch", help="Run deterministic scenario replicates")
    batch.add_argument("--scenario", type=Path, required=True)
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--replicates", type=int, default=3)
    batch.add_argument("--ticks", type=int)

    stress = commands.add_parser("stress", help="Run invariant-audited headless ticks")
    stress.add_argument("--config", type=Path, required=True)
    stress.add_argument("--ticks", type=int, default=100_000)
    stress.add_argument("--seed", type=int, default=2026)

    ui = commands.add_parser("ui", help="Launch the interactive laboratory")
    ui.add_argument("--config", type=Path, default=Path("config/default.json"))
    ui.add_argument("--seed", type=int, default=2026)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            SimulationConfig.from_json(args.config)
            print(f"Configuration is valid: {args.config}")
            return 0
        if args.command == "run":
            spec = ExperimentSpec.from_json(args.scenario).with_runtime(
                ticks=args.ticks, seed=args.seed
            )
            result = run_experiment(spec, args.output)
            print(
                f"Completed {result.engine.tick:,} ticks in {result.elapsed_seconds:.2f}s; "
                f"population={len(result.engine.creatures)}; output={result.manifest.root}"
            )
            return 0
        if args.command == "batch":
            spec = ExperimentSpec.from_json(args.scenario).with_runtime(ticks=args.ticks)
            results = run_batch(spec, output_dir=args.output, replicates=args.replicates)
            print(f"Completed {len(results)} replicates in {args.output}")
            return 0
        if args.command == "stress":
            report = run_stress(
                SimulationConfig.from_json(args.config),
                seed=args.seed,
                ticks=args.ticks,
            )
            if report.invariant_errors:
                print("Stress run failed: " + "; ".join(report.invariant_errors), file=sys.stderr)
                return 1
            print(
                f"Stress run completed {report.ticks_completed:,} ticks in "
                f"{report.elapsed_seconds:.2f}s"
            )
            return 0
        if args.command == "ui":
            from evolution_sim.ui.app import EvolutionApp

            EvolutionApp(SimulationConfig.from_json(args.config), seed=args.seed).run()
            return 0
    except (ConfigError, ScenarioError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

