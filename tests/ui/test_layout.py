from __future__ import annotations

from evolution_sim.ui.layout import MINIMUM_SIZE, compute_layout


def test_reference_layout_gives_world_visual_priority() -> None:
    layout = compute_layout(1440, 900)

    assert layout.window.size == (1440, 900)
    assert layout.world.width > layout.sidebar.width * 2
    assert layout.world.height > layout.chart_strip.height * 2
    assert layout.sidebar.left >= layout.world.right
    assert layout.chart_strip.top >= layout.world.bottom


def test_minimum_layout_has_no_overlaps_or_negative_rectangles() -> None:
    layout = compute_layout(*MINIMUM_SIZE)
    rectangles = [layout.top_bar, layout.world, layout.sidebar, layout.chart_strip]

    assert all(rect.width > 0 and rect.height > 0 for rect in rectangles)
    assert not layout.world.colliderect(layout.sidebar)
    assert not layout.world.colliderect(layout.top_bar)
    assert not layout.world.colliderect(layout.chart_strip)


def test_smaller_requested_size_is_clamped_to_accessible_minimum() -> None:
    layout = compute_layout(640, 480)
    assert layout.window.size == MINIMUM_SIZE
