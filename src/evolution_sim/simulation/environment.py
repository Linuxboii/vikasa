"""Scheduled environmental pressure independent of rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

EVENT_KINDS = {"drought", "abundance", "heat", "redistribute"}


@dataclass(frozen=True, slots=True)
class EnvironmentEvent:
    kind: str
    start_tick: int
    duration: int
    intensity: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"Unsupported environmental event: {self.kind}")
        if self.start_tick < 0:
            raise ValueError("start_tick must be non-negative")
        if self.duration <= 0:
            raise ValueError("duration must be positive")
        if not math.isfinite(self.intensity) or self.intensity <= 0:
            raise ValueError("intensity must be finite and positive")

    @property
    def end_tick(self) -> int:
        return self.start_tick + self.duration

    def active_at(self, tick: int) -> bool:
        return self.start_tick <= tick < self.end_tick

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start_tick": self.start_tick,
            "duration": self.duration,
            "intensity": self.intensity,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentEvent:
        return cls(
            kind=str(data["kind"]),
            start_tick=int(data["start_tick"]),
            duration=int(data["duration"]),
            intensity=float(data["intensity"]),
            label=str(data.get("label", "")),
        )


class EnvironmentState:
    def __init__(self) -> None:
        self.events: list[EnvironmentEvent] = []
        self.history: list[dict[str, Any]] = []
        self.food_multiplier = 1.0
        self.metabolic_multiplier = 1.0

    def schedule(self, event: EnvironmentEvent) -> None:
        self.events.append(event)
        self.events.sort(key=lambda item: (item.start_tick, item.kind, item.label))

    def update(self, tick: int) -> None:
        self.food_multiplier = 1.0
        self.metabolic_multiplier = 1.0
        recorded = {
            (entry["kind"], entry["start_tick"], entry["duration"], entry["intensity"])
            for entry in self.history
        }
        for event in self.events:
            key = (event.kind, event.start_tick, event.duration, event.intensity)
            if tick >= event.start_tick and key not in recorded:
                self.history.append(event.to_dict())
                recorded.add(key)
            if not event.active_at(tick):
                continue
            if event.kind == "drought" or event.kind == "abundance":
                self.food_multiplier *= event.intensity
            elif event.kind == "heat":
                self.metabolic_multiplier *= event.intensity

    @property
    def active_events(self) -> tuple[EnvironmentEvent, ...]:
        return tuple(
            event
            for event in self.events
            if (self.food_multiplier != 1.0 or self.metabolic_multiplier != 1.0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "history": list(self.history),
            "food_multiplier": self.food_multiplier,
            "metabolic_multiplier": self.metabolic_multiplier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentState:
        state = cls()
        state.events = [EnvironmentEvent.from_dict(item) for item in data.get("events", [])]
        state.history = [dict(item) for item in data.get("history", [])]
        state.food_multiplier = float(data.get("food_multiplier", 1.0))
        state.metabolic_multiplier = float(data.get("metabolic_multiplier", 1.0))
        return state
