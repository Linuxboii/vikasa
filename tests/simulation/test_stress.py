from __future__ import annotations

from dataclasses import replace

import pytest

from evolution_sim.experiments.runner import run_stress


@pytest.mark.slow
def test_engine_survives_100000_ticks_without_state_corruption(tiny_config) -> None:
    config = replace(
        tiny_config,
        initial_population=2,
        maximum_age=250,
        resources=replace(
            tiny_config.resources,
            initial_count=0,
            spawn_rate=0.0,
            maximum_count=0,
        ),
        metrics=replace(tiny_config.metrics, sample_interval=5_000),
    )

    report = run_stress(config, seed=404, ticks=100_000, audit_interval=1_000)

    assert report.ticks_completed == 100_000
    assert report.invariant_errors == []
    assert report.elapsed_seconds > 0

