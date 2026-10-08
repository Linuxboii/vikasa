"""Scheduled environmental pressure independent of rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from evolution_sim.config import EcologyConfig

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


class HabitatField:
    """Finite plant energy and bucket water with conservative grid transport.

    Units are illustrative simulation units, not measured vegetation biomass.
    Food creation transfers energy out of this field. Photosynthesis is an
    explicitly measured external input, not a closed thermodynamic system.
    """

    LEDGER_KEYS = ("initial_biomass", "grown_energy", "weather_loss", "harvested_energy",
                   "initial_water", "rain_input", "evaporation", "transpiration")

    def __init__(self, settings: EcologyConfig, *, width: float, height: float,
                 boundary: str) -> None:
        self.settings = settings
        self.width, self.height, self.boundary = width, height, boundary
        self.biomass = np.full((settings.rows, settings.columns),
                              settings.capacity * settings.initial_fraction, dtype=float)
        self.water = np.full_like(self.biomass, 0.6)
        self.steps = 0
        self.ledger = dict.fromkeys(self.LEDGER_KEYS, 0.0)
        self.ledger["initial_biomass"] = float(self.biomass.sum())
        self.ledger["initial_water"] = float(self.water.sum())

    def _diffuse(self, values: np.ndarray, coefficient: float) -> np.ndarray:
        padded = np.pad(values, 1, mode="wrap" if self.boundary == "wrap" else "edge")
        return ((1 - 4 * coefficient) * values + coefficient *
                (padded[2:, 1:-1] + padded[:-2, 1:-1]
                 + padded[1:-1, 2:] + padded[1:-1, :-2]))

    def step(self, weather: EnvironmentState) -> None:
        cfg = self.settings
        rain = np.minimum(1 - self.water, cfg.rainfall_rate * weather.rainfall)
        self.water += rain
        evaporated = np.minimum(self.water, cfg.evaporation_rate * (.5 + weather.temperature))
        self.water -= evaporated
        moisture = np.divide(self.water, cfg.water_half_saturation + self.water,
                             out=np.zeros_like(self.water),
                             where=cfg.water_half_saturation + self.water > 0)
        thermal = math.exp(-((weather.temperature - .6) / .35) ** 2)
        rate = (cfg.growth_rate * weather.food_multiplier
                * weather.seasonal_food_multiplier * thermal * moisture)
        # Exact local logistic flow, avoiding Euler overshoot at high productivity.
        old = self.biomass.copy()
        grown = np.divide(cfg.capacity * old,
                          old + (cfg.capacity - old) * np.exp(-rate),
                          out=np.zeros_like(old), where=old > 0) - old
        if cfg.transpiration_rate > 0:
            grown = np.minimum(grown, self.water * cfg.capacity / cfg.transpiration_rate)
        used = grown / cfg.capacity * cfg.transpiration_rate
        self.water -= used
        self.biomass += grown
        lost = self.biomass * (-math.expm1(-weather.resource_decay))
        self.biomass -= lost
        self.biomass = self._diffuse(self.biomass, cfg.biomass_diffusion)
        self.water = self._diffuse(self.water, cfg.water_diffusion)
        self.ledger["grown_energy"] += float(grown.sum())
        self.ledger["weather_loss"] += float(lost.sum())
        self.ledger["rain_input"] += float(rain.sum())
        self.ledger["evaporation"] += float(evaporated.sum())
        self.ledger["transpiration"] += float(used.sum())
        self.steps += 1

    def harvest(self, energy: float, rng: np.random.Generator) -> np.ndarray | None:
        result = self._harvest(energy, rng, partial=False)
        return result[0] if result is not None else None

    def harvest_patch(self, energy: float,
                      rng: np.random.Generator) -> tuple[np.ndarray, float] | None:
        """Allow partial edible patches; never invent their requested energy."""
        return self._harvest(energy, rng, partial=True)

    def _harvest(self, energy: float, rng: np.random.Generator, *,
                 partial: bool) -> tuple[np.ndarray, float] | None:
        if not math.isfinite(energy) or energy <= 0:
            raise ValueError("Harvest energy must be finite and positive")
        # Leave a one-percent seed reservoir. A fully dead cell regrows only by
        # actual transport from neighboring living cells, never spontaneous food.
        available = np.maximum(0., self.biomass.ravel() - self.settings.capacity * .01)
        minimum = min(energy, 1.) if partial else energy
        weights = np.where(available >= minimum, available, 0.)
        total = float(weights.sum())
        if total == 0:
            return None
        index = int(rng.choice(len(weights), p=weights / total))
        row, column = divmod(index, self.settings.columns)
        energy = min(energy, float(available[index]))
        self.biomass[row, column] -= energy
        self.ledger["harvested_energy"] += energy
        position = ((np.array([column, row]) + rng.random(2))
                    * np.array([self.width / self.settings.columns,
                                self.height / self.settings.rows]))
        return position, energy

    def summary(self) -> dict[str, float | int]:
        biomass, water = float(self.biomass.sum()), float(self.water.sum())
        return {**self.ledger, "steps": self.steps, "plant_energy": biomass,
                "mean_water": float(self.water.mean()),
                "biomass_fraction": biomass / (self.biomass.size * self.settings.capacity),
                "biomass_balance_residual": (self.ledger["initial_biomass"]
                    + self.ledger["grown_energy"] - self.ledger["weather_loss"]
                    - self.ledger["harvested_energy"] - biomass),
                "water_balance_residual": (self.ledger["initial_water"]
                    + self.ledger["rain_input"] - self.ledger["evaporation"]
                    - self.ledger["transpiration"] - water)}

    def to_dict(self) -> dict[str, Any]:
        return {"biomass": self.biomass.tolist(), "water": self.water.tolist(),
                "steps": self.steps, "ledger": dict(self.ledger)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any], settings: EcologyConfig, *,
                  width: float, height: float, boundary: str) -> HabitatField:
        field = cls(settings, width=width, height=height, boundary=boundary)
        for name, maximum in (("biomass", settings.capacity), ("water", 1.)):
            values = np.asarray(payload[name], dtype=float)
            if (values.shape != field.biomass.shape or not np.isfinite(values).all()
                    or np.any(values < -1e-12) or np.any(values > maximum + 1e-12)):
                raise ValueError(f"Invalid habitat.{name}")
            setattr(field, name, values)
        steps = payload["steps"]
        if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
            raise ValueError("Invalid habitat.steps")
        field.steps = steps
        ledger = payload["ledger"]
        if set(ledger) != set(cls.LEDGER_KEYS):
            raise ValueError("Invalid habitat ledger fields")
        for key, value in ledger.items():
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError(f"Invalid habitat ledger {key}")
        field.ledger = dict(ledger)
        expected_initial = (settings.rows * settings.columns * settings.capacity
                            * settings.initial_fraction)
        if (not math.isclose(field.ledger["initial_biomass"], expected_initial, rel_tol=1e-12)
                or not math.isclose(field.ledger["initial_water"],
                                    settings.rows * settings.columns * .6,
                                    rel_tol=1e-12)):
            raise ValueError("Habitat initial ledger does not match configured initialization")
        initial_keys = {"initial_biomass", "initial_water", "harvested_energy"}
        if steps == 0 and any(field.ledger[key] != 0 for key in cls.LEDGER_KEYS
                              if key not in initial_keys):
            raise ValueError("Unadvanced habitat cannot contain dynamic fluxes")
        errors = field.audit()
        if errors:
            raise ValueError("; ".join(errors))
        return field

    def audit(self) -> list[str]:
        result = self.summary()
        errors = []
        for name, total in (("biomass", self.ledger["initial_biomass"]
                            + self.ledger["grown_energy"]),
                            ("water", self.ledger["initial_water"] + self.ledger["rain_input"])):
            if abs(result[f"{name}_balance_residual"]) > 1e-9 * max(1, total):
                errors.append(f"Habitat {name} ledger is not balanced")
        if (not np.isfinite(self.biomass).all() or not np.isfinite(self.water).all()
                or np.any(self.biomass < -1e-12)
                or np.any(self.biomass > self.settings.capacity + 1e-9)
                or np.any(self.water < -1e-12) or np.any(self.water > 1 + 1e-12)):
            errors.append("Habitat fields are outside finite physical bounds")
        return errors
