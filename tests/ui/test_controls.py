from __future__ import annotations

from evolution_sim.simulation.engine import SimulationEngine
from evolution_sim.ui.app import SimulationController


def test_pause_prevents_steps_and_resume_uses_selected_rate(tiny_config) -> None:
    engine = SimulationEngine(tiny_config, seed=72)
    controller = SimulationController(engine)
    controller.toggle_pause()

    controller.advance_frame()
    assert engine.tick == 0

    controller.toggle_pause()
    controller.set_speed_index(3)
    controller.advance_frame()
    assert engine.tick == controller.speed_steps


def test_speed_and_pause_do_not_change_simulation_rules(tiny_config) -> None:
    direct = SimulationEngine(tiny_config, seed=73)
    controlled = SimulationEngine(tiny_config, seed=73)
    controller = SimulationController(controlled)
    controller.set_speed_index(4)

    direct.step(controller.speed_steps)
    controller.advance_frame()

    assert controlled.snapshot() == direct.snapshot()


def test_keyboard_actions_are_named_by_user_outcome(tiny_config) -> None:
    controller = SimulationController(SimulationEngine(tiny_config, seed=2))

    assert controller.action_for_key("space", ctrl=False) == "toggle_pause"
    assert controller.action_for_key("s", ctrl=True) == "save"
    assert controller.action_for_key("o", ctrl=True) == "load"
    assert controller.action_for_key("e", ctrl=False) == "export"
    assert controller.action_for_key("?", ctrl=False) == "help"
    assert controller.action_for_key("4", ctrl=False) == "speed_4"
