from __future__ import annotations

from pathlib import Path

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
