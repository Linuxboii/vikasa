from __future__ import annotations

import json

import pytest

from evolution_sim.cli import main as top_main
from evolution_sim.climate.cli import PROFILES, main


def test_climate_help_lists_subcommands(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for name in ("fetch", "calibrate", "sweep", "sensitivity", "assess", "report", "pipeline"):
        assert name in out


def test_top_level_cli_delegates_climate(capsys) -> None:
    with pytest.raises(SystemExit):
        top_main(["climate", "pipeline", "--help"])
    assert "--profile" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        top_main(["--help"])
    assert "climate" in capsys.readouterr().out


def test_bad_region_is_friendly_error(tmp_path, capsys) -> None:
    code = main(["assess", "--root", str(tmp_path), "--region", "atlantis", "--profile",
                 "quick", "--workers", "1"])
    err = capsys.readouterr().err
    assert code == 2
    assert "Unknown region" in err and "Traceback" not in err


def test_calibration_from_another_profile_is_refused(tmp_path, capsys) -> None:
    (tmp_path / "calibration.json").write_text(
        json.dumps({"profile": "full", "generation_ticks": 469}), encoding="utf-8")
    code = main(["calibrate", "--root", str(tmp_path), "--profile", "quick", "--workers", "1"])
    assert code == 2 and "profile" in capsys.readouterr().err


def test_default_root_follows_profile() -> None:
    from evolution_sim.climate.cli import build_parser, resolve_root

    quick = build_parser().parse_args(["pipeline", "--profile", "quick"])
    assert resolve_root(quick).as_posix() == "exports/climate/quick"
    assert resolve_root(build_parser().parse_args(["report"])).as_posix() == \
        "exports/climate/full"


def test_profiles_are_consistent() -> None:
    for profile in PROFILES.values():
        warming = profile["phases"]["warming"]
        assert max(profile["rates"]) * warming <= 30
        assert profile["rates"][0] == 0.0
    assert len(PROFILES["full"]["rates"]) == 9 and PROFILES["full"]["seeds"] == 12


def test_criteria_print_on_legacy_windows_console(monkeypatch) -> None:
    import io
    import sys

    from evolution_sim.climate import cli

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    cli._configure_console()
    cli._print_criteria([{"id": "C2", "passed": True, "statement": "rank ≤ 2 at 4 °C"}])
    sys.stdout.flush()
    assert "PASS" in raw.getvalue().decode("utf-8")


def test_local_breadth_scales_with_seasonality() -> None:
    from evolution_sim.climate.cli import local_breadth
    from evolution_sim.climate.data import resolve_region

    profile = PROFILES["full"]
    assert local_breadth(resolve_region("delhi-ncr"), profile) == pytest.approx(
        1.5 * resolve_region("delhi-ncr").seasonal_amplitude_c)
    # Never narrower than the reference organism's breadth.
    assert local_breadth(resolve_region("western-ghats"), profile) == profile["breadth_c"]
    assert local_breadth(resolve_region("delhi-ncr"), PROFILES["quick"]) is None


def test_design_batches_keep_first_batch_stable() -> None:
    from evolution_sim.climate.cli import design_batches

    assert design_batches({"design_batches": 1}) == [("design", 2026, 10_000)]
    batches = design_batches(PROFILES["full"])
    assert batches[0] == ("design", 2026, 10_000)
    assert len(batches) == 2 and len({seed for _, seed, _ in batches}) == 2
    starts = sorted(seed0 for _, _, seed0 in batches)
    assert starts[1] - starts[0] >= PROFILES["full"]["design_points"]


@pytest.mark.slow
def test_quick_pipeline_end_to_end(tmp_path, capsys) -> None:
    root = tmp_path / "quick"
    code = main(["pipeline", "--profile", "quick", "--root", str(root), "--workers", "6"])
    out = capsys.readouterr().out
    assert code in (0, 3), out
    assert (root / "report" / "index.html").exists()
    assert "C1" in out and "S9" in out
    summary = json.loads((root / "report" / "summary.json").read_text(encoding="utf-8"))
    assert summary["assessments"] and summary["sensitivity"]["names"][0] == "rate_c_per_gen"
    sweep_lines = (root / "sweep" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    # Rerun is resumable: nothing recomputed, the same rows remain.
    assert main(["pipeline", "--profile", "quick", "--root", str(root), "--workers", "6"]) in (0, 3)
    assert (root / "sweep" / "results.jsonl").read_text(encoding="utf-8").splitlines() == \
        sweep_lines
    first = json.loads((root / "report" / "summary.json").read_text(encoding="utf-8"))
    assert main(["report", "--root", str(root), "--profile", "quick"]) in (0, 3)
    second = json.loads((root / "report" / "summary.json").read_text(encoding="utf-8"))
    first.pop("generated_utc")
    second.pop("generated_utc")
    assert first == second
