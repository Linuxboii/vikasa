from __future__ import annotations

import json
from pathlib import Path

from evolution_sim.experiments.runner import ExperimentSpec, run_batch, run_experiment

ROOT = Path(__file__).resolve().parents[2]


def test_baseline_run_exports_data_and_five_charts(tmp_path) -> None:
    spec = ExperimentSpec.from_json(ROOT / "experiments" / "baseline.json")
    spec = spec.with_runtime(ticks=40, seed=17)

    result = run_experiment(spec, tmp_path / "baseline")

    assert result.engine.tick == 40
    assert result.manifest.root == tmp_path / "baseline"
    assert {path.name for path in result.charts} == {
        "population.png",
        "traits.png",
        "births_deaths.png",
        "distributions.png",
        "trait_space.png",
    }
    assert all(path.stat().st_size > 1_000 for path in result.charts)
    assert (tmp_path / "baseline" / "summary.json").exists()


def test_scenario_overrides_can_create_exportable_extinction(tmp_path) -> None:
    source = {
        "name": "extinction-test",
        "description": "No resources and immediate aging",
        "config": str(ROOT / "config" / "default.json"),
        "seed": 4,
        "ticks": 5,
        "overrides": {
            "initial_population": 1,
            "maximum_age": 1,
            "resources": {"initial_count": 0, "spawn_rate": 0.0},
        },
        "events": [],
    }
    scenario = tmp_path / "extinction.json"
    scenario.write_text(json.dumps(source), encoding="utf-8")

    result = run_experiment(ExperimentSpec.from_json(scenario), tmp_path / "run")

    assert result.engine.extinct
    summary = json.loads((tmp_path / "run" / "summary.json").read_text(encoding="utf-8"))
    assert summary["extinct"] is True


def test_batch_uses_stable_replicate_directory_names(tmp_path) -> None:
    spec = ExperimentSpec.from_json(ROOT / "experiments" / "baseline.json").with_runtime(
        ticks=5, seed=100
    )

    results = run_batch(spec, output_dir=tmp_path, replicates=3)

    assert [result.manifest.root.name for result in results] == [
        "replicate-001-seed-100",
        "replicate-002-seed-101",
        "replicate-003-seed-102",
    ]


def test_equal_scenario_runs_have_identical_canonical_summaries(tmp_path) -> None:
    spec = ExperimentSpec.from_json(ROOT / "experiments" / "scarcity.json").with_runtime(
        ticks=45, seed=302
    )

    first = run_experiment(spec, tmp_path / "first")
    second = run_experiment(spec, tmp_path / "second")

    assert (first.manifest.root / "summary.json").read_bytes() == (
        second.manifest.root / "summary.json"
    ).read_bytes()
