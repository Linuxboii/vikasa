from __future__ import annotations

from evolution_sim.simulation.environment import EnvironmentEvent, EnvironmentState


def test_environment_events_apply_only_during_half_open_tick_window() -> None:
    state = EnvironmentState()
    state.schedule(EnvironmentEvent("drought", start_tick=3, duration=2, intensity=0.2))

    state.update(2)
    assert state.food_multiplier == 1.0
    state.update(3)
    assert state.food_multiplier == 0.2
    state.update(4)
    assert state.food_multiplier == 0.2
    state.update(5)
    assert state.food_multiplier == 1.0


def test_multiple_event_types_compose_and_history_records_once() -> None:
    state = EnvironmentState()
    state.schedule(EnvironmentEvent("abundance", 1, 3, 2.0, label="Bloom"))
    state.schedule(EnvironmentEvent("heat", 2, 1, 1.5))

    state.update(2)

    assert state.food_multiplier == 2.0
    assert state.metabolic_multiplier == 1.5
    assert [entry["kind"] for entry in state.history] == ["abundance", "heat"]
    state.update(2)
    assert len(state.history) == 2


def test_invalid_event_is_rejected() -> None:
    try:
        EnvironmentEvent("meteor", 0, 3, 1.0)
    except ValueError as exc:
        assert "meteor" in str(exc)
    else:
        raise AssertionError("Unsupported event was accepted")
