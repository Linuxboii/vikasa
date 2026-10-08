"""Replicated studies must report extinction and uncertainty rather than cherry-pick."""

import json
from dataclasses import replace

import pytest

from evolution_sim.cli import main
from evolution_sim.experiments import runner


def extinct_config(config):
    return replace(config, initial_population=1, maximum_age=2,
                   reproduction=replace(config.reproduction, minimum_age=0),
                   resources=replace(config.resources, initial_count=0, spawn_rate=0),
                   energy=replace(config.energy, basal_cost=0, movement_cost=0))


def test_study_reports_exact_extinction_and_uncertainty(tiny_config):
    report = runner.run_development_study(extinct_config(tiny_config), seeds=[1, 2],
                                           ticks=20, sample_interval=5)
    assert report["aggregate"]["survival_fraction"] == 0
    assert report["aggregate"]["survival_wilson_95"][0] == 0
    assert report["aggregate"]["survival_wilson_95"][1] == pytest.approx(.6576, abs=.0001)
    assert [row["extinction_tick"] for row in report["replicates"]] == [3, 3]
    assert report["replicates"][0]["trajectory"][-1]["tick"] == 3
    assert report["protocol"]["ticks"] == 20
    assert len(report["provenance"]["config_sha256"]) == 64


def test_study_is_reproducible_and_never_resurrects(tiny_config):
    config = extinct_config(tiny_config)
    first = runner.run_development_study(config, seeds=[7, 8], ticks=20)
    second = runner.run_development_study(config, seeds=[7, 8], ticks=20)
    assert first == second
    assert all(row["total_births"] == 0 for row in first["replicates"])
    assert all(row["final_population"] == 0 for row in first["replicates"])


@pytest.mark.parametrize("seeds,ticks", [([], 10), ([1, 1], 10), ([True], 10), ([1], 0)])
def test_invalid_study_protocol_is_rejected(tiny_config, seeds, ticks):
    with pytest.raises(ValueError):
        runner.run_development_study(tiny_config, seeds=seeds, ticks=ticks)


def test_study_command_writes_a_portable_evidence_report(tiny_config, tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(extinct_config(tiny_config).to_dict()), encoding="utf-8")
    result_path = tmp_path / "study.json"
    assert main(["study", "--config", str(config_path), "--ticks", "20", "--seeds", "1", "2",
                 "--output", str(result_path)]) == 0
    report = json.loads(result_path.read_text(encoding="utf-8"))
    assert report["aggregate"]["replicates"] == 2
    assert report["replicates"][0]["extinction_tick"] == 3


def test_study_rejects_source_changes_during_execution(tiny_config, monkeypatch):
    hashes = iter(["before", "after"])
    monkeypatch.setattr(runner, "_source_digest", lambda: next(hashes), raising=False)
    with pytest.raises(ValueError, match="source changed"):
        runner.run_development_study(extinct_config(tiny_config), seeds=[1], ticks=4)
