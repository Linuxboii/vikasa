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
    LITE_CREATURE_FIELDS,
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


def test_lite_state_is_compact_with_full_focus_detail(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    bridge.start()
    try:
        bridge.command({"action": "step", "count": 5})
        full = bridge.state()
        focus_id = full["creatures"][0]["id"]
        lite = json.loads(bridge.state_bytes(lite=True, focus=focus_id))
        assert lite["lite"] is True
        assert [c["id"] for c in lite["creatures"]] == [c["id"] for c in full["creatures"]]
        assert set(lite["creatures"][0]) == set(LITE_CREATURE_FIELDS)
        assert lite["focus"] == full["creatures"][0]
        assert lite["history"] == full["history"]
        assert "focus" not in json.loads(bridge.state_bytes(lite=True, focus=999_999))
        assert len(bridge.state_bytes(lite=True)) < len(bridge.state_bytes())
        port = bridge._http.server_address[1]
        url = f"http://127.0.0.1:{port}/state?lite=1&focus={focus_id}"
        with urllib.request.urlopen(url, timeout=3) as response:
            assert json.loads(response.read())["focus"]["id"] == focus_id
    finally:
        bridge.stop()


def test_lite_state_streams_histories_incrementally(tiny_config) -> None:
    bridge = _bridge(tiny_config)
    bridge.start()
    try:
        bridge.command({"action": "step", "count": 100})
        full = bridge.state()
        assert len(full["history"]) >= 3
        cut = full["history"][-3]["tick"]
        since = {"history": cut, "birth_history": 10**9}
        lite = json.loads(bridge.state_bytes(lite=True, since=since))
        assert lite["history"] == [row for row in full["history"] if row["tick"] > cut]
        assert lite["birth_history"] == []
        assert lite["history_since"] == {"history": cut, "birth_history": 10**9}
        port = bridge._http.server_address[1]
        url = f"http://127.0.0.1:{port}/state?lite=1&hs={cut}&bs=-1"
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read())
        assert [row["tick"] for row in payload["history"]] == [
            row["tick"] for row in full["history"] if row["tick"] > cut]
        assert payload["birth_history"] == full["birth_history"]
    finally:
        bridge.stop()


def test_push_stream_delivers_length_prefixed_frames(tiny_config) -> None:
    import socket
    import struct

    bridge = _bridge(tiny_config)
    bridge.start()
    try:
        port = bridge._http.server_address[1]
        with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
            sock.sendall(b"GET /stream HTTP/1.1\r\nHost: localhost\r\n\r\n")
            data = b""
            while b"\r\n\r\n" not in data:
                data += sock.recv(4096)
            head, _, data = data.partition(b"\r\n\r\n")
            assert b"200" in head.split(b"\r\n")[0]
            bridge.command({"action": "step", "count": 3})
            ticks = []
            while len(ticks) < 2:
                while len(data) < 4 or len(data) < 4 + struct.unpack("<I", data[:4])[0]:
                    data += sock.recv(65536)
                size = struct.unpack("<I", data[:4])[0]
                ticks.append(decode_frame(data[4:4 + size])["tick"])
                data = data[4 + size:]
            assert ticks[-1] == bridge.engine.tick
            assert ticks == sorted(ticks)
    finally:
        bridge.stop()


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
