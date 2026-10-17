"""Mechanistic inheritance checks with hand-derived two-locus examples."""


import json

import numpy as np
import pytest

from evolution_sim.config import ConfigError, SimulationConfig
from evolution_sim.model import genetics


def diploid_config(config, **overrides):
    data = config.to_dict()
    data["genome"]["architecture"] = {
        "effects": [[1, 0]] * 6, "dominance": [0, 0],
        "recombination": [0], "founder_frequency": [.5, .5],
        "allele_mutation_probability": .001, **overrides,
    }
    return SimulationConfig.from_dict(data)


def test_dominance_maps_heterozygotes_to_expected_trait(tiny_config):
    config = diploid_config(tiny_config, dominance=[.5, 0])
    genome = genetics.polygenic_genome(((0, 0), (1, 1)), config.genome)
    for i, bounds in enumerate(config.genome.traits.values()):
        assert genome.values[i] == pytest.approx(bounds.minimum + .75 * (
            bounds.maximum - bounds.minimum))


def test_effect_weights_are_scale_invariant_even_at_tiny_magnitude(tiny_config):
    config = diploid_config(tiny_config, effects=[[5e-324, 0]] * 6)
    genome = genetics.polygenic_genome(((0, 0), (1, 1)), config.genome)
    for i, bounds in enumerate(config.genome.traits.values()):
        assert genome.values[i] == pytest.approx((bounds.minimum + bounds.maximum) / 2)
    homozygote = genetics.polygenic_genome(((1, 1), (1, 1)), config.genome)
    assert homozygote.values == tuple(b.maximum for b in config.genome.traits.values())


def test_zero_recombination_transmits_intact_parental_homologs(tiny_config):
    config = diploid_config(tiny_config)
    parent = genetics.polygenic_genome(((0, 0), (1, 1)), config.genome)
    gametes = [genetics.gamete(parent, config.genome.architecture, np.random.default_rng(seed))
               for seed in range(100)]
    assert set(gametes) == {(0, 0), (1, 1)}


def test_recombination_produces_recombinant_gametes(tiny_config):
    config = diploid_config(tiny_config, recombination=[.5])
    parent = genetics.polygenic_genome(((0, 0), (1, 1)), config.genome)
    gametes = [genetics.gamete(parent, config.genome.architecture, np.random.default_rng(seed))
               for seed in range(200)]
    assert set(gametes) == {(0, 0), (1, 1), (0, 1), (1, 0)}


def test_child_receives_one_gamete_from_each_parent(tiny_config):
    config = diploid_config(tiny_config)
    first = genetics.polygenic_genome(((0, 0), (0, 0)), config.genome)
    second = genetics.polygenic_genome(((1, 1), (1, 1)), config.genome)
    child = genetics.crossover(first, second, "arithmetic", np.random.default_rng(7),
                              config=config.genome)
    assert child.haplotypes == ((0, 0), (1, 1))
    for i, bounds in enumerate(config.genome.traits.values()):
        assert child.values[i] == pytest.approx((bounds.minimum + bounds.maximum) / 2)


def test_allele_mutation_flips_bits_and_recomputes_traits(tiny_config):
    config = diploid_config(tiny_config, allele_mutation_probability=1)
    parent = genetics.polygenic_genome(((0, 0), (0, 0)), config.genome)
    child = genetics.mutate(parent, config.genome, np.random.default_rng(7))
    assert child.haplotypes == ((1, 1), (1, 1))
    assert child.values == tuple(bounds.maximum for bounds in config.genome.traits.values())


@pytest.mark.parametrize("override", [
    {"recombination": [.6]}, {"dominance": [2, 0]},
    {"effects": [[0, 0]] * 6}, {"founder_frequency": [.5]},
    {"allele_mutation_probability": float("nan")}, {"effects": [[True, 0]] * 6},
])
def test_invalid_architecture_is_rejected(tiny_config, override):
    with pytest.raises(ConfigError):
        diploid_config(tiny_config, **override)


def test_checkpoint_preserves_genotype_and_future_random_state(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import checkpoint_payload, load_checkpoint, save_checkpoint
    from evolution_sim.simulation.engine import SimulationEngine

    engine = SimulationEngine(diploid_config(tiny_config), 7)
    engine.step(40)
    path = save_checkpoint(engine, tmp_path / "diploid.json")
    restored = load_checkpoint(path)
    assert all(c.genome.haplotypes is not None for c in restored.creatures.values())
    engine.step(40)
    restored.step(40)
    assert checkpoint_payload(engine) == checkpoint_payload(restored)


def test_checkpoint_rejects_corrupted_genotype_or_derived_traits(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import CheckpointError, load_checkpoint, save_checkpoint
    from evolution_sim.simulation.engine import SimulationEngine

    engine = SimulationEngine(diploid_config(tiny_config), 7)
    path = save_checkpoint(engine, tmp_path / "corrupt.json")
    original = json.loads(path.read_text())
    for corruption in ("missing", "boolean", "phenotype"):
        data = json.loads(json.dumps(original))
        row = data["creatures"][0]
        if corruption == "missing":
            del row["haplotypes"]
        elif corruption == "boolean":
            row["haplotypes"][0][0] = True
        else:
            row["genome"][0] = tiny_config.genome.traits["size"].maximum
        path.write_text(json.dumps(data))
        with pytest.raises(CheckpointError):
            load_checkpoint(path)


def test_diploid_checkpoint_cannot_claim_a_legacy_schema(tiny_config, tmp_path):
    from evolution_sim.io.checkpoints import CheckpointError, load_checkpoint, save_checkpoint
    from evolution_sim.simulation.engine import SimulationEngine

    path = save_checkpoint(SimulationEngine(diploid_config(tiny_config), 7), tmp_path / "v3.json")
    data = json.loads(path.read_text())
    data["version"] = 3
    path.write_text(json.dumps(data))
    with pytest.raises(CheckpointError):
        load_checkpoint(path)


def test_population_genetics_has_hand_derived_allele_and_linkage_statistics():
    from evolution_sim.analytics import trait_space

    result = trait_space.population_genetics([[[0, 0], [1, 1]], [[0, 0], [1, 1]]])
    assert result["allele_frequency"] == [.5, .5]
    assert result["observed_heterozygosity"] == [1, 1]
    assert result["expected_heterozygosity"] == [.5, .5]
    assert result["linkage_d"] == [[.25, .25], [.25, .25]]
    assert result["linkage_r_squared"] == [[1, 1], [1, 1]]


def test_diploid_export_includes_phased_individuals_and_statistics(tiny_config, tmp_path):
    from evolution_sim.experiments.charts import export_charts
    from evolution_sim.io.export import export_experiment
    from evolution_sim.simulation.engine import SimulationEngine

    engine = SimulationEngine(diploid_config(tiny_config), 7)
    manifest = export_experiment(engine, tmp_path)
    data = json.loads((manifest.root / "trait-space.json").read_text())
    assert len(data["individuals"][0]["haplotypes"]) == 2
    assert data["population_genetics"]["individuals"] == len(engine.creatures)
    assert "chromosomes.png" in [p.name for p in export_charts(engine, tmp_path)]


def test_live_bridge_exposes_phased_chromosomes(tiny_config):
    from evolution_sim.bridge import GodotSimulationServer

    bridge = GodotSimulationServer(diploid_config(tiny_config), seed=7, port=0)
    try:
        state = bridge._build_state()
        assert len(state["creatures"][0]["haplotypes"]) == 2
        assert state["creatures"][0]["generation"] == 0
        assert state["population_genetics"]["individuals"] == len(bridge.engine.creatures)
    finally:
        bridge._http.server_close()
