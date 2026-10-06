"""Validated wildlife behavior contracts; scoring is owned by the controller."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

import numpy as np

from evolution_sim.config import SimulationConfig
from evolution_sim.model.genome import Trait
from evolution_sim.model.math2d import distance_sq

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
        {
            (key if isinstance(key, ActionName) else ActionName(key)): _normalized(value, name)
            for key, value in values.items()
        }
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
            if len(position) != 2 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in position
            ):
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
        if self.scores is not self.state.utility_breakdown:
            object.__setattr__(self, "scores", _scores(self.scores, "scores"))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


class BehaviorController:
    """Score perceived opportunities without modifying creatures or consuming hidden RNG.

    Utility is clamp(affinity dot drives + reward - travel - exposure - conflict, 0, 1).
    Affinities below use InstinctVector.NAMES order. Invalid actions are excluded
    (equivalent to negative infinity for arbitration); displayed scores stay in [0, 1].
    Travel is 0.12 * normalized distance * speed/4 / metabolism plus terrain cost.
    Exposure is danger * 0.25 for active actions, 0.05 for rest, zero for flee.
    Conflict is threat pressure * 0.15 for courtship, or * 0.30 / relative strength
    for challenge. Near ties are within one temperature of the top utility, and
    use a seeded softmax only after emergency preemption and hysteresis.
    """

    AFFINITIES: ClassVar[dict[ActionName, tuple[float, ...]]] = {
        ActionName.EXPLORE: (0.10, 0.15, 0.0, 0.0, 0.0, 0.0),
        ActionName.FORAGE: (0.35, 0.65, 0.0, 0.0, 0.0, 0.0),
        ActionName.REST: (0.55, 0.0, 0.0, 0.0, 0.0, 0.0),
        ActionName.SEEK_MATE: (0.0, 0.0, 0.65, 0.0, 0.0, 0.0),
        ActionName.CARE: (0.0, 0.0, 0.0, 0.75, 0.0, 0.0),
        ActionName.FLEE: (0.15, 0.0, 0.0, 0.0, 0.85, 0.0),
        ActionName.PATROL: (0.0, 0.0, 0.0, 0.0, 0.0, 0.65),
        ActionName.CHALLENGE: (0.0, 0.0, 0.0, 0.0, 0.0, 0.45),
    }
    REASONS: ClassVar[dict[ActionName, str]] = {
        ActionName.EXPLORE: "Searching nearby for better habitat",
        ActionName.FORAGE: "Following food scent to replenish energy",
        ActionName.REST: "Resting to conserve energy and recover",
        ActionName.SEEK_MATE: "Approaching an eligible mate",
        ActionName.CARE: "Staying near hungry or vulnerable young",
        ActionName.FLEE: "Moving away from danger",
        ActionName.PATROL: "Returning toward the home range",
        ActionName.CHALLENGE: "Defending the home range under local competition",
    }

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def _eligible(self, creature: Creature, tick: int) -> bool:
        cooldown = max(
            1,
            round(
                self.config.reproduction.cooldown * (1.0 - 0.5 * creature.genome[Trait.FERTILITY])
            ),
        )
        return (
            creature.alive
            and creature.age >= self.config.reproduction.minimum_age
            and creature.energy >= creature.genome[Trait.REPRODUCTION_THRESHOLD]
            and tick - creature.last_reproduction_tick >= cooldown
        )

    def _dependents(
        self, creature: Creature, perception: BehaviorPerception
    ) -> tuple[Creature, ...]:
        return tuple(
            child
            for child in perception.dependent_offspring
            if child.alive
            and child.parents is not None
            and creature.id in child.parents
            and child.age < self.config.behavior.dependent_age_ticks
            and distance_sq(creature.position, child.position)
            <= self.config.behavior.care_radius**2
        )

    @staticmethod
    def threat_pressure(creature: Creature, threat: Creature) -> float:
        if not threat.alive or threat.id == creature.id:
            return 0.0
        proximity = _clamp(
            1.0
            - math.sqrt(distance_sq(creature.position, threat.position))
            / max(1.0, creature.genome[Trait.PERCEPTION])
        )
        relative_size = threat.genome[Trait.SIZE] / creature.genome[Trait.SIZE]
        strength = _clamp(relative_size / 1.5)
        return _clamp(
            proximity * threat.temperament.aggression * strength * (0.85 + 0.15 * creature.injury)
        )

    def drives(
        self,
        creature: Creature,
        perception: BehaviorPerception,
        maximum_energy: float,
        tick: int = 0,
    ) -> InstinctVector:
        food_rewards = {
            food.id: self.food_reward(creature, food, maximum_energy) for food in perception.food
        }
        threats = {
            threat.id: self.threat_pressure(creature, threat) for threat in perception.threats
        }
        return self._drives(creature, perception, maximum_energy, tick, food_rewards, threats)

    def _drives(
        self,
        creature: Creature,
        perception: BehaviorPerception,
        maximum_energy: float,
        tick: int,
        food_rewards: dict[int, float],
        threats: dict[int, float],
    ) -> InstinctVector:
        if not math.isfinite(maximum_energy) or maximum_energy <= 0:
            raise ValueError("maximum_energy must be finite and positive")
        deficit = _clamp(1.0 - creature.energy / maximum_energy)
        survival = _clamp(0.65 * (1.0 - creature.energy / maximum_energy) + 0.35 * creature.injury)
        hunger = max(creature.hunger, deficit)
        food_reward = max(food_rewards.values(), default=0.0)
        foraging = _clamp(hunger * (0.5 + 0.5 * food_reward)) if perception.food else 0.0
        danger = max(
            perception.local_hazard,
            max(threats.values(), default=0.0),
        )
        mates = [
            mate
            for mate in perception.eligible_mates
            if mate.id != creature.id and self._eligible(mate, tick)
        ]
        mating = 0.0
        if self._eligible(creature, tick) and mates and survival < 0.55 and creature.injury < 0.65:
            proximity = max(
                _clamp(
                    1.0
                    - math.sqrt(distance_sq(creature.position, mate.position))
                    / max(1.0, creature.genome[Trait.PERCEPTION])
                )
                for mate in mates
            )
            mating = _clamp(
                (0.5 + 0.5 * creature.energy / maximum_energy)
                * proximity
                * (0.7 + 0.3 * creature.temperament.sociability)
            )
        care = max(
            (
                _clamp(
                    0.35 * (1.0 - child.age / max(1, self.config.behavior.dependent_age_ticks))
                    + 0.45 * _clamp(1.0 - child.energy / maximum_energy)
                    + 0.20 * max(child.injury, danger)
                )
                * (0.6 + 0.4 * creature.temperament.sociability)
                for child in self._dependents(creature, perception)
            ),
            default=0.0,
        )
        displacement = math.sqrt(distance_sq(creature.position, creature.home_center))
        territory = _clamp(0.35 + 0.65 * displacement / creature.home_radius)
        territory = territory * (1.0 - 0.75 * hunger) * (1.0 - 0.5 * danger)
        return InstinctVector((survival, foraging, mating, care, danger, territory))

    @staticmethod
    def food_reward(creature: Creature, food: Resource, maximum_energy: float) -> float:
        proximity = _clamp(
            1.0
            - math.sqrt(distance_sq(creature.position, food.position))
            / max(1.0, creature.genome[Trait.PERCEPTION])
        )
        return _clamp(food.energy / max(1.0, maximum_energy * 0.15)) * proximity

    def decide(
        self,
        creature: Creature,
        perception: BehaviorPerception,
        maximum_energy: float,
        tick: int,
        rng: np.random.Generator,
    ) -> BehaviorDecision:
        food_rewards = {
            food.id: self.food_reward(creature, food, maximum_energy) for food in perception.food
        }
        threat_pressures = {
            threat.id: self.threat_pressure(creature, threat) for threat in perception.threats
        }
        drives = self._drives(
            creature, perception, maximum_energy, tick, food_rewards, threat_pressures
        )
        survival, _, mating, care, danger, territory = drives.values
        patrol_target = creature.behavior_state.target_position
        if (
            creature.behavior_state.action is not ActionName.PATROL
            or creature.behavior_state.target_kind != "home"
            or patrol_target is None
            or distance_sq(creature.position, patrol_target) <= 1.0
        ):
            # Keep a patrol waypoint until reached, then sample a new point near
            # the range edge. Clipping to world bounds can only shorten its radius.
            angle = float(rng.uniform(0.0, math.tau))
            radius = creature.home_radius * float(rng.uniform(0.9, 1.0))
            patrol_target = (
                float(
                    min(
                        max(0.0, creature.home_center[0] + radius * math.cos(angle)),
                        self.config.world.width,
                    )
                ),
                float(
                    min(
                        max(0.0, creature.home_center[1] + radius * math.sin(angle)),
                        self.config.world.height,
                    )
                ),
            )
            if distance_sq(patrol_target, creature.home_center) == 0.0:
                # At a world edge, clipping an outward sample can collapse it
                # onto the home center. Choose the longest feasible inward
                # axis so patrol still has somewhere to go without leaving the
                # world or the home range.
                width, height = self.config.world.width, self.config.world.height
                cx, cy = (float(value) for value in creature.home_center)
                feasible = (
                    (min(creature.home_radius, width - cx), (1.0, 0.0)),
                    (min(creature.home_radius, cx), (-1.0, 0.0)),
                    (min(creature.home_radius, height - cy), (0.0, 1.0)),
                    (min(creature.home_radius, cy), (0.0, -1.0)),
                )
                distance, inward = max(feasible, key=lambda option: option[0])
                patrol_target = (
                    cx + inward[0] * distance,
                    cy + inward[1] * distance,
                )
        targets: dict[ActionName, tuple[str | None, int | None, tuple[float, float] | None]] = {
            ActionName.EXPLORE: (None, None, None),
            ActionName.REST: (None, None, None),
            ActionName.PATROL: ("home", None, patrol_target),
        }
        rewards = {
            ActionName.EXPLORE: 0.25 * (1.0 - survival),
            ActionName.REST: 0.4 * creature.injury,
            ActionName.PATROL: 0.05 * (1.0 - danger),
        }
        if perception.food:
            food = max(
                perception.food,
                key=lambda item: (
                    food_rewards[item.id]
                    - 0.12
                    * math.sqrt(distance_sq(creature.position, item.position))
                    / max(1.0, creature.genome[Trait.PERCEPTION]),
                    -item.id,
                ),
            )
            targets[ActionName.FORAGE] = ("food", food.id, tuple(float(v) for v in food.position))
            rewards[ActionName.FORAGE] = 0.25 * food_rewards[food.id]
        if mating > 0:
            mates = [
                item
                for item in perception.eligible_mates
                if self._eligible(item, tick) and item.id != creature.id
            ]
            # A viable courtship target persists instead of changing at every near encounter.
            mate = next(
                (
                    item
                    for item in mates
                    if creature.behavior_state.action is ActionName.SEEK_MATE
                    and item.id == creature.behavior_state.target_id
                ),
                None,
            )
            if mate is None:
                mate = min(
                    mates, key=lambda item: (distance_sq(creature.position, item.position), item.id)
                )
            targets[ActionName.SEEK_MATE] = (
                "creature",
                mate.id,
                tuple(float(v) for v in mate.position),
            )
            rewards[ActionName.SEEK_MATE] = 0.25 * (1.0 - survival)
        if care > 0:
            child = min(
                self._dependents(creature, perception),
                key=lambda item: (distance_sq(creature.position, item.position), item.id),
            )
            targets[ActionName.CARE] = (
                "creature",
                child.id,
                tuple(float(v) for v in child.position),
            )
            rewards[ActionName.CARE] = 0.2 * care
        threats = [item for item in perception.threats if item.alive and item.id != creature.id]
        if danger > 0:
            if threats:
                threat = max(threats, key=lambda item: (threat_pressures[item.id], -item.id))
                targets[ActionName.FLEE] = (
                    "creature",
                    threat.id,
                    tuple(float(v) for v in threat.position),
                )
            else:
                # Hazards are world-wide in this model: retreat toward familiar habitat.
                targets[ActionName.FLEE] = (
                    "home",
                    None,
                    tuple(float(v) for v in creature.home_center),
                )
            rewards[ActionName.FLEE] = 0.1 * danger
        strength = 1.0
        if threats and creature.temperament.aggression >= 0.5 and survival < 0.45 and danger < 0.75:
            rival = min(
                threats, key=lambda item: (distance_sq(creature.position, item.position), item.id)
            )
            strength = creature.genome[Trait.SIZE] / rival.genome[Trait.SIZE]
            if strength >= 0.8 and territory > 0.2:
                targets[ActionName.CHALLENGE] = (
                    "creature",
                    rival.id,
                    tuple(float(v) for v in rival.position),
                )
                contest = max(danger, creature.hunger, rival.hunger)
                rewards[ActionName.CHALLENGE] = creature.temperament.aggression * (
                    0.20 * territory
                    + 0.55 * contest
                    + 0.25 * _clamp(creature.satisfaction_vector[3])
                )
        scores = {}
        for action, (_, _, position) in targets.items():
            affinity = sum(
                weight * drive
                for weight, drive in zip(self.AFFINITIES[action], drives.values, strict=True)
            )
            distance = (
                0.0 if position is None else math.sqrt(distance_sq(creature.position, position))
            )
            travel = (
                0.12
                * _clamp(distance / max(1.0, creature.genome[Trait.PERCEPTION]))
                * creature.genome[Trait.SPEED]
                / 4.0
                / creature.genome[Trait.METABOLISM]
            )
            if action is not ActionName.REST:
                travel += 0.08 * perception.terrain_cost
            exposure = danger * (0.05 if action is ActionName.REST else 0.25)
            if action is ActionName.FLEE:
                exposure = 0.0
            conflict = (
                0.15 * danger
                if action is ActionName.SEEK_MATE
                else 0.30 * danger / strength
                if action is ActionName.CHALLENGE
                else 0.0
            )
            scores[action] = _clamp(
                affinity + rewards.get(action, 0.0) - travel - exposure - conflict
            )
        best = max(scores, key=scores.get)
        emergency = False
        if danger > 0 and danger >= self.config.behavior.danger_preempt_threshold:
            best, emergency = ActionName.FLEE, True
        elif survival >= 0.65 or creature.injury >= 0.65:
            best = (
                ActionName.REST
                if creature.injury >= 0.65
                else (ActionName.FORAGE if ActionName.FORAGE in scores else ActionName.EXPLORE)
            )
            emergency = True
        current = creature.behavior_state
        if not emergency:
            if current.action in scores and scores[best] <= (
                scores[current.action] + self.config.behavior.hysteresis_margin
            ):
                best = current.action
            else:
                temperature = self.config.behavior.softmax_temperature
                tied = [action for action in scores if scores[best] - scores[action] <= temperature]
                if len(tied) > 1:
                    weights = np.exp(
                        [(scores[action] - scores[best]) / temperature for action in tied]
                    )
                    best = tied[int(rng.choice(len(tied), p=weights / weights.sum()))]
        kind, target_id, position = targets[best]
        state = BehaviorState(
            best,
            current.started_tick if best is current.action else tick,
            kind,
            target_id,
            position,
            drives,
            scores,
            self.REASONS[best],
        )
        return BehaviorDecision(state, state.utility_breakdown)
