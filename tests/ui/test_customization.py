from __future__ import annotations

from evolution_sim.ui.customization import PRESETS, CustomizationPanel


def test_preset_changes_ecology_genetics_and_seed_without_mutating_base(tiny_config) -> None:
    panel = CustomizationPanel(tiny_config, seed=12)

    panel.apply_preset("Hypermutation")

    assert panel.config.genome.mutation_probability == 0.3
    assert panel.config.genome.mutation_sigma == 0.15
    assert panel.config.resources.initial_count >= 100
    assert panel.seed == 404
    assert tiny_config.genome.mutation_probability != panel.config.genome.mutation_probability


def test_adjustment_is_bounded_and_keeps_dependent_limits_valid(tiny_config) -> None:
    panel = CustomizationPanel(tiny_config, seed=7)
    panel.select("Founders")

    for _ in range(100):
        panel.adjust(1)

    assert panel.config.initial_population == 500
    assert panel.config.reproduction.population_cap >= panel.config.initial_population

    panel.select("Food at launch")
    for _ in range(100):
        panel.adjust(1)

    assert panel.config.resources.initial_count == 1_000
    assert panel.config.resources.maximum_count >= panel.config.resources.initial_count


def test_keyboard_navigation_and_value_labels_are_user_facing(tiny_config) -> None:
    panel = CustomizationPanel(tiny_config, seed=7)

    panel.move_selection(1)
    before = panel.value
    panel.adjust(1)

    assert panel.selected_label == "Food at launch"
    assert panel.value > before
    assert panel.value_label.isdigit()
    assert tuple(PRESETS) == ("Balanced", "Bloom", "Scarcity", "Hypermutation")


def test_seed_is_customizable_and_clamped(tiny_config) -> None:
    panel = CustomizationPanel(tiny_config, seed=0)
    panel.select("Seed")

    panel.adjust(-1)
    assert panel.seed == 0

    panel.set_value(987_654)
    assert panel.seed == 987_654
