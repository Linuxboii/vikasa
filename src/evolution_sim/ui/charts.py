"""Fast in-app evidence traces drawn directly with Pygame."""

from __future__ import annotations

from collections.abc import Sequence

import pygame

from evolution_sim.analytics.metrics import MetricSample
from evolution_sim.ui import theme
from evolution_sim.ui.widgets import text


def _series_points(rect: pygame.Rect, values: Sequence[float]) -> list[tuple[int, int]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    span = max(1e-9, high - low)
    return [
        (
            round(rect.left + index * rect.width / max(1, len(values) - 1)),
            round(rect.bottom - (value - low) / span * rect.height),
        )
        for index, value in enumerate(values)
    ]


def render_metric_traces(
    surface: pygame.Surface,
    fonts: theme.Fonts,
    rect: pygame.Rect,
    samples: Sequence[MetricSample],
) -> None:
    history = list(samples[-180:])
    plot = rect.inflate(-28, -42)
    plot.top += 18
    pygame.draw.line(surface, theme.HAIRLINE, plot.bottomleft, plot.bottomright, 1)
    pygame.draw.line(surface, theme.HAIRLINE, plot.topleft, plot.bottomleft, 1)
    if not history:
        text(
            surface,
            "Evidence appears as the population evolves",
            fonts.small,
            theme.MUTED,
            plot.center,
            anchor="center",
        )
        return
    populations = [float(sample.population) for sample in history]
    food = [float(sample.food) for sample in history]
    diversity = [sample.diversity for sample in history]
    for values, color, width in (
        (populations, theme.ION, 2),
        (food, theme.FOOD, 2),
        (diversity, theme.MUTATION, 1),
    ):
        points = _series_points(plot, values)
        if len(points) > 1:
            pygame.draw.lines(surface, color, False, points, width)
        elif points:
            pygame.draw.circle(surface, color, points[0], 2)
    text(surface, "Population", fonts.tiny, theme.ION, (plot.left, rect.top + 8))
    text(surface, "Food", fonts.tiny, theme.FOOD, (plot.left + 78, rect.top + 8))
    text(surface, "Diversity", fonts.tiny, theme.MUTATION, (plot.left + 118, rect.top + 8))
