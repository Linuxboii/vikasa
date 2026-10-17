from __future__ import annotations

import json
import urllib.request

import numpy as np
import pytest

from evolution_sim.bridge import (
    BEHAVIOR_CODES,
    CREATURE_STRIDE,
    FRAME_HEADER,
    FRAME_VERSION,
    RESOURCE_STRIDE,
    WEATHER_CODES,
    GodotSimulationServer,
    decode_frame,
)


def _bridge(config, seed: int = 19) -> GodotSimulationServer:
    bridge = GodotSimulationServer(config, seed=seed, port=0)
    bridge.paused = True
    return bridge


def test_binary_frame_round_trips_every_creature_and_resource(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    try:
        bridge.command({"action": "step", "count": 5})
        payload = bridge.frame_bytes()
        frame = decode_frame(payload)
        engine = bridge.engine
        assert frame["version"] == FRAME_VERSION
        assert frame["tick"] == engine.tick
        assert frame["paused"] is True
        assert len(payload) == 4 * (
            FRAME_HEADER
            + CREATURE_STRIDE * len(engine.creatures)
            + RESOURCE_STRIDE * len(engine.resources)
        )
        assert [row["id"] for row in frame["creatures"]] == sorted(engine.creatures)
        assert [row["id"] for row in frame["resources"]] == sorted(engine.resources)
        for row in frame["creatures"]:
            creature = engine.creatures[row["id"]]
            assert row["x"] == pytest.approx(creature.position[0], abs=1e-3)
            assert row["y"] == pytest.approx(creature.position[1], abs=1e-3)
            assert row["behavior"] == creature.behavior_state.action.value
            assert row["generation"] == engine.lineage.generation_of(creature.id)
            assert 0.0 <= row["energy_ratio"] <= 1.0
    finally:
        bridge._http.server_close()


def test_frame_is_finite_little_endian_float32(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    try:
        values = np.frombuffer(bridge.frame_bytes(), dtype="<f4")
        assert np.isfinite(values).all()
        assert values[0] == FRAME_VERSION
    finally:
        bridge._http.server_close()


def test_behavior_and_weather_codes_are_stable_contracts() -> None:
    assert BEHAVIOR_CODES == (
        "explore", "forage", "rest", "seek_mate", "care", "flee", "patrol", "challenge"
    )
    assert WEATHER_CODES[0] == "drought"
    assert len(set(WEATHER_CODES)) == len(WEATHER_CODES)


def test_founder_is_stable_maternal_line_root(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    try:
        engine = bridge.engine
        for _ in range(400):
            bridge.command({"action": "step", "count": 50})
            if any(item.parents for item in engine.creatures.values()):
                break
        children = [item for item in engine.creatures.values() if item.parents]
        if not children:
            pytest.skip("seed produced no births in the probe horizon")
        child = children[0]
        founder = bridge.founder_of(child.id)
        assert engine.lineage.parents_of(founder) is None
        cursor = child.id
        while engine.lineage.parents_of(cursor) is not None:
            cursor = engine.lineage.parents_of(cursor)[0]
        assert founder == cursor
    finally:
        bridge._http.server_close()


def test_event_feed_keeps_every_tick_and_is_sequenced(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    try:
        bridge.command({"action": "step", "count": 100})
        bridge.command({"action": "weather", "kind": "storm", "intensity": 2.0, "duration": 30})
        bridge.command({"action": "step", "count": 60})
        feed = bridge.state()["feed"]
        sequences = [item["seq"] for item in feed]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)
        assert any(item["kind"] == "weather" for item in feed)
        assert all({"seq", "tick", "kind", "text"} <= item.keys() for item in feed)
        assert bridge.state()["feed_seq"] == sequences[-1]
    finally:
        bridge._http.server_close()


def test_food_burst_scatters_bounded_audited_food(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    try:
        before = len(bridge.engine.resources)
        result = bridge.command({"action": "food_burst", "x": 0.5, "y": 0.5,
                                 "count": 6, "radius": 0.1})
        assert result["ok"] is True
        assert result["placed"] == min(6, tiny_config.resources.maximum_count - before)
        assert len(bridge.engine.resources) == before + result["placed"]
        assert bridge.engine.audit_invariants() == []
        with pytest.raises(ValueError):
            bridge.command({"action": "food_burst", "x": 0.5, "y": 0.5, "count": 0})
        with pytest.raises(ValueError):
            bridge.command({"action": "food_burst", "x": 2.0, "y": 0.5, "count": 3})
    finally:
        bridge._http.server_close()


def test_http_serves_binary_frame_and_state(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    bridge.start()
    try:
        port = bridge._http.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/frame", timeout=3) as response:
            assert response.headers["Content-Type"] == "application/octet-stream"
            frame = decode_frame(response.read())
        assert len(frame["creatures"]) == len(bridge.engine.creatures)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/state", timeout=3) as response:
            state = json.loads(response.read())
        assert "feed" in state and "founder" in state["creatures"][0]
    finally:
        bridge.stop()
