from __future__ import annotations

import csv
import json

from evolution_sim.io.export import export_experiment
from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.simulation.environment import EnvironmentEvent


def test_export_writes_complete_machine_readable_package(tiny_config, tmp_path) -> None:
    engine = SimulationEngine(tiny_config, seed=44)
    engine.environment.schedule(EnvironmentEvent("heat", 5, 10, 1.4))
    engine.step(20)

    manifest = export_experiment(engine, tmp_path / "run")

    expected = {
        "config.json",
        "metrics.csv",
        "creatures.csv",
        "lineage.csv",
        "events.json",
        "summary.json",
        "evolution.json",
    }
    assert set(manifest.files) == expected
    assert all((manifest.root / name).exists() for name in expected)
    assert all(len(digest) == 64 for digest in manifest.files.values())


def test_exported_metrics_equal_internal_recorder_values(tiny_config, tmp_path) -> None:
    engine = SimulationEngine(tiny_config, seed=61)
    engine.step(10)

    manifest = export_experiment(engine, tmp_path / "run")
    with (manifest.root / "metrics.csv").open(newline="", encoding="utf-8") as stream:
        exported = list(csv.DictReader(stream))

    internal = engine.metrics.rows()
    assert len(exported) == len(internal)
    assert int(exported[-1]["tick"]) == internal[-1]["tick"]
    assert int(exported[-1]["population"]) == internal[-1]["population"]
    assert float(exported[-1]["speed_mean"]) == internal[-1]["speed_mean"]


def test_summary_is_canonical_for_equal_seeded_runs(tiny_config, tmp_path) -> None:
    first = SimulationEngine(tiny_config, seed=88)
    second = SimulationEngine(tiny_config, seed=88)
    first.step(25)
    second.step(25)

    first_manifest = export_experiment(first, tmp_path / "first")
    second_manifest = export_experiment(second, tmp_path / "second")
    first_summary = (first_manifest.root / "summary.json").read_bytes()
    second_summary = (second_manifest.root / "summary.json").read_bytes()

    assert first_summary == second_summary
    parsed = json.loads(first_summary)
    assert parsed["seed"] == 88
    assert parsed["tick"] == 25


def test_export_includes_inspectable_birth_cohorts_and_generation_depth(tiny_config, tmp_path):
    engine = SimulationEngine(tiny_config, seed=61)
    engine.step(20)
    manifest = export_experiment(engine, tmp_path / "run")
    evolution = json.loads((manifest.root / "evolution.json").read_text(encoding="utf-8"))
    assert evolution["basis"] == "birth-event Price decomposition"
    assert evolution["cohorts"] == engine.metrics.birth_cohorts
    assert evolution["cohort_retention_limit"] == 512
    with (manifest.root / "creatures.csv").open(newline="", encoding="utf-8") as stream:
        creatures = list(csv.DictReader(stream))
    for creature in creatures:
        assert int(creature["generation"]) == engine.lineage.generation_of(int(creature["id"]))
