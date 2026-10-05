from __future__ import annotations

import json
from pathlib import Path

from evolution_sim.bridge import GodotSimulationServer
from evolution_sim.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_validate_command_accepts_valid_config(capsys) -> None:
    result = main(["validate", "--config", str(ROOT / "config" / "default.json")])

    assert result == 0
    assert "valid" in capsys.readouterr().out.lower()


def test_validate_command_reports_invalid_config(tmp_path, capsys) -> None:
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    result = main(["validate", "--config", str(path)])

    assert result == 2
    assert "required" in capsys.readouterr().err.lower()


def test_run_command_creates_summary(tmp_path) -> None:
    result = main(
        [
            "run",
            "--scenario",
            str(ROOT / "experiments" / "baseline.json"),
            "--output",
            str(tmp_path / "cli-run"),
            "--ticks",
            "8",
            "--seed",
            "5",
        ]
    )

    assert result == 0
    assert (tmp_path / "cli-run" / "summary.json").exists()
    assert (tmp_path / "cli-run" / "population.png").exists()


def test_shortcut_command_installs_named_link(tmp_path, capsys) -> None:
    result = main(
        [
            "shortcut",
            "--desktop",
            str(tmp_path),
            "--name",
            "My Vikasa",
            "--seed",
            "44",
        ]
    )

    assert result == 0
    assert (tmp_path / "My Vikasa.lnk").exists()
    assert "My Vikasa.lnk" in capsys.readouterr().out


def test_bridge_state_keeps_legacy_fields_and_exposes_explainable_instincts(tiny_config) -> None:
    bridge = GodotSimulationServer(tiny_config, seed=19, port=0)
    try:
        state = bridge.state()
        json.dumps(state, allow_nan=False)
        creature = state["creatures"][0]
        snapshot = bridge.engine.snapshot().creatures[0]
        assert {"id", "position", "energy", "hunger", "satisfaction", "alpha"} <= creature.keys()
        assert creature["behavior"] == "explore"
        assert snapshot.behavior == creature["behavior"]
        assert snapshot.behavior_reason == creature["behavior_reason"]
        assert snapshot.drives == tuple(creature["drives"].values())
        assert set(creature["drives"]) == {
            "survival",
            "foraging",
            "mating",
            "offspring_care",
            "danger_avoidance",
            "territory",
        }
        assert len(creature["behavior_reason"]) <= 240
        assert creature["target_kind"] is None
        assert creature["target_position"] is None
        assert set(creature["home_range"]) == {"center", "radius"}
        assert isinstance(creature["dependent_ids"], list)
        assert bridge.command({"action": "pause"}) == {"ok": True, "action": "pause"}
    finally:
        bridge._http.server_close()
