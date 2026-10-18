"""Self-contained offline HTML report for a climate-rescue evidence package."""

from __future__ import annotations

import base64
import hashlib
import json
from html import escape
from pathlib import Path
from typing import Any

from evolution_sim.climate.assess import BIOLOGY_DISCLAIMER

SECTION_TITLES = (
    "The question and the answer",
    "How to read this report",
    "Method",
    "Critical warming rate",
    "Evolution vs no evolution",
    "Adaptation lag",
    "What matters most",
    "Surrogate accuracy",
    "Regional assessments",
    "Success criteria",
    "Limitations",
    "Provenance",
)

CSS = """
:root{color-scheme:light;--bg:#f4f3ef;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--line:#e4e3de;--accent:#2a78d6;--good:#0b7a3b;--bad:#b42318;--chip:#ecebe6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--line:#33322f;--accent:#3987e5;
--good:#4cc27e;--bad:#f07167;--chip:#262624}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;
--ink-2:#c3c2b7;--line:#33322f;--accent:#3987e5;--good:#4cc27e;--bad:#f07167;--chip:#262624}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 80px}
header h1{font-size:clamp(1.6rem,4vw,2.3rem);line-height:1.2;margin:0 0 8px}
.meta{color:var(--ink-2);font-size:.9rem}
section{background:var(--surface);border:1px solid var(--line);border-radius:14px;
padding:20px 22px;margin:18px 0}
h2{font-size:1.25rem;margin:0 0 10px}h3{font-size:1.02rem;margin:18px 0 6px}
.headline{font-size:1.15rem;border-left:4px solid var(--accent);padding:4px 0 4px 14px}
figure{margin:14px 0}figure img{width:100%;height:auto;border-radius:10px;
background:#fcfcfb;border:1px solid var(--line)}
figcaption{color:var(--ink-2);font-size:.88rem;margin-top:6px}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem;
font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--ink-2);font-weight:600}
.pass{color:var(--good);font-weight:600}.fail{color:var(--bad);font-weight:600}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 9px;
font-size:.82rem}.small{font-size:.86rem;color:var(--ink-2)}
code{font-family:ui-monospace,Consolas,monospace;font-size:.85em;word-break:break-all}
ul{padding-left:20px}
"""


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def _ci(ci: list[float] | None) -> str:
    return "undefined" if not ci else f"{ci[0]:.3g}&ndash;{ci[1]:.3g}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
                   for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead>' \
           f"<tbody>{body}</tbody></table></div>"


def _figure(figures: dict[str, bytes], key: str, alt: str, caption: str) -> str:
    if key not in figures:
        return ""
    data = base64.b64encode(figures[key]).decode("ascii")
    return (f'<figure><img src="data:image/png;base64,{data}" alt="{escape(alt)}">'
            f"<figcaption>{escape(caption)}</figcaption></figure>")


def _section(identifier: str, title: str, body: str) -> str:
    return f'<section id="{identifier}"><h2>{escape(title)}</h2>{body}</section>'


def _headline(context: dict[str, Any]) -> str:
    sweep = (context.get("sweep") or {}).get("summary")
    if not sweep:
        return "No rate sweep is included in this package."
    heritable = sweep["critical_rate"].get("heritable") or {}
    kc = heritable.get("estimate")
    text = ("Under this model, populations with heritable thermal tolerance survive "
            f"sustained warming up to about <strong>{_fmt(kc)} °C per generation</strong> "
            f"(95 % CI {_ci(heritable.get('ci95'))})")
    gain = sweep.get("rescue_gain") or {}
    control = sweep["critical_rate"].get("none")
    if gain.get("estimate") is not None:
        text += (f"; heritable adaptation raises the tolerable rate by "
                 f"<strong>{_fmt(gain['estimate'])} °C/generation</strong> "
                 f"(95 % CI {_ci(gain.get('ci95'))}).")
    elif control:
        failing = [p["rate"] for p in control["curve"] if p["rate"] > 0 and p["p"] < 0.5]
        text += (". Without heritable variation, populations failed at every tested "
                 f"warming rate ≥ {_fmt(min(failing))} °C/generation." if failing else ".")
    else:
        text += "."
    return text


def _sweep_sections(context: dict[str, Any], figures: dict[str, bytes]) -> list[str]:
    summary = context["sweep"]["summary"]
    curve_rows = []
    for arm, result in summary["critical_rate"].items():
        for point in result["curve"]:
            curve_rows.append([escape(arm), _fmt(point["rate"]),
                               f"{point['survived']}/{point['n']}",
                               f"{point['p']:.2f} ({point['wilson_lo']:.2f}&ndash;"
                               f"{point['wilson_hi']:.2f})"])
    critical = "".join(
        f"<li><span class=chip>{escape(arm)}</span> k<sub>c</sub> = {_fmt(r['estimate'])} "
        f"°C/gen, 95 % CI {_ci(r['ci95'])} "
        f"(bootstrap undefined fraction {_fmt(r['undefined_fraction'], 2)})</li>"
        for arm, r in summary["critical_rate"].items())
    section_critical = _section("critical", "Critical warming rate", (
        "<p>Each dot is the fraction of independent seeds whose population was still alive "
        "after 5 generations of burn-in, 20 generations of warming and 5 generations of "
        "hold. The curve is a logistic fit; the dashed line marks where survival falls to "
        "50 %, the critical rate k<sub>c</sub>.</p>"
        + _figure(figures, "survival_curve", "Survival fraction against warming rate",
                  "Survival vs warming rate with Wilson 95 % intervals and logistic fits.")
        + f"<ul>{critical}</ul>"
        + _table(["Arm", "Rate (°C/gen)", "Survived", "p (Wilson 95 %)"], curve_rows)))
    gain = summary.get("rescue_gain") or {}
    shift_rows = [[escape(arm), _fmt(row["rate"]), _fmt(row["mean_shift_c"]),
                   _fmt(row["rate"] * summary.get("warming_generations", 20)), row["n"]]
                  for arm, rows in summary["shift"].items() for row in rows]
    section_evolution = _section("evolution", "Evolution vs no evolution", (
        "<p>The control arm has the same spread of thermal optima but zero heritability: "
        "offspring inherit nothing from their parents. Any survival advantage of the "
        "heritable arm is therefore evolutionary rescue.</p>"
        f"<p>Rescue gain (k<sub>c</sub> heritable &minus; control): {_fmt(gain.get('estimate'))} "
        f"°C/gen, 95 % CI {_ci(gain.get('ci95'))}.</p>"
        + _figure(figures, "shift_vs_rate", "Shift of mean thermal optimum by warming rate",
                  "How far the population's mean optimum moved during warming; the dotted "
                  "line is the total warming a perfectly tracking population would match.")
        + _figure(figures, "trajectories", "Population and lag trajectories",
                  "One representative heritable seed per rate: population relative to its "
                  "pre-warming size (left) and degrees behind the warming (right).")
        + _table(["Arm", "Rate (°C/gen)", "Mean shift (°C)", "Total warming (°C)",
                  "Survivors"], shift_rows)))
    lag = summary.get("lag") or {}
    section_lag = _section("lag", "Adaptation lag", (
        "<p>Quantitative-genetic theory (Lynch &amp; Lande 1993) predicts that a population "
        "tracking a steadily moving optimum settles at a constant lag proportional to the "
        "rate of change. Lag here is the warming minus the evolved shift, averaged over the "
        "last five warming generations of surviving heritable runs below k<sub>c</sub>.</p>"
        + _figure(figures, "lag_vs_rate", "Adaptation lag by warming rate",
                  "Lag behind the moving optimum for every surviving heritable run.")
        + f"<p>Slope {_fmt(lag.get('slope'))} °C per (°C/gen), Pearson r = "
          f"{_fmt(lag.get('pearson_r'))}, n = {_fmt(lag.get('n'))}.</p>"))
    return [section_critical, section_evolution, section_lag]


def _sensitivity_section(context: dict[str, Any], figures: dict[str, bytes]) -> str:
    sensitivity = context["sensitivity"]
    survival = sensitivity["sobol"]["survival"]
    rows = [[escape(name.replace("_", " ")), f"{survival['S1'][i]:.3f}",
             f"{survival['ST'][i]:.3f}", _ci(survival["ST_ci"][i])]
            for i, name in enumerate(sensitivity["names"])]
    return _section("sensitivity", "What matters most", (
        "<p>Sobol indices split the variance of the surrogate's predicted survival "
        "probability across the six inputs. S1 is the share an input explains alone; ST "
        "adds its interactions. Inputs were varied over a Latin hypercube of "
        f"{_fmt(sensitivity.get('design_points'))} simulations.</p>"
        + _figure(figures, "sobol_bars", "Sobol sensitivity indices",
                  "First- and total-order Sobol indices for survival probability with "
                  "bootstrap 95 % intervals.")
        + _table(["Input", "S1", "ST", "ST 95 % CI"], rows)))


def _surrogate_section(context: dict[str, Any], figures: dict[str, bytes]) -> str:
    validation = context["surrogate_validation"]
    holdout, cv = validation.get("holdout", {}), validation.get("cv", {})
    rows = [["Hold-out R² (population ratio)", _fmt(holdout.get("r2"))],
            ["Hold-out AUC (survival)", _fmt(holdout.get("auc"))],
            ["Hold-out accuracy", _fmt(holdout.get("accuracy"))],
            ["Hold-out Brier score", _fmt(holdout.get("brier"))],
            ["Hold-out simulations", _fmt(holdout.get("n"))],
            ["5-fold CV mean R²", _fmt(cv.get("r2_mean"))],
            ["5-fold CV mean AUC", _fmt(cv.get("auc_mean"))]]
    return _section("surrogate", "Surrogate accuracy", (
        "<p>A Gaussian-process emulator trained on simulations predicts the final population "
        "relative to its pre-warming size, with uncertainty. Survival probability is the "
        "chance that ratio exceeds a threshold learned from the training runs. It is "
        "scored on simulations it never saw.</p>"
        + _figure(figures, "surrogate_parity", "Predicted vs simulated population ratio",
                  "Held-out simulations: surrogate prediction (±1 sd) against the simulated "
                  "outcome.")
        + _table(["Metric", "Value"], rows)))


def _assessment_section(context: dict[str, Any], figures: dict[str, bytes]) -> str:
    parts = ["<p>Each region uses its observed 1991&ndash;2020 monthly climatology (NASA POWER, "
             "MERRA-2) and the IPCC AR6 warming pathway for each scenario from 2025. The "
             "direct simulation answer is authoritative; the surrogate and sweep values "
             "are quick references and are withheld outside the range they were trained "
             "on.</p>"]
    for assessment in context["assessments"]:
        request = assessment["request"]
        rows = []
        for entry in assessment["ssps"]:
            plan, direct = entry["plan"], entry["direct"]

            def reference(value: Any) -> str:
                if not isinstance(value, dict):
                    return "—"
                if "p" in value:
                    return f"{value['p']:.2f}"
                return escape(value.get("status", "—"))

            rows.append([
                escape(entry["ssp"]), _fmt(plan["rate_c_per_year"]),
                _fmt(plan["rate_c_per_generation"]),
                (f"{direct['p']:.2f} ({direct['wilson'][0]:.2f}&ndash;{direct['wilson'][1]:.2f}), "
                 f"n={direct['n']}" if direct.get("p") is not None else "—"),
                f"<strong>{escape(entry['verdict'])}</strong>",
                reference(entry.get("surrogate")), reference(entry.get("sweep")),
                (f"first {plan['span_years']:g} years" if plan.get("truncated")
                 else "full 2025&ndash;2100")])
        trend = assessment["ssps"][0].get("observed_trend_c_per_decade") if \
            assessment["ssps"] else None
        parts.append(
            f"<h3>{escape(str(request.get('region_name', request['region'])))}</h3>"
            f"<p class=small>Generation time {_fmt(request['generation_years'])} years · "
            f"tolerance breadth {_fmt(request['breadth_c'])} °C · observed local trend "
            f"1981&ndash;present {_fmt(trend)} °C/decade.</p>"
            + _figure(figures, f"assessment_{request['region']}",
                      f"Survival by scenario for {request['region']}",
                      "Direct-simulation survival with Wilson 95 % intervals; dashed lines "
                      "mark the 0.2 and 0.8 verdict thresholds.")
            + _table(["Scenario", "Warming (°C/yr)", "Warming (°C/gen)",
                      "Direct survival p (95 %)", "Verdict", "Surrogate p", "Sweep p",
                      "Simulated span"], rows)
            + "<ul class=small>" + "".join(f"<li>{escape(c)}</li>"
                                          for c in assessment.get("caveats", [])) + "</ul>")
    return _section("regions", "Regional assessments", "".join(parts))


def _criteria_section(context: dict[str, Any]) -> str:
    rows = [[escape(c["id"]), escape(c["statement"]),
             escape(json.dumps(c["value"], allow_nan=True) if isinstance(c["value"], (list, dict))
                    else _fmt(c["value"])),
             escape(c["threshold"]),
             '<span class="pass">PASS</span>' if c["passed"]
             else '<span class="fail">FAIL</span>']
            for c in context["criteria"]]
    return _section("criteria", "Success criteria", (
        "<p>Criteria were fixed before the production run. Failures are shown as failures; "
        "they are results, not hidden.</p>"
        + _table(["ID", "Criterion", "Measured", "Threshold", "Result"], rows)))


def render_report(context: dict[str, Any], figures: dict[str, bytes]) -> str:
    calibration = context.get("calibration") or {}
    sections = [
        _section("answer", "The question and the answer", (
            "<p><strong>Can a population evolve fast enough to survive a warming "
            "climate, and how fast is too fast?</strong></p>"
            f'<p class="headline">{_headline(context)}</p>'
            f"<p class=small>{escape(BIOLOGY_DISCLAIMER)}</p>")),
        _section("reading", "How to read this report", (
            "<ul><li><strong>Warming rate per generation</strong> is what matters "
            "biologically: 0.1 °C/generation is slow for a mouse but fast for an "
            "elephant.</li><li>Every probability is a fraction of independent simulated "
            "seeds, shown with a 95 % interval.</li><li><strong>Heritable</strong> runs "
            "pass thermal tolerance to offspring; <strong>control</strong> runs do not. The "
            "difference is evolutionary rescue.</li><li>Verdicts: likely persists "
            "(p ≥ 0.8), at risk (0.2&ndash;0.8), likely lost (&lt; 0.2).</li></ul>")),
        _section("method", "Method", (
            "<p>Individual-based simulation (ODD protocol in docs/CLIMATE_RESCUE.md). Each "
            "animal carries a heritable thermal optimum. Temperature away from that "
            "optimum, more sharply on the warm side, raises its energy cost, causes injury "
            "and blocks breeding. Offspring inherit the parental mean plus Gaussian "
            "segregation and mutation noise (the infinitesimal model).</p>"
            f"<p>Generation interval, measured from ancestry depth: "
            f"{_fmt(calibration.get('generation_ticks'))} ticks. Protocol: burn-in, "
            "warming at a fixed rate in °C per generation, then hold.</p>")),
    ]
    if context.get("sweep"):
        sections.extend(_sweep_sections(context, figures))
    if context.get("sensitivity"):
        sections.append(_sensitivity_section(context, figures))
    if context.get("surrogate_validation"):
        sections.append(_surrogate_section(context, figures))
    if context.get("assessments"):
        sections.append(_assessment_section(context, figures))
    if context.get("criteria"):
        sections.append(_criteria_section(context))
    sections.append(_section("limitations", "Limitations", (
        f"<ul><li>{escape(BIOLOGY_DISCLAIMER)}</li>"
        "<li>No plasticity, behavioural thermoregulation, migration or food-web effects "
        "of warming; temperature acts only through the tolerance curve.</li>"
        "<li>The world is two-dimensional and small (tens of animals), so demographic "
        "chance matters more than in large natural populations.</li>"
        "<li>Regional warming uses AR6 global-mean pathways times a regional factor, not "
        "downscaled regional climate models.</li>"
        "<li>Ticks have no calibrated real-time meaning; results are expressed per "
        "generation and translated using the generation time you supply.</li></ul>")))
    provenance = context.get("provenance") or {}
    sections.append(_section("provenance", "Provenance", _table(
        ["Item", "Value"], [[escape(str(k)), f"<code>{escape(str(v))}</code>"]
                            for k, v in sorted(provenance.items())])))
    title = escape(context.get("title", "Climate rescue report"))
    generated = escape(context.get("generated_utc", ""))
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            f"<title>{title}</title><style>{CSS}</style></head><body><main>"
            f"<header><h1>{title}</h1><p class=meta>Vikasa climate rescue · generated "
            f"{generated}</p></header>{''.join(sections)}</main></body></html>\n")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def write_report(out_dir: Path, context: dict[str, Any],
                 figures: dict[str, bytes]) -> dict[str, Any]:
    out_dir = Path(out_dir)
    files: dict[str, bytes] = {"index.html": render_report(context, figures).encode("utf-8")}
    summary = {key: value for key, value in context.items() if key != "sweep"}
    if context.get("sweep"):
        summary["sweep"] = {"summary": context["sweep"]["summary"]}
    files["summary.json"] = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)
                             + "\n").encode("utf-8")
    for name, data in figures.items():
        files[f"figures/{name}.png"] = data
    for name, data in files.items():
        _atomic_write(out_dir / name, data)
    manifest = {"schema": "vikasa-climate-report-v1",
                "sha256": {name: hashlib.sha256(data).hexdigest()
                           for name, data in sorted(files.items())}}
    _atomic_write(out_dir / "manifest.json",
                  (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return manifest
