"""Conservation Planner: timelines, gene flow, refuges, triage, outputs and the app."""

from __future__ import annotations

import csv
import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from evolution_sim.climate import planner
from evolution_sim.climate.data import SURVEY_REGIONS, resolve_region
from evolution_sim.climate.risk import load_reference, seasonal_screen

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "watchlist-india.csv"
CRITICAL = load_reference()["heritable"]["critical_rate"]


def test_survey_sites_are_real_power_records_with_provenance() -> None:
    assert len(SURVEY_REGIONS) == 14
    for key, (name, lat, lon) in SURVEY_REGIONS.items():
        region = resolve_region(key)
        assert (region.name, region.latitude, region.longitude) == (name, lat, lon)
        assert region.provenance["source"] == "NASA POWER"
        assert len(region.provenance["sha256"]) == 64
        assert region.annual_mean_c == pytest.approx(sum(region.monthly_c) / 12)
        assert region.last_year - region.first_year >= 40
    assert resolve_region("leh").annual_mean_c < resolve_region("kochi").annual_mean_c


def test_peak_stress_matches_the_seasonal_screen() -> None:
    for key in ("hyderabad", "shimla", "western-ghats", "leh"):
        region = resolve_region(key)
        screen = seasonal_screen(region, 6.0)
        assert planner.peak_stress(region.monthly_c, region.annual_mean_c, 6.0) == \
            pytest.approx(screen["peak_stress"])


def test_evolution_never_makes_the_timeline_worse() -> None:
    region = resolve_region("chennai")
    for generation in (1, 5, 20):
        common = {"generation_years": generation, "breadth_c": 5.7, "ssp": "SSP5-8.5",
                  "critical": CRITICAL}
        evolving = planner.trajectory(region, **common)
        fixed = planner.trajectory(region, evolving=False, **common)
        assert len(evolving) == 76
        assert all(a <= b + 1e-12 for a, b in zip(evolving, fixed, strict=True))


def test_fast_breeders_track_warming_and_slow_breeders_fall_behind() -> None:
    fast = planner.plan_species("chennai", generation_years=1, tolerance="local")
    slow = planner.plan_species("chennai", generation_years=20, tolerance="local")
    assert fast["timeline"]["breeding_fails_with_evolution"] is None
    assert slow["timeline"]["breeding_fails_with_evolution"] == 2077
    assert slow["timeline"]["breeding_fails_without_evolution"] == 2054
    assert slow["timeline"]["years_bought_by_evolution"] == 23
    assert slow["priority"] > fast["priority"]
    # Lower emissions push the failure later or remove it.
    assert slow["pathways"]["SSP1-2.6"]["breeding_fails"] is None


def test_gene_flow_shift_is_the_smallest_that_works() -> None:
    region = resolve_region("chennai")
    common = {"generation_years": 20, "breadth_c": planner.resolve_breadth(region, "local"),
              "ssp": "SSP5-8.5", "critical": CRITICAL}
    shift = planner.gene_flow_needed(region, **common)
    assert shift == pytest.approx(0.65, abs=0.02)
    assert planner.breeding_fails(planner.trajectory(region, shift_c=shift, **common)) is None
    assert planner.breeding_fails(
        planner.trajectory(region, shift_c=shift - 0.05, **common)) is not None
    assert planner.gene_flow_needed(region, **{**common, "generation_years": 1}) == 0.0


def test_refuges_respect_habitat_and_distance() -> None:
    plan = planner.plan_species("chennai", generation_years=20, habitat="coastal")
    keys = {row["key"] for row in plan["refuges"]}
    assert keys <= {"mumbai", "kolkata", "kochi", "sundarbans"}
    refuges = [row for row in plan["refuges"] if row["status"] == "refuge"]
    assert refuges[0]["key"] == "kochi"
    assert all(row["stress_2100"] <= planner.FAIL_STRESS for row in refuges)
    distances = [row["distance_km"] for row in refuges]
    assert distances == sorted(distances)
    assert 540 < planner.distance_km(resolve_region("chennai"), resolve_region("kochi")) < 580
    with pytest.raises(ValueError):
        planner.plan_species("chennai", generation_years=2, habitat="ocean")


def test_find_place_accepts_keys_and_names() -> None:
    assert planner.find_place("Hyderabad").key == "hyderabad"
    assert planner.find_place("Ooty").key == "ooty"
    assert planner.find_place("Western Ghats").key == "western-ghats"
    with pytest.raises(ValueError):
        planner.find_place("Atlantis")


def test_triage_ranks_the_example_watchlist_and_reports_bad_rows() -> None:
    text = EXAMPLE.read_text(encoding="utf-8") + "Ghost,Atlantis,3,local,any,\n"
    result = planner.triage(planner.read_watchlist(text))
    assert result["schema"] == planner.SCHEMA and result["species_count"] == 14
    assert [e["species"] for e in result["errors"]] == ["Ghost"]
    priorities = [plan["priority"] for plan in result["plans"]]
    assert priorities == sorted(priorities, reverse=True)
    assert result["plans"][0]["species"] == "Asian elephant"
    assert result["earliest_failure"] == 2059
    assert sum(result["tiers"].values()) == 14
    for plan in result["plans"]:
        assert plan["actions"], plan["species"]
    json.dumps(result, allow_nan=False)


def test_watchlist_parsing_is_forgiving_but_strict_on_required_columns() -> None:
    rows = planner.read_watchlist("﻿Species,Place,Generation_Years\nFrog,Mumbai,1\n\n")
    assert rows == [{"species": "Frog", "place": "Mumbai", "generation_years": "1"}]
    with pytest.raises(ValueError, match="generation_years"):
        planner.read_watchlist("species,place\nFrog,Mumbai\n")
    with pytest.raises(ValueError):
        planner.read_watchlist("species,place,generation_years\n")


def test_outputs_are_complete_and_self_contained(tmp_path) -> None:
    result = planner.triage(planner.read_watchlist(EXAMPLE.read_text(encoding="utf-8")),
                            ssp="SSP2-4.5")
    paths = planner.write_outputs(result, tmp_path)
    table = list(csv.DictReader(io.StringIO(paths["csv"].read_text(encoding="utf-8"))))
    assert len(table) == 14 and table[0]["rank"] == "1"
    page = paths["html"].read_text(encoding="utf-8")
    assert "<script" not in page and "http" not in page.split("</style>")[1].split("Reference")[0]
    assert page.count('class="card"') == 14 and "<svg" in page
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["ssp"] == "SSP2-4.5"


def test_html_escapes_user_text() -> None:
    text = "species,place,generation_years,notes\n<script>x</script>,mumbai,2,<b>hi</b>\n"
    page = planner.render_html(planner.triage(planner.read_watchlist(text)))
    assert "<script>x" not in page and "&lt;script&gt;" in page and "<b>hi" not in page


def test_bundled_example_matches_the_app_copy() -> None:
    app_copy = ROOT / "src" / "evolution_sim" / "climate" / "web" / "watchlist-example.csv"
    assert app_copy.read_bytes() == EXAMPLE.read_bytes()


def test_cli_plan_commands(tmp_path, capsys) -> None:
    from evolution_sim.cli import main

    assert main(["plan", "triage", str(EXAMPLE), "--output", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "14 species" in out and (tmp_path / "report.html").is_file()
    assert main(["plan", "species", "--place", "Chennai", "--generation-years", "20",
                 "--habitat", "coastal", "--name", "Olive ridley"]) == 0
    out = capsys.readouterr().out
    assert "Olive ridley" in out and "Assisted migration: Kochi" in out
    assert main(["plan", "species", "--place", "mumbai", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["place"]["key"] == "mumbai"


def test_app_serves_the_planner(tmp_path) -> None:
    from evolution_sim.climate.risk_app import RiskApp, make_server

    server = make_server(RiskApp(root=tmp_path, launch_godot=False), 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert b"Conservation Planner" in urllib.request.urlopen(base + "/plan").read()
        assert b'href="/plan"' in urllib.request.urlopen(base + "/").read()
        example = urllib.request.urlopen(base + "/api/plan/example").read().decode()
        request = urllib.request.Request(
            base + "/api/plan", data=json.dumps({"csv": example, "ssp": "SSP3-7.0"}).encode(),
            headers={"Content-Type": "application/json"})
        reply = json.loads(urllib.request.urlopen(request).read())
        assert reply["result"]["ssp"] == "SSP3-7.0" and reply["html"].startswith("<!DOCTYPE")
        assert reply["csv"].startswith("rank,species")
        bad = urllib.request.Request(base + "/api/plan", data=b'{"csv": "a,b\\n1,2"}',
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(bad)
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
