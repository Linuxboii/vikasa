"""Validated wildlife behavior contracts; scoring is owned by the controller."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from evolution_sim.model.entities import Creature, Resource


class ActionName(StrEnum):
    EXPLORE = "explore"
    FORAGE = "forage"
    REST = "rest"
    SEEK_MATE = "seek_mate"
    CARE = "care"
    FLEE = "flee"
    PATROL = "patrol"
    CHALLENGE = "challenge"


def _normalized(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number between zero and one")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a finite number between zero and one")
    return float(value)


def _scores(values: Mapping[ActionName, float], name: str) -> Mapping[ActionName, float]:
    return MappingProxyType(
        {ActionName(key): _normalized(value, name) for key, value in values.items()}
    )


@dataclass(frozen=True, slots=True)
class InstinctVector:
    """Six normalized drives in the sole serialization/presentation order."""

    values: tuple[float, ...] = (0.0,) * 6
    NAMES: ClassVar[tuple[str, ...]] = (
        "survival",
        "foraging",
        "mating",
        "offspring_care",
        "danger_avoidance",
        "territory",
    )

    def __post_init__(self) -> None:
        if len(self.values) != 6:
            raise ValueError("drives must contain six normalized values")
        object.__setattr__(self, "values", tuple(_normalized(v, "drives") for v in self.values))

    def to_dict(self) -> dict[str, float]:
        return dict(zip(self.NAMES, self.values, strict=True))


@dataclass(frozen=True, slots=True)
class BehaviorPerception:
    """Read-only tick-local candidates supplied by spatial indexes.

    Referenced entities are live; consumers must not mutate them during scoring.
    """

    food: tuple[Resource, ...] = ()
    threats: tuple[Creature, ...] = ()
    eligible_mates: tuple[Creature, ...] = ()
    dependent_offspring: tuple[Creature, ...] = ()
    local_hazard: float = 0.0
    terrain_cost: float = 0.0

    def __post_init__(self) -> None:
        for name in ("food", "threats", "eligible_mates", "dependent_offspring"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("local_hazard", "terrain_cost"):
            object.__setattr__(self, name, _normalized(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class BehaviorState:
    action: ActionName = ActionName.EXPLORE
    started_tick: int = 0
    target_kind: str | None = None
    target_id: int | None = None
    target_position: tuple[float, float] | None = None
    drives: InstinctVector = field(default_factory=InstinctVector)
    utility_breakdown: Mapping[ActionName, float] = field(default_factory=dict)
    reason: str = "Exploring nearby"

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", ActionName(self.action))
        for name in ("started_tick", "target_id"):
            value = getattr(self, name)
            if value is None and name == "target_id":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.target_kind not in {None, "food", "creature", "home", "position"}:
            raise ValueError("target_kind must name food, creature, home, or position")
        if self.target_position is not None:
            position = tuple(self.target_position)
            if len(position) != 2 or any(not math.isfinite(v) for v in position):
                raise ValueError("target_position must contain two finite numbers")
            object.__setattr__(self, "target_position", position)
        if not isinstance(self.drives, InstinctVector):
            raise ValueError("drives must be an InstinctVector")
        object.__setattr__(
            self, "utility_breakdown", _scores(self.utility_breakdown, "utility_breakdown")
        )
        if not isinstance(self.reason, str) or not self.reason or len(self.reason) > 240:
            raise ValueError("reason must contain between one and 240 characters")


@dataclass(frozen=True, slots=True)
class BehaviorDecision:
    state: BehaviorState
    scores: Mapping[ActionName, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.state, BehaviorState):
            raise ValueError("state must be a BehaviorState")
        object.__setattr__(self, "scores", _scores(self.scores, "scores"))
