"""Command-line interface for interactive and headless operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from evolution_sim.config import ConfigError, SimulationConfig
from evolution_sim.experiments.runner import (
    ContrastProtocol,
    ExperimentSpec,
    run_batch,
    run_contrast,
    run_development_study,
    run_experiment,
    run_stress,
)
from evolution_sim.experiments.scenarios import ScenarioError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vikasa",
        description="Vikasa: observe evolution in a deterministic artificial-life laboratory.",
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

    study = commands.add_parser("study", help="Measure replicated generational development")
    study.add_argument("--config", type=Path, required=True)
    study.add_argument("--seeds", type=int, nargs="+", default=[2026, 7, 41])
    study.add_argument("--ticks", type=int, default=12_000)
    study.add_argument("--sample-interval", type=int, default=500)
    study.add_argument("--output", type=Path, required=True)

    contrast = commands.add_parser("contrast", help="Compare predeclared seed-blocked conditions")
    contrast.add_argument("--protocol", type=Path, required=True)
    contrast.add_argument("--output", type=Path, required=True,
                          help="New evidence directory containing JSON and an offline viewer")

    stress = commands.add_parser("stress", help="Run invariant-audited headless ticks")
    stress.add_argument("--config", type=Path, required=True)
    stress.add_argument("--ticks", type=int, default=100_000)
    stress.add_argument("--seed", type=int, default=2026)

    ui = commands.add_parser("ui", help="Launch the interactive laboratory")
    ui.add_argument("--config", type=Path, default=Path("config/default.json"))
    ui.add_argument("--seed", type=int, default=2026)

    shortcut = commands.add_parser("shortcut", help="Install a desktop shortcut")
    shortcut.add_argument("--desktop", type=Path)
    shortcut.add_argument("--name", default="Vikasa")
    shortcut.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    shortcut.add_argument("--seed", type=int, default=2026)

    godot = commands.add_parser("godot", help="Launch the Living Biome 3D laboratory")
    godot.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    godot.add_argument("--seed", type=int, default=2026)
    godot.add_argument("--godot-path", type=str)

    bridge = commands.add_parser("serve", help="Run the local simulation bridge for Godot")
    bridge.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    bridge.add_argument("--seed", type=int, default=2026)
    bridge.add_argument("--port", type=int, default=8765)
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
        if args.command == "study":
            report = run_development_study(SimulationConfig.from_json(args.config),
                                           seeds=args.seeds, ticks=args.ticks,
                                           sample_interval=args.sample_interval)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True,
                                              allow_nan=False) + "\n", encoding="utf-8")
            aggregate = report["aggregate"]
            print(f"Study: {aggregate['survivors']}/{aggregate['replicates']} survived; "
                  f"report={args.output}")
            return 1 if aggregate["invariant_failure_replicates"] else 0
        if args.command == "contrast":
            from evolution_sim.experiments.dashboard import render_dashboard

            if args.output.exists():
                raise ValueError("Evidence directory already exists; choose a new output directory")
            protocol = ContrastProtocol.from_json(args.protocol)
            # mkdir is an exclusive claim, not a check-then-overwrite promise.
            args.output.mkdir(parents=True, exist_ok=False)
            marker = args.output / "INCOMPLETE.txt"
            marker.write_text("Run in progress or interrupted. Only a verified manifest certifies "
                              "a complete package. Choose a new directory to rerun.\n",
                              encoding="utf-8")

            def progress(row):
                print(f"Run {row['completed_runs']}/{row['total_runs']}: "
                      f"seed={row['seed']} arm={row['arm']} {row['status']}", flush=True)

            report = run_contrast(protocol, progress=progress)
            artifacts = {"report.json": json.dumps(report, indent=2, sort_keys=True,
                                                     allow_nan=False) + "\n",
                         "index.html": render_dashboard(report)}
            for filename, content in artifacts.items():
                with (args.output / filename).open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(content)
            manifest = {"schema": "vikasa-contrast-package-v1",
                        "sha256": {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                                   for name, content in artifacts.items()}}
            with (args.output / "manifest.json").open("x", encoding="utf-8",
                                                      newline="\n") as handle:
                handle.write(json.dumps(manifest, indent=2) + "\n")
            marker.unlink()
            print(f"Compared {len(report['replicates'])} runs; viewer={args.output / 'index.html'}")
            return 1 if (report["invariant_failure_replicates"]
                         or report["execution_failure_replicates"]) else 0
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
        if args.command == "shortcut":
            from evolution_sim.shortcut import install_desktop_shortcut

            shortcut = install_desktop_shortcut(
                desktop=args.desktop,
                name=args.name,
                config=args.config,
                seed=args.seed,
            )
            print(f"Desktop shortcut installed: {shortcut}")
            return 0
        if args.command == "godot":
            from evolution_sim.bridge import launch_godot

            return launch_godot(
                SimulationConfig.from_json(args.config),
                seed=args.seed,
                godot_path=args.godot_path,
            )
        if args.command == "serve":
            if not 1 <= args.port <= 65_535:
                raise ValueError("port must be between 1 and 65535")
            from evolution_sim.bridge import serve_bridge

            serve_bridge(
                SimulationConfig.from_json(args.config), seed=args.seed, port=args.port
            )
            return 0
    except (ConfigError, ScenarioError, OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
