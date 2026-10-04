"""Portable experiment exports with content hashes."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evolution_sim.analytics.metrics import MetricsRecorder
from evolution_sim.model.genome import TRAITS
from evolution_sim.simulation.engine import SimulationEngine


@dataclass(frozen=True, slots=True)
class ExportManifest:
    root: Path
    files: dict[str, str]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_experiment(engine: SimulationEngine, directory: str | Path) -> ExportManifest:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    metrics = engine.metrics
    if not metrics.samples:
        metrics = MetricsRecorder()
        metrics.record(engine)

    _write_json(root / "config.json", {"seed": engine.seed, "config": engine.config.to_dict()})
    metric_rows = metrics.rows()
    _write_csv(root / "metrics.csv", metric_rows, list(metric_rows[0]))

    creature_rows: list[dict[str, Any]] = []
    for creature_id in sorted(engine.creatures):
        creature = engine.creatures[creature_id]
        row: dict[str, Any] = {
            "id": creature.id,
            "x": float(creature.position[0]),
            "y": float(creature.position[1]),
            "age": creature.age,
            "energy": creature.energy,
            "parent_a": creature.parents[0] if creature.parents else "",
            "parent_b": creature.parents[1] if creature.parents else "",
            "offspring_count": creature.offspring_count,
            "food_acquired": creature.food_acquired,
            "birth_tick": creature.birth_tick,
        }
        row.update(creature.genome.to_mapping())
        creature_rows.append(row)
    creature_fields = [
        "id",
        "x",
        "y",
        "age",
        "energy",
        "parent_a",
        "parent_b",
        "offspring_count",
        "food_acquired",
        "birth_tick",
        *(trait.value for trait in TRAITS),
    ]
    _write_csv(root / "creatures.csv", creature_rows, creature_fields)

    lineage_rows = engine.lineage.to_records()
    _write_csv(
        root / "lineage.csv",
        lineage_rows,
        ["child", "parent_a", "parent_b", "birth_tick"],
    )
    _write_json(
        root / "events.json",
        {
            "scheduled": [event.to_dict() for event in engine.environment.events],
            "history": engine.environment.history,
        },
    )
    final_sample = metric_rows[-1]
    _write_json(
        root / "summary.json",
        {
            "format": "vikasa-export",
            "version": 1,
            "seed": engine.seed,
            "tick": engine.tick,
            "population": len(engine.creatures),
            "resources": len(engine.resources),
            "total_births": engine.total_births,
            "total_deaths": engine.total_deaths,
            "extinct": engine.extinct,
            "peak_population": metrics.summary()["peak_population"],
            "final_metrics": final_sample,
            "invariant_errors": engine.audit_invariants(),
        },
    )
    names = [
        "config.json",
        "metrics.csv",
        "creatures.csv",
        "lineage.csv",
        "events.json",
        "summary.json",
    ]
    return ExportManifest(root=root, files={name: _sha256(root / name) for name in names})
