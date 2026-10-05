"""Headless-first deterministic artificial-life engine."""

from __future__ import annotations

import math

import numpy as np

from evolution_sim.analytics.metrics import MetricsRecorder
from evolution_sim.config import SimulationConfig
from evolution_sim.model.entities import Creature, Resource
from evolution_sim.model.genetics import crossover, mutate
from evolution_sim.model.genome import Trait, random_genome
from evolution_sim.model.lineage import LineageStore
from evolution_sim.model.math2d import distance_sq, reflect_bounds, unit_vector
from evolution_sim.model.spatial import SpatialHash
from evolution_sim.model.temperament import Temperament
from evolution_sim.simulation.behavior import (
    ActionName,
    BehaviorController,
    BehaviorPerception,
)
from evolution_sim.simulation.culture import CultureLedger
from evolution_sim.simulation.environment import EnvironmentState
from evolution_sim.simulation.snapshots import (
    CreatureSnapshot,
    ResourceSnapshot,
    WorldSnapshot,
)

HOME_MIGRATION_PERSISTENCE_TICKS = 24
HOME_MIGRATION_RATE = 0.005
CARE_PARENT_RESERVE = 0.35


class SimulationEngine:
    """Own all evolutionary state and advance it in stable tick order."""

    def __init__(self, config: SimulationConfig, seed: int = 0) -> None:
        if not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        self.config = config
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.creatures: dict[int, Creature] = {}
        self.resources: dict[int, Resource] = {}
        self.lineage = LineageStore()
        self.environment = EnvironmentState()
        self.culture = CultureLedger()
        self.combat_events: list[dict[str, int | float | str]] = []
        self.recent_events: list[dict[str, int | str | None]] = []
        self.death_causes: dict[str, int] = {}
        self.next_creature_id = 0
        self.next_resource_id = 0
        self.spawn_accumulator = 0.0
        self.tick_births = 0
        self.tick_deaths = 0
        self.total_births = 0
        self.total_deaths = 0
        self.reproduction_skipped_at_cap = 0
        self.metrics = MetricsRecorder()
        self.behavior_controller = BehaviorController(config)
        self._behavior_resource_index: SpatialHash | None = None
        self._behavior_creature_index: SpatialHash | None = None
        self._behavior_eligible_ids: set[int] | None = None
        self._tick_perceptions: dict[int, BehaviorPerception] = {}
        self._initialize_world()

    @property
    def extinct(self) -> bool:
        return not self.creatures

    def _initialize_world(self) -> None:
        for _ in range(self.config.initial_population):
            self._create_initial_creature()
        for _ in range(self.config.resources.initial_count):
            self._spawn_resource()

    def _random_position(self) -> np.ndarray:
        return self.rng.uniform(
            [0.0, 0.0],
            [float(self.config.world.width), float(self.config.world.height)],
        )

    def _create_initial_creature(self) -> None:
        creature_id = self.next_creature_id
        self.next_creature_id += 1
        genome = random_genome(self.config.genome, self.rng)
        angle = float(self.rng.uniform(0.0, math.tau))
        speed = genome[Trait.SPEED] * float(self.rng.uniform(0.15, 0.45))
        self.creatures[creature_id] = Creature(
            id=creature_id,
            position=self._random_position(),
            velocity=np.array([math.cos(angle), math.sin(angle)]) * speed,
            age=int(self.rng.integers(0, max(1, self.config.reproduction.minimum_age))),
            energy=self.config.energy.initial,
            genome=genome,
            wander_angle=angle,
            temperament=Temperament.random(self.rng),
            home_radius=min(
                float(self.rng.uniform(18.0, 36.0)),
                min(self.config.world.width, self.config.world.height) / 2.0,
            ),
        )

    def _spawn_resource(self) -> None:
        if len(self.resources) >= self.config.resources.maximum_count:
            return
        resource_id = self.next_resource_id
        self.next_resource_id += 1
        self.resources[resource_id] = Resource(
            resource_id,
            self._random_position(),
            self.config.resources.energy_value,
        )

    def step(self, count: int = 1) -> None:
        if not isinstance(count, int) or count < 0:
            raise ValueError("count must be a non-negative integer")
        for _ in range(count):
            self._step_once()

    def _step_once(self) -> None:
        self.tick_births = 0
        self.tick_deaths = 0
        self.combat_events = []
        self.recent_events = []
        for creature in self.creatures.values():
            creature.fight_wins_tick = 0
        self.environment.update(self.tick)
        self._regenerate_resources()
        resource_index = self._resource_index()
        self._move_creatures(resource_index)
        self._resolve_fights()
        self._resolve_consumption(resource_index)
        self._resolve_reproduction()
        self._resolve_deaths()
        self.tick += 1
        self.culture.update(self)
        self._update_satisfaction()
        if self.tick % self.config.metrics.sample_interval == 0:
            self.metrics.record(self)

    def _regenerate_resources(self) -> None:
        self.spawn_accumulator += (
            self.config.resources.spawn_rate
            * self.environment.food_multiplier
            * self.environment.seasonal_food_multiplier
        )
        spawn_count = int(self.spawn_accumulator)
        self.spawn_accumulator -= spawn_count
        available = self.config.resources.maximum_count - len(self.resources)
        for _ in range(min(spawn_count, max(0, available))):
            self._spawn_resource()

    def _resource_index(self) -> SpatialHash:
        maximum_perception = self.config.genome.traits["perception"].maximum
        cell_size = max(24.0, maximum_perception / 2.0)
        index = SpatialHash(cell_size)
        index.rebuild({key: item.position for key, item in self.resources.items()})
        return index

    def _move_creatures(self, resource_index: SpatialHash) -> None:
        self._behavior_resource_index = resource_index
        self._behavior_creature_index = SpatialHash(
            max(24.0, self.config.genome.traits["perception"].maximum / 2.0)
        )
        self._behavior_creature_index.rebuild(
            {key: item.position for key, item in self.creatures.items()}
        )
        self._tick_perceptions.clear()
        for creature_id in sorted(self.creatures):
            self.creatures[creature_id].age += 1
        self._behavior_eligible_ids = {
            key for key, creature in self.creatures.items() if self._eligible(creature)
        }
        # Every decision sees the same tick's positions; no earlier creature has moved.
        for creature_id in sorted(self.creatures):
            self._choose_behavior(creature_id)
        for creature_id in sorted(self.creatures):
            self._execute_behavior(creature_id)
        self._behavior_resource_index = self._behavior_creature_index = None
        self._behavior_eligible_ids = None
        self._tick_perceptions.clear()

    def _behavior_perception(self, creature_id: int) -> BehaviorPerception:
        creature = self.creatures[creature_id]
        resource_index = self._behavior_resource_index or self._resource_index()
        creature_index = self._behavior_creature_index
        if creature_index is None:
            creature_index = SpatialHash(max(24.0, creature.genome[Trait.PERCEPTION] / 2.0))
            creature_index.rebuild({key: item.position for key, item in self.creatures.items()})
        radius = creature.genome[Trait.PERCEPTION]
        eligible = self._behavior_eligible_ids
        if eligible is None:
            eligible = {key for key, item in self.creatures.items() if self._eligible(item)}
        neighbors = [
            self.creatures[key]
            for key in creature_index.query_radius(creature.position, radius)
            if key != creature_id and self.creatures[key].alive
        ]
        # Reuse the neighborhood when it includes the care radius.
        care_neighbors = (
            neighbors
            if self.config.behavior.care_radius <= radius
            else [
                self.creatures[key]
                for key in creature_index.query_radius(
                    creature.position, self.config.behavior.care_radius
                )
            ]
        )
        dependents = tuple(
            child
            for child in care_neighbors
            if child.alive
            and child.parents is not None
            and creature_id in child.parents
            and child.age < self.config.behavior.dependent_age_ticks
            and distance_sq(creature.position, child.position)
            <= self.config.behavior.care_radius**2
        )
        return BehaviorPerception(
            food=tuple(
                self.resources[key]
                for key in resource_index.query_radius(creature.position, radius)
                if key in self.resources
            ),
            threats=tuple(
                other
                for other in neighbors
                if other.temperament.aggression >= 0.5
                and not (other.parents is not None and creature_id in other.parents)
                and not (creature.parents is not None and other.id in creature.parents)
            ),
            eligible_mates=tuple(
                other
                for other in neighbors
                if creature_id in eligible
                and other.id in eligible
                and not (other.parents is not None and creature_id in other.parents)
                and not (creature.parents is not None and other.id in creature.parents)
            ),
            dependent_offspring=dependents,
            local_hazard=min(1.0, max(0.0, self.environment.health_pressure)),
            terrain_cost=min(1.0, max(0.0, (self.environment.movement_multiplier - 1.0) / 3.0)),
        )

    def _choose_behavior(self, creature_id: int) -> None:
        creature = self.creatures[creature_id]
        perception = self._behavior_perception(creature_id)
        self._tick_perceptions[creature_id] = perception
        decision = self.behavior_controller.decide(
            creature, perception, self.config.energy.maximum, self.tick, self.rng
        )
        creature.behavior_state = decision.state
        outside = distance_sq(creature.position, creature.home_center) > creature.home_radius**2
        if not outside or decision.state.action is not ActionName.FORAGE:
            creature.home_migration_ticks = 0
            return
        # Only locally perceived food supplies evidence of a better outside habitat.
        outside_reward = max(
            (
                self.behavior_controller.food_reward(creature, food, self.config.energy.maximum)
                for food in perception.food
                if distance_sq(food.position, creature.home_center) > creature.home_radius**2
            ),
            default=0.0,
        )
        home_reward = max(
            (
                self.behavior_controller.food_reward(creature, food, self.config.energy.maximum)
                for food in perception.food
                if distance_sq(food.position, creature.home_center) <= creature.home_radius**2
            ),
            default=0.0,
        )
        if (
            outside
            and decision.state.action is ActionName.FORAGE
            and outside_reward - home_reward > self.config.behavior.territory_migration_margin
        ):
            creature.home_migration_ticks += 1
            if creature.home_migration_ticks >= HOME_MIGRATION_PERSISTENCE_TICKS:
                creature.home_center += HOME_MIGRATION_RATE * (
                    creature.position - creature.home_center
                )
        else:
            creature.home_migration_ticks = 0

    def _execute_behavior(self, creature_id: int) -> None:
        creature = self.creatures[creature_id]
        state = creature.behavior_state
        target = None if state.target_position is None else np.asarray(state.target_position)
        if state.target_kind == "creature" and state.target_id in self.creatures:
            target = self.creatures[state.target_id].position
        if state.action is ActionName.REST:
            direction = np.zeros(2)
        elif state.action is ActionName.FLEE:
            if target is not None and state.target_kind == "creature":
                direction = unit_vector(creature.position - target)
            else:
                direction = unit_vector(creature.home_center - creature.position)
            if float(np.linalg.norm(direction)) == 0.0:
                direction = np.array(
                    [math.cos(creature.wander_angle), math.sin(creature.wander_angle)]
                )
        elif target is not None:
            delta = target - creature.position
            if state.action is ActionName.CARE and float(np.linalg.norm(delta)) <= 4.0:
                direction = np.zeros(2)
            else:
                direction = unit_vector(delta)
        else:
            if self.rng.random() < self.config.wander_change_probability:
                creature.wander_angle += float(self.rng.normal(0.0, 0.65))
            direction = np.array([math.cos(creature.wander_angle), math.sin(creature.wander_angle)])
        max_speed = creature.genome[Trait.SPEED]
        speed_factor = {
            ActionName.REST: 0.0,
            ActionName.CARE: 0.4,
            ActionName.PATROL: 0.6,
            ActionName.EXPLORE: 0.65,
        }.get(state.action, 1.0)
        desired_velocity = direction * max_speed * speed_factor
        steering = 0.8 if state.action is ActionName.REST else 0.3
        creature.velocity += steering * (desired_velocity - creature.velocity)
        if float(np.linalg.norm(creature.velocity)) > max_speed:
            creature.velocity = unit_vector(creature.velocity) * max_speed
        distance = float(np.linalg.norm(creature.velocity))
        creature.position += creature.velocity
        if self.config.world.boundary == "collision":
            creature.position, creature.velocity = reflect_bounds(
                creature.position,
                creature.velocity,
                width=float(self.config.world.width),
                height=float(self.config.world.height),
            )
        else:
            creature.position %= np.array([self.config.world.width, self.config.world.height])
        size, metabolism = creature.genome[Trait.SIZE], creature.genome[Trait.METABOLISM]
        basal = (
            self.config.energy.basal_cost
            * (1.0 + size / 8.0)
            / metabolism
            * self.environment.metabolic_multiplier
            * self.environment.seasonal_metabolic_multiplier
            * (1.0 + creature.injury * 0.35)
            * (1.0 + self.environment.health_pressure * 0.25)
        )
        movement = (
            self.config.energy.movement_cost
            * distance
            * (0.5 + size / 8.0)
            * (0.5 + max_speed / 4.0)
            * self.environment.movement_multiplier
        )
        creature.energy -= basal + movement
        if state.action is ActionName.CARE and state.target_id in self.creatures:
            child = self.creatures[state.target_id]
            if (
                child.alive
                and child.parents is not None
                and creature.id in child.parents
                and child.age < self.config.behavior.dependent_age_ticks
                and distance_sq(creature.position, child.position)
                <= self.config.behavior.care_radius**2
            ):
                transfer = min(
                    self.config.behavior.care_energy_rate,
                    max(0.0, creature.energy - CARE_PARENT_RESERVE * self.config.energy.maximum),
                    max(0.0, self.config.energy.maximum - child.energy),
                )
                creature.energy -= transfer
                child.energy += transfer
                child.hunger = min(1.0, max(0.0, 1.0 - child.energy / self.config.energy.maximum))
        if self.environment.health_pressure > 0.0:
            creature.injury = min(
                1.0,
                creature.injury
                + self.environment.health_pressure
                * (1.0 - creature.temperament.resilience)
                * 0.003,
            )
        else:
            recovery = 0.003 if state.action is ActionName.REST else 0.0015
            creature.injury = max(0.0, creature.injury - recovery)
        creature.hunger = min(1.0, max(0.0, 1.0 - creature.energy / self.config.energy.maximum))
        creature.starvation_ticks = (
            creature.starvation_ticks + 1
            if creature.energy <= 0.0
            else max(0, creature.starvation_ticks - 1)
        )
        creature.trail.append((float(creature.position[0]), float(creature.position[1])))
        if len(creature.trail) > 18:
            del creature.trail[:-18]

    def _resolve_fights(self) -> None:
        if len(self.creatures) < 2:
            return
        index = SpatialHash(36.0)
        index.rebuild({key: item.position for key, item in self.creatures.items()})
        engaged: set[int] = set()
        max_energy = self.config.energy.maximum
        for first_id in sorted(self.creatures):
            if first_id in engaged:
                continue
            first = self.creatures[first_id]
            radius = max(16.0, self.config.genome.traits["size"].maximum * 5.0)
            for second_id in index.query_radius(first.position, radius):
                if second_id <= first_id or second_id in engaged:
                    continue
                second = self.creatures[second_id]
                reach = max(10.0, 2.5 * (first.genome[Trait.SIZE] + second.genome[Trait.SIZE]))
                if distance_sq(first.position, second.position) > reach * reach:
                    continue
                pressure = max(first.hunger, second.hunger)
                is_challenge = any(
                    actor.behavior_state.action is ActionName.CHALLENGE
                    and actor.behavior_state.target_id == rival.id
                    for actor, rival in ((first, second), (second, first))
                )
                if pressure < 0.48 and not is_challenge:
                    continue
                aggression = (first.temperament.aggression + second.temperament.aggression) / 2.0
                if aggression <= 0 or any(
                    actor.behavior_state.action is ActionName.FLEE for actor in (first, second)
                ):
                    continue
                risk = min(
                    0.09,
                    0.004 * (0.25 + pressure) * (0.3 + aggression) * (1.5 if is_challenge else 1.0),
                )
                if self.rng.random() >= risk:
                    continue

                first_score = first.genome[Trait.SIZE] * (
                    0.6 + first.temperament.aggression
                ) + 0.45 * max(0.0, first.energy / max_energy)
                second_score = second.genome[Trait.SIZE] * (
                    0.6 + second.temperament.aggression
                ) + 0.45 * max(0.0, second.energy / max_energy)
                first_defense = first.genome[Trait.SIZE] * (0.7 + first.temperament.resilience)
                second_defense = second.genome[Trait.SIZE] * (0.7 + second.temperament.resilience)
                first_win_probability = (first_score + second_defense) / (
                    first_score + second_score + first_defense + second_defense
                )
                winner, loser = (
                    (first, second)
                    if self.rng.random() < first_win_probability
                    else (second, first)
                )
                winner.fights_won += 1
                winner.fight_wins_tick += 1
                winner.alpha = True
                loser.fights_lost += 1
                loser.injury = min(
                    1.0,
                    loser.injury + 0.08 + 0.1 * winner.temperament.aggression,
                )
                winner.energy -= 0.012 * max_energy
                loser.energy -= (0.025 + 0.05 * winner.temperament.aggression) * max_energy
                lethal_risk = min(
                    0.42,
                    0.006
                    + max(0.0, 0.25 - loser.energy / max_energy) * 0.55
                    + max(0.0, loser.injury - 0.65) * 0.35,
                )
                if self.rng.random() < lethal_risk:
                    loser.injury = 1.0
                winner.hunger = min(1.0, max(0.0, 1.0 - winner.energy / max_energy))
                loser.hunger = min(1.0, max(0.0, 1.0 - loser.energy / max_energy))
                engaged.update((first_id, second_id))
                event = {
                    "tick": self.tick,
                    "winner": winner.id,
                    "loser": loser.id,
                    "severity": round(loser.injury, 4),
                    "fatal": loser.injury >= 0.98,
                }
                self.combat_events.append(event)
                self.recent_events.append(
                    {
                        "tick": self.tick,
                        "kind": "fight",
                        "text": f"Creature {winner.id} won a clash with creature {loser.id}.",
                        "creature_id": winner.id,
                    }
                )
                break

    def _resolve_consumption(self, resource_index: SpatialHash) -> None:
        if not self.resources:
            return
        contenders: dict[int, list[tuple[float, int]]] = {}
        maximum_resource_radius = max(resource.radius for resource in self.resources.values())
        for creature_id in sorted(self.creatures):
            creature = self.creatures[creature_id]
            reach = creature.genome[Trait.SIZE] + maximum_resource_radius
            for resource_id in resource_index.query_radius(creature.position, reach):
                resource = self.resources[resource_id]
                exact_reach = creature.genome[Trait.SIZE] + resource.radius
                squared = distance_sq(creature.position, resource.position)
                if squared <= exact_reach * exact_reach:
                    contenders.setdefault(resource_id, []).append((squared, creature_id))
        for resource_id in sorted(contenders):
            winner_id = min(contenders[resource_id])[1]
            resource = self.resources.pop(resource_id, None)
            if resource is None or winner_id not in self.creatures:
                continue
            winner = self.creatures[winner_id]
            winner.food_acquired += resource.energy
            winner.energy = min(self.config.energy.maximum, winner.energy + resource.energy)
            winner.hunger = min(1.0, max(0.0, 1.0 - winner.energy / self.config.energy.maximum))

    def _eligible(self, creature: Creature) -> bool:
        fertility = creature.genome[Trait.FERTILITY]
        cooldown = max(1, round(self.config.reproduction.cooldown * (1.0 - 0.5 * fertility)))
        return (
            creature.alive
            and creature.age >= self.config.reproduction.minimum_age
            and creature.energy >= creature.genome[Trait.REPRODUCTION_THRESHOLD]
            and self.tick - creature.last_reproduction_tick >= cooldown
        )

    def _resolve_reproduction(self) -> None:
        eligible = {
            creature_id
            for creature_id, creature in self.creatures.items()
            if self._eligible(creature) and creature.behavior_state.action is ActionName.SEEK_MATE
        }
        if len(eligible) < 2:
            return
        index = SpatialHash(max(1.0, self.config.reproduction.mate_radius))
        index.rebuild({key: item.position for key, item in self.creatures.items()})
        paired: set[int] = set()
        newborns: list[Creature] = []
        for first_id in sorted(eligible):
            if first_id in paired:
                continue
            first = self.creatures[first_id]
            candidates = [
                candidate
                for candidate in index.query_radius(
                    first.position, self.config.reproduction.mate_radius
                )
                if candidate in eligible
                and candidate != first_id
                and candidate not in paired
                and first.behavior_state.target_id == candidate
                and self.creatures[candidate].behavior_state.target_id == first_id
            ]
            if not candidates:
                continue
            second_id = min(
                candidates,
                key=lambda item: (distance_sq(first.position, self.creatures[item].position), item),
            )
            if len(self.creatures) + len(newborns) >= self.config.reproduction.population_cap:
                self.reproduction_skipped_at_cap += 1
                break
            second = self.creatures[second_id]
            child_genome = crossover(
                first.genome, second.genome, self.config.genome.crossover, self.rng
            )
            child_genome = mutate(child_genome, self.config.genome, self.rng)
            child_id = self.next_creature_id
            self.next_creature_id += 1
            midpoint = (first.position + second.position) / 2.0
            child_position = midpoint + self.rng.normal(0.0, 2.0, 2)
            child_position = np.clip(
                child_position,
                [0.0, 0.0],
                [float(self.config.world.width), float(self.config.world.height)],
            )
            child = Creature(
                id=child_id,
                position=child_position,
                velocity=np.zeros(2),
                age=0,
                energy=self.config.reproduction.offspring_energy,
                genome=child_genome,
                parents=(first_id, second_id),
                birth_tick=self.tick,
                wander_angle=float(self.rng.uniform(0.0, math.tau)),
                temperament=Temperament.inherited(first.temperament, second.temperament, self.rng),
                home_center=child_position,
                home_radius=min(
                    max(
                        0.001,
                        (first.home_radius + second.home_radius)
                        / 2.0
                        * float(self.rng.uniform(0.9, 1.1)),
                    ),
                    min(self.config.world.width, self.config.world.height) / 2.0,
                ),
            )
            contribution = self.config.reproduction.offspring_energy / 2.0
            first.energy -= contribution
            second.energy -= contribution
            first.offspring_count += 1
            second.offspring_count += 1
            first.last_reproduction_tick = self.tick
            second.last_reproduction_tick = self.tick
            paired.update((first_id, second_id))
            newborns.append(child)
            self.lineage.record(child_id, (first_id, second_id), birth_tick=self.tick)
            self.recent_events.append(
                {
                    "tick": self.tick,
                    "kind": "birth",
                    "text": f"A new creature was born to {first_id} and {second_id}.",
                    "creature_id": child_id,
                }
            )
        for child in newborns:
            self.creatures[child.id] = child
        self.tick_births = len(newborns)
        self.total_births += self.tick_births

    def _resolve_deaths(self) -> None:
        dead: list[tuple[int, str]] = []
        for creature_id, creature in self.creatures.items():
            if creature.age > self.config.maximum_age:
                cause = "old age"
            elif creature.injury >= 0.98:
                cause = "fight injuries"
            elif creature.starvation_ticks >= 12:
                cause = "starvation"
            else:
                continue
            dead.append((creature_id, cause))
        for creature_id, cause in dead:
            creature = self.creatures.pop(creature_id)
            creature.alive = False
            creature.death_cause = cause
            self.death_causes[cause] = self.death_causes.get(cause, 0) + 1
            self.recent_events.append(
                {
                    "tick": self.tick,
                    "kind": "death",
                    "text": f"Creature {creature_id} died from {cause}.",
                    "creature_id": creature_id,
                }
            )
        self.tick_deaths = len(dead)
        self.total_deaths += self.tick_deaths

    def _update_satisfaction(self) -> None:
        food_scale = max(1.0, self.config.resources.energy_value * 8.0)
        for creature in self.creatures.values():
            energy = min(1.0, max(0.0, creature.energy / self.config.energy.maximum))
            offspring = 1.0 - math.exp(-creature.offspring_count / 3.0)
            food = 1.0 - math.exp(-creature.food_acquired / food_scale)
            fights = 1.0 - math.exp(-creature.fights_won / 2.0)
            creature.satisfaction_vector = (energy, offspring, food, fights)
            creature.satisfaction = min(
                1.0,
                max(0.0, 0.34 * energy + 0.18 * offspring + 0.22 * food + 0.26 * fights),
            )

    def snapshot(self) -> WorldSnapshot:
        dependent_ids: dict[int, list[int]] = {}
        for child in self.creatures.values():
            if (
                child.alive
                and child.parents is not None
                and child.age < self.config.behavior.dependent_age_ticks
            ):
                for parent_id in child.parents:
                    dependent_ids.setdefault(parent_id, []).append(child.id)
        creatures = tuple(
            CreatureSnapshot(
                id=item.id,
                position=(float(item.position[0]), float(item.position[1])),
                velocity=(float(item.velocity[0]), float(item.velocity[1])),
                age=item.age,
                energy=float(item.energy),
                genome=item.genome.values,
                parents=item.parents,
                offspring_count=item.offspring_count,
                food_acquired=float(item.food_acquired),
                birth_tick=item.birth_tick,
                hunger=item.hunger,
                satisfaction_vector=item.satisfaction_vector,
                satisfaction=item.satisfaction,
                fights_won=item.fights_won,
                fights_lost=item.fights_lost,
                alpha=item.alpha,
                injury=item.injury,
                temperament=item.temperament.as_tuple(),
                belief_id=item.belief_id,
                behavior=item.behavior_state.action.value,
                behavior_reason=item.behavior_state.reason,
                behavior_started_tick=item.behavior_state.started_tick,
                drives=item.behavior_state.drives.values,
                behavior_scores=tuple(
                    (action.value, float(score))
                    for action, score in item.behavior_state.utility_breakdown.items()
                ),
                target_kind=item.behavior_state.target_kind,
                target_id=item.behavior_state.target_id,
                target_position=item.behavior_state.target_position,
                home_center=tuple(float(value) for value in item.home_center),
                home_radius=item.home_radius,
                dependent_ids=tuple(sorted(dependent_ids.get(item.id, ()))),
            )
            for item in (self.creatures[key] for key in sorted(self.creatures))
        )
        resources = tuple(
            ResourceSnapshot(
                id=item.id,
                position=(float(item.position[0]), float(item.position[1])),
                energy=float(item.energy),
            )
            for item in (self.resources[key] for key in sorted(self.resources))
        )
        return WorldSnapshot(
            tick=self.tick,
            seed=self.seed,
            creatures=creatures,
            resources=resources,
            births=self.tick_births,
            deaths=self.tick_deaths,
            total_births=self.total_births,
            total_deaths=self.total_deaths,
            food_multiplier=self.environment.food_multiplier,
            metabolic_multiplier=self.environment.metabolic_multiplier,
            extinct=self.extinct,
            active_fights=tuple(self.combat_events),
        )

    def audit_invariants(self) -> list[str]:
        errors: list[str] = []
        width = self.config.world.width
        height = self.config.world.height
        for key, creature in self.creatures.items():
            if key != creature.id:
                errors.append(f"creature key/id mismatch: {key}/{creature.id}")
            if not np.isfinite(creature.position).all() or not np.isfinite(creature.velocity).all():
                errors.append(f"creature {key} has non-finite motion state")
            if not math.isfinite(creature.energy):
                errors.append(f"creature {key} has non-finite energy")
            if not np.isfinite(creature.home_center).all() or not (
                0 <= creature.home_center[0] <= width and 0 <= creature.home_center[1] <= height
            ):
                errors.append(f"creature {key} has invalid home center")
            if not (0 < creature.home_radius <= min(width, height) / 2.0):
                errors.append(f"creature {key} has invalid home radius")
            if creature.home_migration_ticks < 0:
                errors.append(f"creature {key} has invalid migration counter")
            if not (0 <= creature.position[0] <= width and 0 <= creature.position[1] <= height):
                errors.append(f"creature {key} is outside world bounds")
            for trait, value in creature.genome.to_mapping().items():
                bounds = self.config.genome.traits[trait]
                if not bounds.minimum <= value <= bounds.maximum:
                    errors.append(f"creature {key} has out-of-bounds {trait}")
        for key, resource in self.resources.items():
            if key != resource.id:
                errors.append(f"resource key/id mismatch: {key}/{resource.id}")
            if not np.isfinite(resource.position).all() or not math.isfinite(resource.energy):
                errors.append(f"resource {key} has non-finite state")
        errors.extend(self.lineage.validate())
        return errors
