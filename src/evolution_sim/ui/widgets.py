"""Small drawing primitives with consistent observatory styling."""

from __future__ import annotations

from collections.abc import Iterable

import pygame

from evolution_sim.ui import theme


def panel(surface: pygame.Surface, rect: pygame.Rect, *, raised: bool = False) -> None:
    pygame.draw.rect(
        surface,
        theme.TISSUE_RAISED if raised else theme.TISSUE,
        rect,
        border_radius=10,
    )
    pygame.draw.rect(surface, theme.HAIRLINE, rect, width=1, border_radius=10)


def text(
    surface: pygame.Surface,
    value: str,
    font: pygame.font.Font,
    color: pygame.Color,
    position: tuple[int, int],
    *,
    anchor: str = "topleft",
) -> pygame.Rect:
    image = font.render(value, True, color)
    rect = image.get_rect()
    setattr(rect, anchor, position)
    surface.blit(image, rect)
    return rect


def metric(
    surface: pygame.Surface,
    fonts: theme.Fonts,
    position: tuple[int, int],
    label: str,
    value: str,
    color: pygame.Color = theme.INK,
) -> None:
    x, y = position
    text(surface, value, fonts.metric, color, (x, y))
    text(surface, label, fonts.tiny, theme.MUTED, (x, y + 23))


def segmented_tabs(
    surface: pygame.Surface,
    fonts: theme.Fonts,
    rect: pygame.Rect,
    labels: Iterable[str],
    active: str,
) -> dict[str, pygame.Rect]:
    labels = tuple(labels)
    width = rect.width // len(labels)
    result: dict[str, pygame.Rect] = {}
    for index, label in enumerate(labels):
        item = pygame.Rect(rect.left + index * width, rect.top, width, rect.height)
        selected = label == active
        if selected:
            pygame.draw.rect(surface, theme.TISSUE_RAISED, item, border_radius=7)
            pygame.draw.line(
                surface,
                theme.ION,
                (item.left + 8, item.bottom - 2),
                (item.right - 8, item.bottom - 2),
                2,
            )
        text(
            surface,
            label,
            fonts.small,
            theme.INK if selected else theme.MUTED,
            item.center,
            anchor="center",
        )
        result[label] = item
    return result
