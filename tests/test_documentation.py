from __future__ import annotations

import json
from pathlib import Path

import pytest

from evolution_sim.cli import build_parser
from evolution_sim.experiments.runner import ExperimentSpec

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "baseline",
    "scarcity",
    "mutation_low",
    "mutation_high",
    "environmental_shift",
)


@pytest.mark.parametrize("name", SCENARIOS)
def test_documented_scenario_is_valid_and_loadable(name: str) -> None:
    spec = ExperimentSpec.from_json(ROOT / "experiments" / f"{name}.json")

    assert spec.ticks > 0
    assert spec.name
    assert spec.load_config().initial_population >= 1


def test_cli_help_exposes_every_documented_operating_mode() -> None:
    help_text = build_parser().format_help()

    for command in ("ui", "run", "batch", "stress", "validate"):
        assert command in help_text


@pytest.mark.parametrize(
    "name",
    ("baseline", "scarcity", "mutation-low", "mutation-high", "environmental-shift"),
)
def test_example_result_is_audited_and_self_describing(name: str) -> None:
    summary_path = ROOT / "examples" / "results" / name / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert summary["format"] == "vikasa-export"
    assert summary["tick"] > 0
    assert summary["invariant_errors"] == []
    assert (summary_path.parent / "population.png").stat().st_size > 1_000


def test_documentation_screenshots_are_real_rendered_images() -> None:
    for name in ("setup.png", "laboratory.png", "inspector.png", "pressure.png"):
        path = ROOT / "docs" / "images" / name
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert path.stat().st_size > 5_000
