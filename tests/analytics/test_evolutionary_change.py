"""Hand-derived quantitative-evolution identities, not visual trend assertions."""

import json

import numpy as np
import pytest

from evolution_sim.analytics import metrics
from evolution_sim.model.entities import Creature
from evolution_sim.model.genome import Genome
from evolution_sim.model.lineage import LineageStore
from evolution_sim.simulation.engine import SimulationEngine


def test_price_identity_separates_selection_and_transmission():
    # z=[1,3], w=[1,3], descendants=[2,4]: ancestral mean 2 -> descendant mean 3.5.
    result = metrics.price_decomposition([1, 3], [1, 3], [2, 4])
    assert result["selection"] == pytest.approx(0.5)
    assert result["transmission"] == pytest.approx(1.0)
    assert result["total_change"] == pytest.approx(1.5)
    assert result["residual"] == pytest.approx(0.0)


def test_extinct_cohort_has_no_defined_price_change():
    assert metrics.price_decomposition([1, 3], [0, 0], [0, 0]) is None


def test_price_rejects_negative_descendant_weights():
    with pytest.raises(ValueError):
        metrics.price_decomposition([1, 3], [1, -1], [1, 3])


@pytest.mark.parametrize("traits,weights,descendants", [([1], [1, 2], [1]),
                        ([float("nan")], [1], [1]), ([[1]], [1], [1])])
def test_price_rejects_nonfinite_or_mismatched_vectors(traits, weights, descendants):
    with pytest.raises(ValueError):
        metrics.price_decomposition(traits, weights, descendants)


def test_generation_depth_survives_checkpoint_lineage_round_trip():
    lineage = LineageStore()
    lineage.record(3, (1, 2), birth_tick=10)
    lineage.record(4, (2, 3), birth_tick=20)
    lineage.record(5, (3, 4), birth_tick=30)
    restored = LineageStore.from_records(lineage.to_records())
    assert restored.generation_of(1) == 0
    assert restored.generation_of(3) == 1
    assert restored.generation_of(5) == 3


def test_generation_depth_detects_cycles_instead_of_hanging():
    lineage = LineageStore()
    lineage.record(1, (2, 3), birth_tick=1)
    lineage.record(2, (1, 3), birth_tick=2)
    with pytest.raises(ValueError, match="Cyclic"):
        lineage.generation_of(1)


def test_generation_cache_preserves_unaffected_ancestry():
    lineage = LineageStore()
    lineage.record(3, (1, 2), birth_tick=1)
    assert lineage.generation_of(3) == 1
    lineage.record(4, (1, 2), birth_tick=2)
    assert lineage._generations[3] == 1
    lineage.record(1, (5, 6), birth_tick=0)
    assert lineage.generation_of(3) == 2
    assert lineage.generation_of(4) == 2


def test_metrics_report_lineage_development_not_just_age(tiny_config):
    engine = SimulationEngine(tiny_config, 4)
    engine.lineage.record(2, (0, 1), birth_tick=0)
    engine.lineage.record(3, (1, 2), birth_tick=0)
    sample = engine.metrics.record(engine)
    assert sample.max_generation == 2
    assert sample.mean_generation == pytest.approx(0.75)
    assert sample.founder_fraction == pytest.approx(0.5)
    assert sample.to_row()["max_generation"] == 2


def test_birth_cohort_uses_both_parent_contributions_and_real_child_genome(tiny_config):
    def creature(cid, fraction, parents=None):
        genome = Genome.from_mapping({name: bounds.minimum + fraction *
                                      (bounds.maximum - bounds.minimum)
                                      for name, bounds in tiny_config.genome.traits.items()},
                                     tiny_config.genome)
        return Creature(cid, np.array([40., 40.]), np.zeros(2), 100, 200,
                        genome, parents=parents)
    source = {i: creature(i, fraction) for i, fraction in enumerate([0, .5, 1])}
    child = creature(3, 0, parents=(0, 1))
    recorder = metrics.MetricsRecorder()
    recorder.record_birth_cohort(source, [child], tick=10)
    row = recorder.birth_cohorts[-1]
    assert row["parent_population"] == 3
    assert row["births"] == 1
    assert row["size_selection"] == pytest.approx(-1.375)
    assert row["size_transmission"] == pytest.approx(-1.375)
    assert row["size_total_change"] == pytest.approx(-2.75)
    assert row["size_residual"] == pytest.approx(0)


def test_real_births_publish_price_decomposition_and_survive_save_load(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
    from evolution_sim.simulation.behavior import ActionName, BehaviorState
    engine = SimulationEngine(tiny_config, 8)
    engine.creatures = {key: engine.creatures[key] for key in (0, 1)}
    for key, creature in engine.creatures.items():
        creature.age = 100
        creature.energy = 220
        creature.position[:] = [50, 50]
        creature.behavior_state = BehaviorState(action=ActionName.SEEK_MATE,
                                               target_id=1-key, target_kind="creature")
    engine._resolve_reproduction()
    assert engine.tick_births == 1
    assert engine.metrics.birth_cohorts[-1]["births"] == 1
    assert abs(engine.metrics.birth_cohorts[-1]["size_residual"]) < 1e-12
    save_checkpoint(engine, tmp_path / "birth.json")
    restored = load_checkpoint(tmp_path / "birth.json")
    assert restored.metrics.birth_cohorts == engine.metrics.birth_cohorts


def test_legacy_development_history_remains_unavailable(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import load_checkpoint, save_checkpoint
    engine = SimulationEngine(tiny_config, 8)
    engine.metrics.record(engine)
    path = tmp_path / "legacy.json"
    save_checkpoint(engine, path)
    payload = json.loads(path.read_text())
    for row in payload["metrics"]:
        for key in ("max_generation", "mean_generation", "founder_fraction",
                    "juvenile_fraction", "mean_age"):
            row.pop(key, None)
    path.write_text(json.dumps(payload))
    restored = load_checkpoint(path)
    assert restored.metrics.samples[-1].founder_fraction is None
    assert restored.metrics.samples[-1].to_row()["mean_age"] is None
    assert restored.metrics.development(restored)["founder_fraction"] == 1.0


def valid_cohort(tick=1):
    return {"tick": tick, "parent_population": 2, "births": 1,
            **{f"{trait.value}_{key}": value for trait in metrics.TRAITS
               for key, value in {"selection": 1., "transmission": 2.,
                                  "total_change": 3., "residual": 0.}.items()}}


@pytest.mark.parametrize("kind", ["duplicate", "future", "parents", "births", "identity"])
def test_corrupt_birth_history_rejected(kind):
    row = valid_cohort()
    rows = [row]
    if kind == "duplicate":
        rows.append(dict(row))
    if kind == "future":
        row["tick"] = 11
    if kind == "parents":
        row["parent_population"] = 1
    if kind == "births":
        rows.append(valid_cohort(2))
    if kind == "identity":
        row["size_total_change"] = 999.
    with pytest.raises(ValueError):
        metrics.MetricsRecorder().restore_birth_cohorts(rows, current_tick=10, total_births=1)


def test_impossible_price_identity_rejected_without_context():
    row = valid_cohort()
    row["size_total_change"] = 999.
    with pytest.raises(ValueError):
        metrics.MetricsRecorder().restore_birth_cohorts([row])


def test_retained_cohorts_allow_truncated_earlier_births():
    recorder = metrics.MetricsRecorder()
    rows = [valid_cohort(tick) for tick in range(1, 513)]
    recorder.restore_birth_cohorts(rows, current_tick=600, total_births=700)
    assert recorder.birth_cohorts == rows
    with pytest.raises(ValueError):
        recorder.restore_birth_cohorts([*rows, valid_cohort(513)])
