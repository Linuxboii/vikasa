"""Species Risk Checker: data provenance, the seasonal screen, estimates and the app."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from evolution_sim.climate import risk
from evolution_sim.climate.data import CITY_REGIONS, resolve_region
from evolution_sim.config import SimulationConfig

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "results" / "climate-rescue-2026-10-18"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundled_city_files_match_their_build_script() -> None:
    for record in _load_tool("build_city_regions").build_records():
        on_disk = json.loads(
            (ROOT / "src/evolution_sim/climate/data" / f"{record['key']}.json").read_text(
                encoding="utf-8"))
        assert on_disk == json.loads(json.dumps(record))
        region = resolve_region(record["key"])
        assert region.annual_mean_c == pytest.approx(sum(region.monthly_c) / 12)
        assert len(region.series) == 45
        assert region.provenance["sha256"] and region.provenance["source"] == "NASA POWER"
    assert set(CITY_REGIONS) == {"hyderabad", "bengaluru", "chennai", "mumbai", "kolkata",
                                 "jaipur", "shimla"}


def test_reference_curve_is_a_faithful_copy_of_the_published_sweep() -> None:
    reference = risk.load_reference()
    sweep = json.loads((EVIDENCE / "sweep-summary.json").read_text(encoding="utf-8"))
    heritable = sweep["critical_rate"]["heritable"]
    assert reference["heritable"]["critical_rate"] == heritable["estimate"]
    assert reference["heritable"]["logistic"] == heritable["logistic"]
    assert reference["heritable"]["ci95"] == heritable["ci95"]
    assert reference["control"]["critical_rate"] == sweep["critical_rate"]["none"]["estimate"]
    calibration = json.loads((EVIDENCE / "calibration.json").read_text(encoding="utf-8"))
    assert reference["generation_ticks"] == calibration["generation_ticks"]


def test_seasonal_screen_reproduces_every_published_baseline_verdict() -> None:
    published = json.loads((EVIDENCE / "assessments.json").read_text(encoding="utf-8"))
    checked = 0
    for entry in published:
        region = resolve_region(entry["request"]["region"])
        screen = risk.seasonal_screen(region, entry["request"]["breadth_c"])
        assert (screen["status"] != "not viable") == entry["baseline_viable"], entry["id"]
        checked += 1
    assert checked >= 5


def test_tolerance_modes_scale_with_local_seasons() -> None:
    region = resolve_region("hyderabad")
    assert risk.resolve_breadth(region, "local") == pytest.approx(
        1.5 * region.seasonal_amplitude_c)
    assert risk.resolve_breadth(region, "specialist") < risk.resolve_breadth(region, "generalist")
    assert risk.resolve_breadth(region, 7.5) == 7.5
    assert risk.resolve_breadth(region, "6") == 6.0
    with pytest.raises(ValueError):
        risk.resolve_breadth(region, "huge")
    with pytest.raises(ValueError):
        risk.resolve_breadth(region, 0.1)


def test_slower_breeders_face_more_warming_per_generation() -> None:
    estimates = [risk.instant_estimate("hyderabad", generation_years=years, ssp="SSP5-8.5")
                 for years in (0.25, 1, 6, 25)]
    rates = [e["scenario"]["rate_c_per_generation"] for e in estimates]
    survival = [e["survival_probability"] for e in estimates]
    assert rates == sorted(rates)
    assert survival == sorted(survival, reverse=True)
    assert estimates[0]["verdict"] == "likely persists"
    assert estimates[-1]["verdict"] == "likely lost"
    six = estimates[2]
    assert six["verdict"] == "at risk"
    assert six["scenario"]["critical_generation_years"] == pytest.approx(
        risk.load_reference()["heritable"]["critical_rate"] / six["scenario"]["rate_c_per_year"])
    for estimate in estimates:
        json.dumps(estimate, allow_nan=False)


def test_unviable_seasons_override_the_warming_curve() -> None:
    estimate = risk.instant_estimate("delhi-ncr", generation_years=1, tolerance=4.0)
    assert estimate["seasonal"]["status"] == "not viable"
    assert estimate["verdict"] == "not viable in today's climate"
    assert estimate["survival_probability"] == 0.0


def test_scenarios_order_by_emissions_and_flag_the_reference_domain() -> None:
    estimate = risk.instant_estimate("western-ghats", generation_years=6, tolerance=4.0)
    p = [estimate["scenarios"][ssp]["p_with_evolution"]
         for ssp in ("SSP1-2.6", "SSP2-4.5", "SSP3-7.0", "SSP5-8.5")]
    assert p == sorted(p, reverse=True)
    assert estimate["in_reference_domain"] is True
    assert risk.instant_estimate("jaipur", generation_years=1)["in_reference_domain"] is False
    with pytest.raises(ValueError):
        risk.instant_estimate("hyderabad", generation_years=100)
    with pytest.raises(ValueError):
        risk.instant_estimate("hyderabad", generation_years=1, ssp="SSP9")


def test_watch_config_is_a_valid_living_biome_world() -> None:
    data = risk.watch_config("jaipur", generation_years=6, tolerance="local", ssp="SSP5-8.5")
    config = SimulationConfig.from_dict(data)
    region = resolve_region("jaipur")
    assert config.climate.enabled
    assert config.climate.monthly_c == pytest.approx(region.monthly_c)
    assert config.climate.anomaly_c[-1][1] == pytest.approx(
        risk.ssp_rate_c_per_year("SSP5-8.5") * 6 * 20, rel=1e-3)


def test_live_check_wraps_the_direct_assessment(tmp_path, monkeypatch) -> None:
    calls = {}

    def fake_assess(request, base, **kwargs):
        calls["request"], calls["kwargs"] = request, kwargs
        return {"baseline_viable": True, "caveats": ["c"], "ssps": [{
            "verdict": "likely persists",
            "direct": {"survived": 3, "n": 3, "p": 1.0, "wilson": [0.4, 1.0]},
            "plan": {"rate_c_per_generation": 0.1, "span_years": 75, "truncated": False,
                     "simulated_end_year": 2100.0, "warming_c": 3.0, "extra": 1}}]}

    monkeypatch.setattr(risk, "assess", fake_assess)
    checks = risk.LiveChecks(root=tmp_path, workers=1)
    job = checks.start("chennai", generation_years=2, tolerance="local", ssp="SSP2-4.5",
                       seeds=3, run_inline=True)
    snapshot = checks.get(job.id).snapshot()
    assert snapshot["status"] == "done", snapshot["error"]
    assert snapshot["result"]["direct"]["survived"] == 3
    assert "extra" not in snapshot["result"]["plan"]
    assert calls["request"].ssps == ("SSP2-4.5",) and calls["request"].seeds == (1, 2, 3)
    assert calls["kwargs"]["calibration_kwargs"]["reference_generation_ticks"] == 469
    with pytest.raises(ValueError):
        checks.start("chennai", generation_years=2, tolerance="local", ssp="SSP2-4.5", seeds=0)


def test_live_check_reports_failures_instead_of_hiding_them(tmp_path, monkeypatch) -> None:
    def broken(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(risk, "assess", broken)
    checks = risk.LiveChecks(root=tmp_path, workers=1)
    job = checks.start("chennai", generation_years=2, tolerance="local", ssp="SSP2-4.5",
                       seeds=2, run_inline=True)
    assert job.snapshot()["status"] == "error"
    assert "simulated failure" in job.snapshot()["error"]


@pytest.fixture
def app_server(tmp_path):
    from evolution_sim.climate.risk_app import RiskApp, make_server

    app = RiskApp(root=tmp_path, launch_godot=False)
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(base + path, data=data,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            kind = response.headers["Content-Type"]
        return json.loads(raw) if kind.startswith("application/json") else raw

    yield call, app
    server.shutdown()
    server.server_close()


def test_app_serves_pages_estimates_and_stats(app_server) -> None:
    call, _app = app_server
    home = call("/")
    for tile in (b'data-launch="biome"', b'data-launch="biome-demo"', b'data-launch="climate-demo"',
                 b'href="/risk"', b'href="/demo"', b'href="/evidence/index.html"'):
        assert tile in home
    assert b"Species Risk Checker" in call("/risk")
    assert b"DEMO MODE" in call("/demo")
    meta = call("/api/meta")
    assert {place["key"] for place in meta["places"]} >= {"hyderabad", "western-ghats"}
    assert meta["reference"]["critical_rate"] == pytest.approx(0.2624, abs=1e-4)
    estimate = call("/api/estimate?place=mumbai&generation_years=3&tolerance=local&ssp=SSP3-7.0")
    assert estimate["place"]["name"] == "Mumbai" and estimate["ssp"] == "SSP3-7.0"
    stats = call("/api/stats")
    assert stats["tests"] > 360 and stats["python_lines"] > 10_000
    assert [row["id"] for row in stats["criteria"]][:3] == ["C1", "C2", "C3"]
    assert call("/evidence/figures/survival_curve.png")[:4] == b"\x89PNG"


def test_app_launches_are_whitelisted_and_paths_are_contained(app_server) -> None:
    call, _app = app_server
    launched = call("/api/launch", {"what": "biome-demo"})
    assert launched["arguments"][-1] == "--demo" and launched["launched"] is False
    watch = call("/api/watch", {"place": "kolkata", "generation_years": 2, "ssp": "SSP1-2.6"})
    SimulationConfig.from_json(Path(watch["config"]))
    for bad in ("/api/launch", "/api/watch"):
        with pytest.raises(urllib.error.HTTPError) as error:
            call(bad, {"what": "rm -rf", "place": "../../etc/passwd"})
        assert error.value.code == 400
    with pytest.raises(urllib.error.HTTPError):
        call("/evidence/../../../pyproject.toml")
    with pytest.raises(urllib.error.HTTPError):
        call("/api/estimate?place=custom:../../x")


def test_cli_risk_check_prints_a_verdict(capsys) -> None:
    from evolution_sim.cli import main

    assert main(["risk", "check", "--place", "hyderabad", "--generation-years", "6"]) == 0
    out = capsys.readouterr().out
    assert "VERDICT     AT RISK" in out and "Hyderabad" in out
    assert main(["risk", "check", "--place", "shimla", "--tolerance", "12", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["estimate"]["organism"]["breadth_c"] == 12.0
    assert main(["risk", "places"]) == 0
    assert "western-ghats" in capsys.readouterr().out


def test_cli_demo_flags_reach_the_godot_client(monkeypatch) -> None:
    from evolution_sim import bridge
    from evolution_sim.cli import main

    seen = []
    monkeypatch.setattr(bridge, "launch_godot",
                        lambda config, **kwargs: seen.append(kwargs) or 0)
    assert main(["godot", "--demo"]) == 0
    assert main(["demo", "--biome-only"]) == 0
    assert main(["godot"]) == 0
    assert [kwargs["user_args"] for kwargs in seen] == [["--demo"], ["--demo"], None]


def test_launch_godot_passes_user_arguments_after_a_separator(monkeypatch, tiny_config) -> None:
    from evolution_sim import bridge

    commands = []

    class FakeProcess:
        def __init__(self, command):
            commands.append(command)

        def wait(self):
            return 0

    monkeypatch.setattr(bridge, "_godot_binary", lambda _path: "godot")
    monkeypatch.setattr(bridge.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(bridge.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(bridge.GodotSimulationServer, "start", lambda self: None)
    monkeypatch.setattr(bridge.GodotSimulationServer, "stop", lambda self: None)
    assert bridge.launch_godot(tiny_config, seed=1, user_args=["--demo"]) == 0
    assert commands[0][-2:] == ["--", "--demo"]


def test_cli_app_opens_the_home_screen(monkeypatch) -> None:
    from evolution_sim.cli import main
    from evolution_sim.climate import risk_app

    pages = []
    monkeypatch.setattr(risk_app, "serve", lambda **kwargs: pages.append(kwargs["page"]) or 0)
    assert main(["app", "--no-browser"]) == 0
    assert main(["risk", "--no-browser"]) == 0
    assert main(["demo", "--no-browser"]) == 0
    assert pages == ["/", "/risk", "/demo"]
