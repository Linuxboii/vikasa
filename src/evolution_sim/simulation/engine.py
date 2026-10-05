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
from evolution_sim.simulation.culture import CultureLedger
from evolution_sim.simulation.environment import EnvironmentState
from evolution_sim.simulation.snapshots import (
    CreatureSnapshot,
    ResourceSnapshot,
    WorldSnapshot,
)


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
        creature_index = SpatialHash(
            max(24.0, self.config.genome.traits["perception"].maximum / 2.0)
        )
        creature_index.rebuild({key: item.position for key, item in self.creatures.items()})
        for creature_id in sorted(self.creatures):
            creature = self.creatures[creature_id]
            creature.age += 1
            perception = creature.genome[Trait.PERCEPTION]
            nearby = resource_index.query_radius(creature.position, perception)
            social_targets: list[int] = []
            if creature.alpha and creature.satisfaction >= 0.35:
                social_targets = [
                    other_id
                    for other_id in creature_index.query_radius(creature.position, perception)
                    if other_id != creature_id
                ]
            seeking_trouble = bool(social_targets) and self.rng.random() < min(
                0.45,
                0.04 + 0.32 * creature.satisfaction * creature.temperament.aggression,
            )
            if seeking_trouble:
                target_id = min(
                    social_targets,
                    key=lambda item: (distance_sq(creature.position, self.creatures[item].position), item),
                )
                direction = unit_vector(self.creatures[target_id].position - creature.position)
            elif nearby:
                target_id = min(
                    nearby,
                    key=lambda item: (
                        distance_sq(creature.position, self.resources[item].position),
                        item,
                    ),
                )
                direction = unit_vector(self.resources[target_id].position - creature.position)
            else:
                if self.rng.random() < self.config.wander_change_probability:
                    creature.wander_angle += float(self.rng.normal(0.0, 0.65))
                direction = np.array(
                    [math.cos(creature.wander_angle), math.sin(creature.wander_angle)]
                )
            max_speed = creature.genome[Trait.SPEED]
            desired_velocity = direction * max_speed
            creature.velocity += 0.3 * (desired_velocity - creature.velocity)
            velocity_length = float(np.linalg.norm(creature.velocity))
            if velocity_length > max_speed:
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
                creature.position %= np.array(
                    [float(self.config.world.width), float(self.config.world.height)]
                )
            size = creature.genome[Trait.SIZE]
            metabolism = creature.genome[Trait.METABOLISM]
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
            if self.environment.health_pressure > 0.0:
                creature.injury = min(
                    1.0,
                    creature.injury
                    + self.environment.health_pressure
                    * (1.0 - creature.temperament.resilience)
                    * 0.003,
                )
            else:
                creature.injury = max(0.0, creature.injury - 0.0015)
            creature.hunger = min(
                1.0, max(0.0, 1.0 - creature.energy / self.config.energy.maximum)
            )
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
                is_challenge = first.alpha or second.alpha
                if pressure < 0.48 and not is_challenge:
                    continue
                aggression = (first.temperament.aggression + second.temperament.aggression) / 2.0
                alpha_drive = 1.0 + 0.5 * int(first.alpha) + 0.5 * int(second.alpha)
                risk = min(0.09, 0.004 * (0.25 + pressure) * (0.3 + aggression) * alpha_drive)
                if self.rng.random() >= risk:
                    continue

                first_score = (
                    first.genome[Trait.SIZE] * (0.6 + first.temperament.aggression)
                    + 0.45 * max(0.0, first.energy / max_energy)
                )
                second_score = (
                    second.genome[Trait.SIZE] * (0.6 + second.temperament.aggression)
                    + 0.45 * max(0.0, second.energy / max_energy)
                )
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
            winner.hunger = min(
                1.0, max(0.0, 1.0 - winner.energy / self.config.energy.maximum)
            )

    def _eligible(self, creature: Creature) -> bool:
        fertility = creature.genome[Trait.FERTILITY]
        cooldown = max(1, round(self.config.reproduction.cooldown * (1.0 - 0.5 * fertility)))
        return (
            creature.age >= self.config.reproduction.minimum_age
            and creature.energy >= creature.genome[Trait.REPRODUCTION_THRESHOLD]
            and self.tick - creature.last_reproduction_tick >= cooldown
        )

    def _resolve_reproduction(self) -> None:
        eligible = {
            creature_id
            for creature_id, creature in self.creatures.items()
            if self._eligible(creature)
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
                if candidate in eligible and candidate != first_id and candidate not in paired
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
