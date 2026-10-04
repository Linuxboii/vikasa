from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from evolution_sim.config import SimulationConfig

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def tiny_config() -> SimulationConfig:
    base = SimulationConfig.from_json(ROOT / "config" / "default.json")
    return replace(
        base,
        world=replace(base.world, width=200, height=120),
        initial_population=4,
        maximum_age=2_000,
        resources=replace(base.resources, initial_count=8, maximum_count=40, spawn_rate=0.1),
        reproduction=replace(
            base.reproduction,
            minimum_age=2,
            cooldown=3,
            mate_radius=30.0,
            population_cap=40,
        ),
        metrics=replace(base.metrics, sample_interval=1),
    )
