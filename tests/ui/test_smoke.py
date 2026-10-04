from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.ui.app import EvolutionApp
from evolution_sim.ui.layout import compute_layout
from evolution_sim.ui.renderer import hit_test_creature, world_to_screen


def test_world_projection_and_hit_testing_select_visible_creature(tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=17)
    snapshot = engine.snapshot()
    layout = compute_layout(1200, 760)
    creature = snapshot.creatures[0]
    point = world_to_screen(creature.position, layout.world, tiny_config.world)

    assert hit_test_creature(snapshot, point, layout.world, tiny_config) == creature.id


def test_headless_app_renders_scripted_frames_and_screenshot(tiny_config, tmp_path) -> None:
    app = EvolutionApp(tiny_config, seed=33, size=(1200, 760), show_setup=False)
    screenshot = tmp_path / "laboratory.png"

    frames = app.run(max_frames=3, screenshot_path=screenshot)

    assert frames == 3
    assert app.engine.tick > 0
    assert screenshot.exists()
    assert screenshot.stat().st_size > 5_000
    pygame.quit()


def test_save_and_load_actions_round_trip_in_app(tiny_config, tmp_path) -> None:
    app = EvolutionApp(tiny_config, seed=81, size=(1200, 760), show_setup=False)
    app.engine.step(5)
    expected = app.engine.snapshot()
    path = tmp_path / "ui-save.json"

    app.save(path)
    app.engine.step(5)
    app.load(path)

    assert app.engine.snapshot() == expected
    pygame.quit()


def test_export_action_writes_data_and_chart_artifacts(tiny_config, tmp_path) -> None:
    app = EvolutionApp(tiny_config, seed=91, size=(1200, 760), show_setup=False)
    app.engine.step(5)
    target = tmp_path / "ui-export"

    exported = app.export(target)

    assert exported == target
    assert (target / "config.json").exists()
    assert (target / "summary.json").exists()
    assert (target / "metrics.csv").exists()
    assert (target / "population.png").exists()
    assert (target / "traits.png").exists()
    assert (target / "births_deaths.png").exists()
    assert (target / "distributions.png").exists()
    pygame.quit()
