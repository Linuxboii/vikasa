"""Counterfactual effects must use seed blocks, not correlated time points."""

import json
import math
from dataclasses import replace

import pytest

from evolution_sim.cli import main
from evolution_sim.experiments import runner


def protocol_data(**changes):
    data = {
        "name": "Weather experiment",
        "description": "A model comparison",
        "control": "baseline",
        "seeds": [7, 41, 2026],
        "ticks": 20,
        "sample_interval": 5,
        "bootstrap_seed": 123,
        "bootstrap_samples": 1000,
        "arms": [
            {"id": "baseline", "label": "Seasonal baseline", "overrides": {}, "events": []},
            {"id": "treatment", "label": "Treatment", "overrides": {}, "events": []},
        ],
    }
    data.update(changes)
    return data


def short_life(config):
    return replace(
        config,
        initial_population=1,
        maximum_age=2,
        reproduction=replace(config.reproduction, minimum_age=0),
        resources=replace(config.resources, initial_count=0, spawn_rate=0),
        energy=replace(config.energy, basal_cost=0, movement_cost=0),
    )


def test_paired_effect_uses_unbiased_between_seed_variance():
    # Treatment-control differences [-2, 0, 2], not six independent measurements.
    stats = runner.paired_effect_statistics(
        [8, 20, 32], [10, 20, 30], bootstrap_seed=123, bootstrap_samples=1000
    )
    assert stats["differences"] == [-2, 0, 2]
    assert stats["mean_difference"] == 0
    assert stats["sample_variance"] == 4
    assert stats["standard_error"] == pytest.approx(math.sqrt(4 / 3))
    assert stats["bootstrap_percentile_95"] == [-2, 2]


def test_single_seed_does_not_fabricate_uncertainty():
    stats = runner.paired_effect_statistics([3], [1], bootstrap_seed=1, bootstrap_samples=100)
    assert stats["mean_difference"] == 2
    assert stats["sample_variance"] is None
    assert stats["standard_error"] is None
    assert stats["bootstrap_percentile_95"] is None


def test_missing_ecology_is_unavailable_not_zero_or_dropped_pairs():
    stats = runner.paired_effect_statistics(
        [None, 3], [None, 2], bootstrap_seed=1, bootstrap_samples=100
    )
    assert stats["pairs"] == 2
    assert stats["available_pairs"] == 1
    assert stats["mean_difference"] is None
    assert stats["differences"] == [None, 1]


@pytest.mark.parametrize(
    "changes",
    [
        {"seeds": [1, 1]},
        {"seeds": [True]},
        {"seeds": [1.5]},
        {"ticks": True},
        {"ticks": 0},
        {"sample_interval": 0},
        {"bootstrap_samples": 0},
        {"control": "missing"},
        {"arms": []},
        {"misspelled": 1},
    ],
)
def test_invalid_protocol_fails_before_any_simulation(tiny_config, changes):
    with pytest.raises(ValueError):
        runner.ContrastProtocol.from_dict(protocol_data(**changes), tiny_config)


@pytest.mark.parametrize(
    "event",
    [
        {"kind": "storm", "start_tick": 1.5, "duration": 3, "intensity": 1},
        {"kind": "storm", "start_tick": 20, "duration": 3, "intensity": 1},
        {"kind": "storm", "start_tick": 1, "duration": True, "intensity": 1},
        {"kind": "storm", "start_tick": 1, "duration": 3, "intensity": float("nan")},
    ],
)
def test_events_are_strictly_validated_without_integer_coercion(tiny_config, event):
    data = protocol_data()
    data["arms"][1]["events"] = [event]
    with pytest.raises(ValueError):
        runner.ContrastProtocol.from_dict(data, tiny_config)


def test_every_arm_config_is_validated_up_front(tiny_config):
    data = protocol_data()
    data["arms"][1]["overrides"] = {"energy": {"basal_cost_typo": 0.1}}
    with pytest.raises(ValueError):
        runner.ContrastProtocol.from_dict(data, tiny_config)


def test_fixed_horizon_integral_retains_extinction_and_identical_arm_zero(tiny_config):
    protocol = runner.ContrastProtocol.from_dict(protocol_data(), short_life(tiny_config))
    report = runner.run_contrast(protocol)
    assert report == runner.run_contrast(protocol)
    assert len(report["replicates"]) == 6
    for row in report["replicates"]:
        assert row["extinction_tick"] == 3
        assert row["ticks_completed"] == 20
        assert row["outcomes"]["final_population"] == 0
        # Populations after ticks 1..20: 1,1,0,...,0. No sampling approximation.
        assert row["outcomes"]["population_tick_sum"] == 2
        assert row["outcomes"]["mean_population"] == 0.1
        assert row["trajectory"][-1]["tick"] == 20
        assert row["invariant_errors"] == []
    assert report["contrasts"][0]["effects"]["mean_population"]["differences"] == [0, 0, 0]
    assert report["contrasts"][0]["effects"]["mean_population"]["bootstrap_percentile_95"] == [0, 0]
    assert report["trajectory_bands"]["baseline"][0]["population"] == {
        "mean": 1,
        "q25": 1,
        "q75": 1,
        "replicates": 3,
    }
    assert len(report["provenance"]["protocol_sha256"]) == 64


def test_storm_changes_actual_population_and_spatial_reservoirs(tiny_config):
    config = replace(
        tiny_config,
        initial_population=4,
        maximum_age=1000,
        ecology=replace(tiny_config.ecology, enabled=True),
        reproduction=replace(tiny_config.reproduction, minimum_age=900),
    )
    data = protocol_data(ticks=250, sample_interval=25)
    data["arms"][1]["events"] = [
        {"kind": "storm", "start_tick": 10, "duration": 240, "intensity": 5}
    ]
    report = runner.run_contrast(runner.ContrastProtocol.from_dict(data, config))
    effects = report["contrasts"][0]["effects"]
    assert effects["mean_population"]["mean_difference"] < 0
    assert effects["total_deaths"]["mean_difference"] > 0
    assert effects["plant_energy"]["mean_difference"] < 0
    assert all(row["invariant_errors"] == [] for row in report["replicates"])


def test_contrast_cli_writes_json_and_offline_dashboard(tiny_config, tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps(short_life(tiny_config).to_dict()), encoding="utf-8")
    data = protocol_data()
    data["config"] = "base.json"
    source = tmp_path / "protocol.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "lab"
    assert main(["contrast", "--protocol", str(source), "--output", str(output)]) == 0
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["protocol"]["seeds"] == [7, 41, 2026]
    assert (output / "index.html").is_file()


def test_observer_sampling_and_bootstrap_rng_do_not_change_biological_outcomes(tiny_config):
    config = short_life(tiny_config)
    first = runner.run_contrast(runner.ContrastProtocol.from_dict(protocol_data(), config))
    second = runner.run_contrast(
        runner.ContrastProtocol.from_dict(
            protocol_data(sample_interval=2, bootstrap_seed=42), config
        )
    )
    assert [row["outcomes"] for row in first["replicates"]] == [
        row["outcomes"] for row in second["replicates"]
    ]


def test_protocol_rejects_duplicate_arm_identifiers(tiny_config):
    data = protocol_data()
    data["arms"][1]["id"] = "baseline"
    with pytest.raises(ValueError, match="unique"):
        runner.ContrastProtocol.from_dict(data, tiny_config)


def test_contrast_rejects_source_changes_during_execution(tiny_config, monkeypatch):
    hashes = iter(["before", "after"])
    monkeypatch.setattr(runner, "_source_digest", lambda: next(hashes))
    protocol = runner.ContrastProtocol.from_dict(protocol_data(), short_life(tiny_config))
    with pytest.raises(ValueError, match="changed"):
        runner.run_contrast(protocol)


def test_cli_never_overwrites_an_existing_evidence_directory(tmp_path):
    (tmp_path / "report.json").write_text("original evidence", encoding="utf-8")
    assert main(["contrast", "--protocol", "missing.json", "--output", str(tmp_path)]) == 2
    assert (tmp_path / "report.json").read_text(encoding="utf-8") == "original evidence"


def test_failed_seed_arm_keeps_completed_runs_and_invalidates_its_contrast(
    tiny_config, monkeypatch
):
    from evolution_sim.experiments import contrast
    from evolution_sim.simulation.engine import SimulationEngine

    class FailingEngine(SimulationEngine):
        def _step_once(self):
            if self.seed == 41 and self.tick == 2:
                raise RuntimeError("Injected model failure")
            super()._step_once()

    monkeypatch.setattr(contrast, "SimulationEngine", FailingEngine)
    protocol = runner.ContrastProtocol.from_dict(protocol_data(), short_life(tiny_config))
    report = runner.run_contrast(protocol)
    assert len(report["replicates"]) == 6
    failures = [row for row in report["replicates"] if row["execution_error"]]
    assert len(failures) == 2
    assert failures[0]["execution_error"]["tick"] == 2
    assert failures[0]["execution_error"]["stage"] == "step"
    assert failures[0]["outcomes"]["mean_population"] is None
    assert report["contrasts"][0]["effects"]["mean_population"]["mean_difference"] is None
    assert report["execution_failure_replicates"] == 2
    assert report["trajectory_bands"]["baseline"][-1]["population"] is None
    assert report["replicates"][-1]["ticks_completed"] == 20


def test_output_claim_is_exclusive_even_during_the_simulation(tiny_config, tmp_path, monkeypatch):
    import evolution_sim.cli as cli

    base = tmp_path / "base.json"
    base.write_text(json.dumps(short_life(tiny_config).to_dict()), encoding="utf-8")
    data = protocol_data()
    data["config"] = "base.json"
    source = tmp_path / "protocol.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "evidence"
    real_run = runner.run_contrast
    attempts = 0

    def concurrent_attempt(protocol, **kwargs):
        nonlocal attempts
        attempts += 1
        assert attempts == 1, "output was not claimed before the concurrent launch"
        # A second run must be rejected before it can execute or write evidence.
        assert cli.main(["contrast", "--protocol", str(source), "--output", str(output)]) == 2
        assert not (output / "manifest.json").exists()
        return real_run(protocol, **kwargs)

    monkeypatch.setattr(cli, "run_contrast", concurrent_attempt)
    assert cli.main(["contrast", "--protocol", str(source), "--output", str(output)]) == 0
    assert (output / "manifest.json").is_file()


def test_nonfinite_measurements_still_export_failed_and_completed_runs(
    tiny_config, tmp_path, monkeypatch
):
    from evolution_sim.experiments import contrast
    from evolution_sim.simulation.engine import SimulationEngine

    class CorruptHabitatEngine(SimulationEngine):
        def __init__(self, config, seed):
            super().__init__(config, seed)
            if seed == 41:
                self.habitat.biomass[0, 0] = float("nan")

    monkeypatch.setattr(contrast, "SimulationEngine", CorruptHabitatEngine)
    config = replace(short_life(tiny_config), ecology=replace(tiny_config.ecology, enabled=True))
    base = tmp_path / "base.json"
    base.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    data = protocol_data()
    data["config"] = "base.json"
    source = tmp_path / "protocol.json"
    source.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "failed-study"
    assert main(["contrast", "--protocol", str(source), "--output", str(output)]) == 1
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert len(report["replicates"]) == 6
    bad = [row for row in report["replicates"] if row["seed"] == 41]
    assert all(row["status"] == "failed" for row in bad)
    assert all(row["trajectory"][0]["plant_energy"] is None for row in bad)
    assert any("plant_energy" in error for error in bad[0]["invariant_errors"])
    assert report["replicates"][-1]["status"] == "completed"
    assert (output / "manifest.json").is_file()
    assert not (output / "INCOMPLETE.txt").exists()
