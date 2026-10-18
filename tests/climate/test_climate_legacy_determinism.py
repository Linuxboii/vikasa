"""Climate support must not perturb any pre-existing deterministic trajectory.

The fingerprints were recorded from commit 62c663f, before the climate module
existed. A mismatch means a non-climate code path changed its RNG stream or
arithmetic.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evolution_sim.config import SimulationConfig
from evolution_sim.simulation.engine import SimulationEngine

ROOT = Path(__file__).resolve().parents[2]

LEGACY_FINGERPRINTS = {
    ("config/default.json", 11): "3d964e43245e47b07b3cea21358dedf364d7915a6f821c5e7e1231d06177135c",
    ("config/showcase.json", 2026): "24e13edf3f962ef9a2493c49acf5a7a0a9f2c08547e233075a3098b8575249b8",
    ("config/spatial-biome.json", 7): "1d90cb49b908f19ba4ad496f6851b983b59f35e68ed00c32fcd011f61820cb59",
}


def fingerprint(engine: SimulationEngine) -> str:
    rows = [
        (key, [round(float(v), 12) for v in item.position], round(item.energy, 12),
         list(item.genome.values), item.age, item.injury)
        for key, item in sorted(engine.creatures.items())
    ]
    payload = json.dumps({"t": engine.tick, "c": rows, "r": str(engine.rng.bit_generator.state),
                          "b": engine.total_births, "d": engine.total_deaths}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@pytest.mark.parametrize(("config", "seed"), sorted(LEGACY_FINGERPRINTS))
def test_legacy_trajectories_are_bit_identical(config: str, seed: int) -> None:
    engine = SimulationEngine(SimulationConfig.from_json(ROOT / config), seed)
    engine.step(400)
    assert fingerprint(engine) == LEGACY_FINGERPRINTS[(config, seed)]
