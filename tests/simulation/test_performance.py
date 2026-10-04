from __future__ import annotations

import time
from pathlib import Path

import pytest

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.slow
def test_default_population_advances_120_ticks_within_interactive_budget() -> None:
    engine = SimulationEngine(SimulationConfig.from_json(ROOT / "config" / "default.json"), seed=77)

    started = time.perf_counter()
    engine.step(120)
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"120 ticks took {elapsed:.2f}s"
    assert engine.audit_invariants() == []
