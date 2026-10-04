"""Validated launch-time customization for the graphical laboratory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evolution_sim.config import SimulationConfig


@dataclass(frozen=True, slots=True)
class Parameter:
    label: str
    path: tuple[str, ...]
    minimum: float
    maximum: float
    step: float
    style: str = "number"


PARAMETERS = (
    Parameter("Founders", ("initial_population",), 25, 500, 25, "integer"),
    Parameter("Food at launch", ("resources", "initial_count"), 25, 1_000, 25, "integer"),
    Parameter("Food growth", ("resources", "spawn_rate"), 0.05, 5.0, 0.05, "decimal"),
    Parameter("Mutation chance", ("genome", "mutation_probability"), 0.0, 0.5, 0.01, "percent"),
    Parameter("Mutation spread", ("genome", "mutation_sigma"), 0.005, 0.3, 0.005, "decimal"),
    Parameter("Population ceiling", ("reproduction", "population_cap"), 100, 2_000, 100, "integer"),
    Parameter("Maximum lifespan", ("maximum_age",), 250, 10_000, 250, "integer"),
    Parameter("Seed", ("seed",), 0, 999_999, 1, "integer"),
)


PRESETS: dict[str, dict[str, Any]] = {
    "Balanced": {},
    "Bloom": {
        "seed": 2026,
        "initial_population": 150,
        "resources": {"initial_count": 350, "spawn_rate": 1.8, "maximum_count": 700},
        "reproduction": {"population_cap": 900},
        "genome": {"mutation_probability": 0.06, "mutation_sigma": 0.04},
    },
    "Scarcity": {
        "seed": 303,
        "initial_population": 80,
        "resources": {"initial_count": 45, "spawn_rate": 0.15, "maximum_count": 180},
        "reproduction": {"population_cap": 500},
        "genome": {"mutation_probability": 0.1, "mutation_sigma": 0.06},
    },
    "Hypermutation": {
        "seed": 404,
        "initial_population": 120,
        "resources": {"initial_count": 220, "spawn_rate": 1.0, "maximum_count": 500},
        "reproduction": {"population_cap": 700},
        "genome": {"mutation_probability": 0.3, "mutation_sigma": 0.15},
    },
}


def _deep_update(target: dict[str, Any], changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _read_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for part in path:
        current = current[part]
    return current


def _write_path(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = data
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value


class CustomizationPanel:
    """Editable, validation-backed launch settings independent of rendering."""

    def __init__(self, config: SimulationConfig, seed: int) -> None:
        self.base_config = config
        self.base_seed = seed
        self.config = config
        self.seed = seed
        self.selected_index = 0
        self.active_preset = "Balanced"

    @property
    def selected(self) -> Parameter:
        return PARAMETERS[self.selected_index]

    @property
    def selected_label(self) -> str:
        return self.selected.label

    @property
    def value(self) -> float:
        return self.value_for(self.selected_index)

    def value_for(self, index: int) -> float:
        parameter = PARAMETERS[index]
        if parameter.path == ("seed",):
            return float(self.seed)
        return float(_read_path(self.config.to_dict(), parameter.path))

    @property
    def value_label(self) -> str:
        return self.value_label_for(self.selected_index)

    def value_label_for(self, index: int) -> str:
        parameter = PARAMETERS[index]
        value = self.value_for(index)
        if parameter.style == "percent":
            return f"{value:.0%}"
        if parameter.style == "integer":
            return f"{int(value):,}"
        return f"{value:.3g}"

    @property
    def progress(self) -> float:
        return self.progress_for(self.selected_index)

    def progress_for(self, index: int) -> float:
        parameter = PARAMETERS[index]
        return (self.value_for(index) - parameter.minimum) / (parameter.maximum - parameter.minimum)

    def select(self, label: str) -> None:
        self.selected_index = next(
            index for index, parameter in enumerate(PARAMETERS) if parameter.label == label
        )

    def move_selection(self, direction: int) -> None:
        self.selected_index = (self.selected_index + direction) % len(PARAMETERS)

    def adjust(self, direction: int) -> None:
        self.set_value(self.value + direction * self.selected.step)

    def set_value(self, value: float) -> None:
        parameter = self.selected
        value = min(parameter.maximum, max(parameter.minimum, value))
        if parameter.style == "integer":
            value = round(value)
        if parameter.path == ("seed",):
            self.seed = int(value)
            self.active_preset = "Custom"
            return
        data = self.config.to_dict()
        _write_path(data, parameter.path, value)
        if parameter.path == ("initial_population",):
            data["reproduction"]["population_cap"] = max(
                data["reproduction"]["population_cap"], int(value)
            )
        elif parameter.path == ("resources", "initial_count"):
            data["resources"]["maximum_count"] = max(data["resources"]["maximum_count"], int(value))
        elif parameter.path == ("reproduction", "population_cap"):
            data["initial_population"] = min(data["initial_population"], int(value))
        self.config = SimulationConfig.from_dict(data)
        self.active_preset = "Custom"

    def apply_preset(self, name: str) -> None:
        if name not in PRESETS:
            raise ValueError(f"Unknown preset: {name}")
        data = self.base_config.to_dict()
        changes = dict(PRESETS[name])
        self.seed = int(changes.pop("seed", self.base_seed))
        _deep_update(data, changes)
        self.config = SimulationConfig.from_dict(data)
        self.active_preset = name
