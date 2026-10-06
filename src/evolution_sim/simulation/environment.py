"""Scheduled environmental pressure independent of rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

EVENT_KINDS = {
    "drought",
    "abundance",
    "heat",
    "cold",
    "storm",
    "flood",
    "wildfire",
    "disease",
    "redistribute",
}


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
        self.movement_multiplier = 1.0
        self.health_pressure = 0.0
        self.resource_decay = 0.0
        self.seasonal_food_multiplier = 1.0
        self.seasonal_metabolic_multiplier = 1.0
        self.season = "spring"
        self.temperature = 0.58
        self.rainfall = 0.64
        self.current_tick = -1

    def schedule(self, event: EnvironmentEvent) -> None:
        self.events.append(event)
        self.events.sort(key=lambda item: (item.start_tick, item.kind, item.label))

    def update(self, tick: int) -> None:
        self.current_tick = tick
        self.food_multiplier = 1.0
        self.metabolic_multiplier = 1.0
        self.movement_multiplier = 1.0
        self.health_pressure = 0.0
        self.resource_decay = 0.0
        season_index = (tick // 96) % 4
        self.season = ("spring", "summer", "autumn", "winter")[season_index]
        self.temperature = (0.58, 0.82, 0.55, 0.3)[season_index]
        self.rainfall = (0.76, 0.38, 0.62, 0.52)[season_index]
        self.seasonal_food_multiplier = (1.12, 0.96, 0.84, 0.72)[season_index]
        self.seasonal_metabolic_multiplier = (0.96, 1.04, 0.98, 1.14)[season_index]
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
            if event.kind in {"drought", "abundance"}:
                self.food_multiplier *= event.intensity
                if event.kind == "drought":
                    severity = max(0.0, 1.0 - event.intensity)
                    self.resource_decay += 0.035 * severity
                    self.metabolic_multiplier *= 1.0 + 0.8 * severity
                    self.health_pressure += 0.15 * severity
                    self.rainfall *= min(1.0, event.intensity)
            elif event.kind == "heat":
                self.metabolic_multiplier *= event.intensity
                self.health_pressure += max(0.0, event.intensity - 1.0) * 0.45
                self.resource_decay += max(0.0, event.intensity - 1.0) * 0.012
                self.temperature = min(1.0, self.temperature + 0.15 * event.intensity)
            elif event.kind == "cold":
                self.metabolic_multiplier *= event.intensity
                self.health_pressure += max(0.0, event.intensity - 1.0) * 0.25
                self.temperature = max(0.0, self.temperature - 0.15 * event.intensity)
            elif event.kind == "storm":
                self.movement_multiplier *= event.intensity
                self.health_pressure += 0.35 * event.intensity
                self.resource_decay += 0.012 * event.intensity
                self.rainfall = min(1.0, self.rainfall + 0.2 * event.intensity)
            elif event.kind == "flood":
                self.food_multiplier *= max(0.1, 1.0 / event.intensity)
                self.health_pressure += 0.45 * event.intensity
                self.resource_decay += 0.025 * event.intensity
            elif event.kind == "wildfire":
                self.food_multiplier *= max(0.05, 1.0 - 0.75 * event.intensity)
                self.health_pressure += 0.8 * event.intensity
                self.resource_decay += 0.055 * event.intensity
            elif event.kind == "disease":
                self.health_pressure += 0.4 * event.intensity

    @property
    def active_events(self) -> tuple[EnvironmentEvent, ...]:
        return tuple(event for event in self.events if event.active_at(self.current_tick))

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "history": list(self.history),
            "food_multiplier": self.food_multiplier,
            "metabolic_multiplier": self.metabolic_multiplier,
            "movement_multiplier": self.movement_multiplier,
            "health_pressure": self.health_pressure,
            "resource_decay": self.resource_decay,
            "seasonal_food_multiplier": self.seasonal_food_multiplier,
            "seasonal_metabolic_multiplier": self.seasonal_metabolic_multiplier,
            "season": self.season,
            "temperature": self.temperature,
            "rainfall": self.rainfall,
            "current_tick": self.current_tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EnvironmentState:
        state = cls()
        state.events = [EnvironmentEvent.from_dict(item) for item in data.get("events", [])]
        state.history = [dict(item) for item in data.get("history", [])]
        state.food_multiplier = float(data.get("food_multiplier", 1.0))
        state.metabolic_multiplier = float(data.get("metabolic_multiplier", 1.0))
        state.movement_multiplier = float(data.get("movement_multiplier", 1.0))
        state.health_pressure = float(data.get("health_pressure", 0.0))
        state.resource_decay = float(data.get("resource_decay", 0.0))
        state.seasonal_food_multiplier = float(data.get("seasonal_food_multiplier", 1.0))
        state.seasonal_metabolic_multiplier = float(
            data.get("seasonal_metabolic_multiplier", 1.0)
        )
        state.season = str(data.get("season", "spring"))
        state.temperature = float(data.get("temperature", 0.58))
        state.rainfall = float(data.get("rainfall", 0.64))
        state.current_tick = int(data.get("current_tick", -1))
        return state
