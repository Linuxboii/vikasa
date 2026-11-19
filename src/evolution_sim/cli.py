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

    shortcut = commands.add_parser(
        "shortcut", help="Install or update the Vikasa desktop shortcut")
    shortcut.add_argument("--desktop", type=Path)
    shortcut.add_argument("--name", default="Vikasa", help="Name of the main shortcut")
    shortcut.add_argument("--only", choices=("app", "biome", "demo", "risk"), action="append",
                          help="Which shortcut to install (repeatable; default: app, the "
                               "single Vikasa home screen)")
    shortcut.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    shortcut.add_argument("--seed", type=int, default=2026)

    godot = commands.add_parser("godot", help="Launch the Living Biome 3D laboratory")
    godot.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    godot.add_argument("--seed", type=int, default=2026)
    godot.add_argument("--godot-path", type=str)
    godot.add_argument("--demo", action="store_true",
                       help="Start the 3D client on presentation autopilot")

    app = commands.add_parser(
        "app", help="Open Vikasa: one home screen for the 3D biome, Risk Checker and Demo mode")
    app.add_argument("--port", type=int, default=8787)
    app.add_argument("--no-browser", action="store_true")

    demo = commands.add_parser(
        "demo", help="Presenter Demo mode: guided showcase with one-click launches")
    demo.add_argument("--port", type=int, default=8787)
    demo.add_argument("--no-browser", action="store_true")
    demo.add_argument("--biome-only", action="store_true",
                      help="Skip the presenter hub and open the 3D biome on autopilot")
    demo.add_argument("--godot-path", type=str)

    risk = commands.add_parser(
        "risk", help="Species Risk Checker: will a species keep up with warming here?")
    risk.add_argument("--port", type=int, default=8787)
    risk.add_argument("--no-browser", action="store_true")
    risk_commands = risk.add_subparsers(dest="risk_command")
    check = risk_commands.add_parser("check", help="Print an assessment in the terminal")
    check.add_argument("--place", default="hyderabad",
                       help="Bundled place key or a region JSON from 'vikasa climate fetch'")
    check.add_argument("--generation-years", type=float, default=1.0)
    check.add_argument("--tolerance", default="local",
                       help="specialist, local, generalist, or a breadth in °C")
    check.add_argument("--ssp", default="SSP5-8.5")
    check.add_argument("--live", action="store_true",
                       help="Also run the direct simulation check (about a minute)")
    check.add_argument("--seeds", type=int, default=4)
    check.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    risk_commands.add_parser("places", help="List the bundled places")

    plan = commands.add_parser(
        "plan", help="Conservation Planner: triage a species watchlist into an action plan")
    plan.add_argument("--port", type=int, default=8787)
    plan.add_argument("--no-browser", action="store_true")
    plan_commands = plan.add_subparsers(dest="plan_command")
    plan_triage = plan_commands.add_parser(
        "triage", help="Rank a watchlist CSV and write JSON, CSV and an HTML report")
    plan_triage.add_argument("watchlist", type=Path,
                             help="CSV with species, place, generation_years "
                                  "[, tolerance, habitat, ssp, notes]")
    plan_triage.add_argument("--ssp", default="SSP5-8.5")
    plan_triage.add_argument("--output", type=Path, default=Path("exports/plan"))
    plan_triage.add_argument("--open", action="store_true", help="Open the HTML report")
    plan_one = plan_commands.add_parser("species", help="Rescue plan for one species")
    plan_one.add_argument("--name", default="")
    plan_one.add_argument("--place", default="hyderabad",
                          help="Place key, place name, or a region JSON")
    plan_one.add_argument("--generation-years", type=float, default=1.0)
    plan_one.add_argument("--tolerance", default="local",
                          help="specialist, local, generalist, or a breadth in °C")
    plan_one.add_argument("--habitat", default="any",
                          choices=("any", "coastal", "montane", "inland"),
                          help="Only consider refuges and donors in this habitat")
    plan_one.add_argument("--ssp", default="SSP5-8.5")
    plan_one.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    bridge = commands.add_parser("serve", help="Run the local simulation bridge for Godot")
    bridge.add_argument("--config", type=Path, default=Path("config/showcase.json"))
    bridge.add_argument("--seed", type=int, default=2026)
    bridge.add_argument("--port", type=int, default=8765)

    commands.add_parser(
        "climate", add_help=False,
        help="Evolutionary rescue under real climate warming (see 'vikasa climate --help')")
    return parser


def _risk(args: argparse.Namespace) -> int:
    from evolution_sim.climate import risk

    if args.risk_command is None:
        from evolution_sim.climate.risk_app import serve

        return serve(page="/risk", port=args.port, open_browser=not args.no_browser)
    if args.risk_command == "places":
        for place in risk.places():
            print(f"{place['key']:<14} {place['name']:<24} mean {place['annual_mean_c']:5.1f} °C"
                  f"  seasons ±{place['seasonal_amplitude_c']:4.1f} °C  ({place['kind']})")
        return 0
    try:
        tolerance: str | float = float(args.tolerance)
    except ValueError:
        tolerance = args.tolerance
    estimate = risk.instant_estimate(args.place, generation_years=args.generation_years,
                                     tolerance=tolerance, ssp=args.ssp)
    live = None
    if args.live:
        print("Running the live simulation check ...", file=sys.stderr, flush=True)
        job = risk.LiveChecks().start(args.place, generation_years=args.generation_years,
                                      tolerance=tolerance, ssp=args.ssp, seeds=args.seeds,
                                      run_inline=True)
        live = job.snapshot()
        if live["status"] != "done":
            raise RuntimeError(live["error"] or "live check failed")
    if args.json:
        print(json.dumps({"estimate": estimate, "live": live}, indent=2, allow_nan=False))
        return 0
    print(risk.describe(estimate))
    if live is not None:
        direct = live["result"]["direct"]
        print(f"  LIVE CHECK  {direct['survived']}/{direct['n']} populations survived to "
              f"{live['result']['plan']['simulated_end_year']:.0f} -> "
              f"{live['result']['verdict'].upper()} ({live['elapsed_seconds']:.0f} s)")
    return 0


def _plan(args: argparse.Namespace) -> int:
    from evolution_sim.climate import planner

    if args.plan_command is None:
        from evolution_sim.climate.risk_app import serve

        return serve(page="/plan", port=args.port, open_browser=not args.no_browser)
    if args.plan_command == "species":
        try:
            tolerance: str | float = float(args.tolerance)
        except ValueError:
            tolerance = args.tolerance
        result = planner.plan_species(args.place, generation_years=args.generation_years,
                                      tolerance=tolerance, ssp=args.ssp, name=args.name,
                                      habitat=args.habitat)
        print(json.dumps(result, indent=2, allow_nan=False) if args.json
              else planner.describe(result))
        return 0
    rows = planner.read_watchlist(args.watchlist.read_text(encoding="utf-8"))
    result = planner.triage(rows, ssp=args.ssp)
    paths = planner.write_outputs(result, args.output)
    tiers = result["tiers"]
    print(f"Conservation plan · {result['species_count']} species · {result['ssp']}")
    print(f"  critical {tiers['critical']}  high {tiers['high']}  watch {tiers['watch']}  "
          f"low {tiers['low']}  ·  earliest breeding failure "
          f"{result['earliest_failure'] or 'none by 2100'}")
    for plan in result["plans"]:
        first = plan["actions"][0]["title"] if plan["actions"] else ""
        print(f"  {plan['rank']:>2}. {plan['tier'].upper():<8} {plan['priority']:>3}  "
              f"{plan['species'][:30]:<30} {plan['place']['name'][:18]:<18} {first}")
    for error in result["errors"]:
        print(f"  skipped row {error['row']} ({error['species']}): {error['error']}")
    for kind, path in paths.items():
        print(f"  {kind:<5}{path}")
    if args.open:
        import webbrowser

        webbrowser.open(paths["html"].resolve().as_uri())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["climate"]:
        from evolution_sim.climate.cli import main as climate_main

        return climate_main(arguments[1:])
    args = build_parser().parse_args(arguments)
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
            from evolution_sim.shortcut import install_shortcut_set

            installed = install_shortcut_set(
                desktop=args.desktop,
                name=args.name,
                config=args.config,
                seed=args.seed,
                modes=tuple(args.only or ("app",)),
            )
            for shortcut in installed:
                print(f"Desktop shortcut installed: {shortcut}")
            return 0
        if args.command == "godot":
            from evolution_sim.bridge import launch_godot

            return launch_godot(
                SimulationConfig.from_json(args.config),
                seed=args.seed,
                godot_path=args.godot_path,
                user_args=["--demo"] if args.demo else None,
            )
        if args.command == "app":
            from evolution_sim.climate.risk_app import serve

            return serve(page="/", port=args.port, open_browser=not args.no_browser)
        if args.command == "demo":
            if args.biome_only:
                from evolution_sim.bridge import launch_godot

                return launch_godot(
                    SimulationConfig.from_json(Path("config/showcase.json")), seed=2026,
                    godot_path=args.godot_path, user_args=["--demo"])
            from evolution_sim.climate.risk_app import serve

            return serve(page="/demo", port=args.port, open_browser=not args.no_browser)
        if args.command == "risk":
            return _risk(args)
        if args.command == "plan":
            return _plan(args)
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
