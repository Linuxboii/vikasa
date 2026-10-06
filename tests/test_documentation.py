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

    for command in ("ui", "godot", "serve", "shortcut", "run", "batch", "stress", "validate"):
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


def test_readme_explains_launch_controls_instincts_and_limits() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()

    for phrase in (".exe ui", "vikasa.exe godot", "pause", "follow", "instinct", "limitations"):
        assert phrase in readme


@pytest.mark.parametrize("name", ("ARCHITECTURE.md", "SCIENTIFIC_MODEL.md", "MATHEMATICS.md"))
def test_model_docs_describe_arbitration_and_checkpoint_compatibility(name: str) -> None:
    document = (ROOT / "docs" / name).read_text(encoding="utf-8").lower()

    for phrase in ("hysteresis", "checkpoint", "version 3", "versions 1 and 2"):
        assert phrase in document


@pytest.mark.parametrize(
    "relative_path",
    (
        "docs/superpowers/specs/2026-10-04-vikasa-design.md",
        "docs/superpowers/specs/2026-10-04-vikasa-ecosystem-v2-design.md",
        "docs/superpowers/plans/2026-10-04-vikasa.md",
        "docs/superpowers/plans/2026-10-04-vikasa-ecosystem-v2.md",
    ),
)
def test_old_specs_and_plans_are_marked_historical(relative_path: str) -> None:
    document = (ROOT / relative_path).read_text(encoding="utf-8").lower()

    assert "historical/superseded" in document
    assert "2026-10-05-vikasa-wildlife-experience-design.md" in document
    assert "../../scientific_model.md" in document


def test_documented_relative_markdown_links_resolve() -> None:
    import re

    markdown_files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for source in markdown_files:
        for target in link_pattern.findall(source.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (source.parent / target.split("#", maxsplit=1)[0]).resolve()
            assert path.exists(), f"Broken link in {source.relative_to(ROOT)}: {target}"
