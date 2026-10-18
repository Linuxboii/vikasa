from __future__ import annotations

import hashlib
import json
import re

import numpy as np
import pytest

from evolution_sim.climate.analysis import summarize_sweep
from evolution_sim.climate.assess import BIOLOGY_DISCLAIMER
from evolution_sim.climate.figures import build_figures
from evolution_sim.climate.report import SECTION_TITLES, render_report, write_report

from .test_climate_analysis import fake_rows


def rows_with_trajectories():
    rows = fake_rows(noise=0.05)
    for row in rows:
        generations = np.linspace(0, 30, 13)
        row["n_pre"] = 50.0
        row["trajectory"] = [{"generation": float(g), "population": 50 - g if not row["survived"]
                              else 50.0, "anomaly_c": min(20, max(0, g - 5)) *
                              row["meta"]["rate_c_per_gen"], "mean_optimum_c": 25.0,
                              "tick": int(g * 100)} for g in generations]
    return rows


@pytest.fixture(scope="module")
def context():
    rows = rows_with_trajectories()
    summary = summarize_sweep(rows, n_boot=100, seed=1)
    names = ["rate_c_per_gen", "breadth_c", "amplitude_c", "founder_sd_c",
             "segregation_sd_c", "capacity_scale"]
    indices = {"S1": [0.6, 0.1, 0.05, 0.05, 0.02, 0.01], "ST": [0.7, 0.2, 0.1, 0.1, 0.05, 0.02],
               "S1_ci": [[0.5, 0.7]] * 6, "ST_ci": [[0.6, 0.8]] * 6}
    assessment = {"request": {"region": "western-ghats", "region_name": "Western Ghats",
                              "generation_years": 1.0, "breadth_c": 4.0},
                  "ssps": [{"ssp": "SSP2-4.5", "plan": {"rate_c_per_year": 0.021,
                                                         "rate_c_per_generation": 0.021,
                                                         "truncated": True, "span_years": 40},
                            "direct": {"survived": 10, "n": 12, "p": 10 / 12,
                                       "wilson": [0.55, 0.95]},
                            "verdict": "likely persists", "sweep": {"p": 0.9},
                            "surrogate": {"status": "outside surrogate domain"},
                            "observed_trend_c_per_decade": 0.17}],
                  "caveats": [BIOLOGY_DISCLAIMER]}
    return {
        "title": "Climate rescue report", "generated_utc": "2026-10-18T00:00:00Z",
        "provenance": {"source_sha256": "a" * 64, "url": "https://power.larc.nasa.gov/"},
        "calibration": {"generation_ticks": 469},
        "sweep": {"summary": summary, "rows": rows},
        "sensitivity": {"names": names, "sobol": {"survival": indices, "ratio": indices},
                        "design_points": 192},
        "surrogate_validation": {"cv": {"r2_mean": 0.8, "auc_mean": 0.9},
                                 "holdout": {"r2": 0.82, "auc": 0.91, "accuracy": 0.9,
                                             "brier": 0.08, "n": 3,
                                             "observed_ratio": [0.0, 1.0, 0.5],
                                             "predicted_ratio": [0.1, 0.9, 0.6],
                                             "predicted_sd": [0.1, 0.1, 0.1]}},
        "assessments": [assessment],
        "criteria": summary["criteria"],
    }


def test_figures_are_png(context) -> None:
    figures = build_figures(context)
    assert {"survival_curve", "shift_vs_rate", "lag_vs_rate", "trajectories", "sobol_bars",
            "surrogate_parity", "assessment_western-ghats"} <= set(figures)
    assert all(data.startswith(b"\x89PNG") for data in figures.values())


def test_non_viable_assessment_gets_no_empty_figure(context) -> None:
    dead = dict(context["assessments"][0], id="delhi-ncr", baseline_viable=False)
    figures = build_figures(dict(context, assessments=[dead]))
    assert "assessment_delhi-ncr" not in figures


def test_critical_generation_time_table() -> None:
    from evolution_sim.climate.report import critical_generation_times

    rows = critical_generation_times({"estimate": 0.255, "ci95": [0.17, 0.34]})
    by_ssp = {row["ssp"]: row for row in rows}
    assert by_ssp["SSP2-4.5"]["years"] == pytest.approx(0.255 / (1.8 / 85))
    assert by_ssp["SSP2-4.5"]["ci95"] == pytest.approx([0.17 / (1.8 / 85), 0.34 / (1.8 / 85)])
    assert by_ssp["SSP1-2.6"]["years"] > by_ssp["SSP5-8.5"]["years"]
    assert critical_generation_times({"estimate": None, "ci95": None}) == []


def test_report_shows_critical_generation_time(context) -> None:
    html = render_report(context, {})
    assert "Critical generation time" in html and "SSP5-8.5" in html
    assert "first-order" in html


def test_two_variants_of_one_region_get_separate_figures(context) -> None:
    local = dict(context["assessments"][0], id="western-ghats-local",
                 label="Locally adapted organism")
    both = dict(context, assessments=[context["assessments"][0], local])
    figures = build_figures(both)
    assert {"assessment_western-ghats", "assessment_western-ghats-local"} <= set(figures)
    assert "Locally adapted organism" in render_report(both, figures)


def test_report_is_self_contained(context) -> None:
    html = render_report(context, build_figures(context))
    body = html.split('<section id="provenance"')[0]
    assert not re.search(r"(src|href)=[\"']https?://", html)
    assert "http://" not in body and "https://" not in body
    assert "data:image/png;base64," in html


def test_report_sections_present_in_order(context) -> None:
    html = render_report(context, build_figures(context))
    positions = [html.index(f">{title}<") for title in SECTION_TITLES]
    assert positions == sorted(positions)


def test_missing_sections_are_skipped(context) -> None:
    trimmed = {key: value for key, value in context.items()
               if key not in {"sensitivity", "surrogate_validation"}}
    html = render_report(trimmed, build_figures(trimmed))
    assert ">What matters most<" not in html and ">Surrogate accuracy<" not in html
    assert ">Critical warming rate<" in html


def test_report_includes_biology_disclaimer_and_escapes(context) -> None:
    hostile = dict(context, title="<script>alert(1)</script>")
    html = render_report(hostile, {})
    assert BIOLOGY_DISCLAIMER in html
    assert "<script>alert" not in html


def test_manifest_hashes_match(tmp_path, context) -> None:
    manifest = write_report(tmp_path, context, build_figures(context))
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert "rows" not in summary.get("sweep", {})
    assert (tmp_path / "figures" / "survival_curve.png").exists()
