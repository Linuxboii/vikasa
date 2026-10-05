"""Heritable behavioral adaptations kept separate from the stable v1 body genome."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Temperament:
    aggression: float = 0.25
    resilience: float = 0.5
    sociability: float = 0.5

    def __post_init__(self) -> None:
        if any(not np.isfinite(value) or not 0.0 <= value <= 1.0 for value in self.as_tuple()):
            raise ValueError("temperament traits must be finite values between zero and one")

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.aggression, self.resilience, self.sociability)

    def to_dict(self) -> dict[str, float]:
        return {
            "aggression": self.aggression,
            "resilience": self.resilience,
            "sociability": self.sociability,
        }

    @classmethod
    def random(cls, rng: np.random.Generator) -> Temperament:
        values = rng.beta(2.0, 2.0, size=3)
        return cls(*(float(value) for value in values))

    @classmethod
    def inherited(
        cls, first: Temperament, second: Temperament, rng: np.random.Generator
    ) -> Temperament:
        parent_values = (np.asarray(first.as_tuple()) + np.asarray(second.as_tuple())) / 2.0
        mutations = rng.normal(0.0, 0.08, size=3)
        return cls(*(float(value) for value in np.clip(parent_values + mutations, 0.0, 1.0)))

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> Temperament:
        if not data:
            return cls()
        return cls(
            aggression=float(data.get("aggression", 0.25)),
            resilience=float(data.get("resilience", 0.5)),
            sociability=float(data.get("sociability", 0.5)),
        )
