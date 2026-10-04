"""Responsive geometry for the laboratory workspace."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

MINIMUM_SIZE = (1100, 700)


@dataclass(frozen=True, slots=True)
class Layout:
    window: pygame.Rect
    top_bar: pygame.Rect
    world: pygame.Rect
    sidebar: pygame.Rect
    chart_strip: pygame.Rect


def compute_layout(width: int, height: int) -> Layout:
    width = max(MINIMUM_SIZE[0], int(width))
    height = max(MINIMUM_SIZE[1], int(height))
    margin = 16
    gap = 12
    top_height = 68
    sidebar_width = max(276, min(330, round(width * 0.225)))
    chart_height = max(154, min(204, round(height * 0.205)))
    top_bar = pygame.Rect(margin, margin, width - margin * 2, top_height)
    content_top = top_bar.bottom + gap
    content_bottom = height - margin - chart_height - gap
    world = pygame.Rect(
        margin,
        content_top,
        width - margin * 2 - sidebar_width - gap,
        content_bottom - content_top,
    )
    sidebar = pygame.Rect(world.right + gap, content_top, sidebar_width, world.height)
    chart_strip = pygame.Rect(margin, world.bottom + gap, width - margin * 2, chart_height)
    return Layout(pygame.Rect(0, 0, width, height), top_bar, world, sidebar, chart_strip)
