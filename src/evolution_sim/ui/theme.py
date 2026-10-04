"""Living-observatory visual tokens and typography."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

MIDNIGHT = pygame.Color("#06101a")
DEEP_WATER = pygame.Color("#0a1724")
TISSUE = pygame.Color("#102536")
TISSUE_RAISED = pygame.Color("#163247")
HAIRLINE = pygame.Color("#28495b")
INK = pygame.Color("#d7e7ee")
MUTED = pygame.Color("#83a1af")
ION = pygame.Color("#43d9cf")
ION_SOFT = pygame.Color("#1f8888")
FOOD = pygame.Color("#f5c65d")
PRESSURE = pygame.Color("#ff7a6b")
MUTATION = pygame.Color("#cf8df4")
GOOD = pygame.Color("#77d59b")


@dataclass(slots=True)
class Fonts:
    display: pygame.font.Font
    title: pygame.font.Font
    body: pygame.font.Font
    small: pygame.font.Font
    tiny: pygame.font.Font
    metric: pygame.font.Font

    @classmethod
    def load(cls) -> Fonts:
        return cls(
            display=pygame.font.SysFont("bahnschrift", 25, bold=True),
            title=pygame.font.SysFont("bahnschrift", 18, bold=True),
            body=pygame.font.SysFont("segoeui", 16),
            small=pygame.font.SysFont("segoeui", 14),
            tiny=pygame.font.SysFont("segoeui", 12),
            metric=pygame.font.SysFont("bahnschrift", 18, bold=True),
        )


def mix(first: pygame.Color, second: pygame.Color, amount: float) -> pygame.Color:
    amount = max(0.0, min(1.0, amount))
    return pygame.Color(
        round(first.r + (second.r - first.r) * amount),
        round(first.g + (second.g - first.g) * amount),
        round(first.b + (second.b - first.b) * amount),
    )
