"""Small-scale cultural transmission and the gradual emergence of shared rituals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evolution_sim.model.spatial import SpatialHash

RITUALS = {
    "season-turn": ("The Turning", "mark the changing season"),
    "drought": ("Keepers of the Deep", "remember the returning water"),
    "heat": ("The Shade Circle", "gather beneath shelter at noon"),
    "storm": ("Voices Before Rain", "call together before the storm"),
    "victory": ("The First Hunt", "honor a victorious elder"),
}


@dataclass(slots=True)
class Tradition:
    id: int
    signal: str
    name: str
    ritual: str
    founder_id: int
    founded_tick: int
    followers: set[int] = field(default_factory=set)
    ritual_count: int = 0
    last_ritual_tick: int = -1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "signal": self.signal,
            "name": self.name,
            "ritual": self.ritual,
            "founder_id": self.founder_id,
            "founded_tick": self.founded_tick,
            "followers": sorted(self.followers),
            "ritual_count": self.ritual_count,
            "last_ritual_tick": self.last_ritual_tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tradition:
        return cls(
            id=int(data["id"]),
            signal=str(data["signal"]),
            name=str(data["name"]),
            ritual=str(data["ritual"]),
            founder_id=int(data["founder_id"]),
            founded_tick=int(data["founded_tick"]),
            followers={int(value) for value in data.get("followers", [])},
            ritual_count=int(data.get("ritual_count", 0)),
            last_ritual_tick=int(data.get("last_ritual_tick", -1)),
        )


class CultureLedger:
    """Beliefs form from repeated shared observations, then spread through contact."""

    def __init__(self) -> None:
        self.traditions: list[Tradition] = []
        self.observations: dict[int, dict[str, int]] = {}
        self.signal_count: dict[str, int] = {}
        self.last_signal_tick: dict[str, int] = {}
        self.next_id = 1
        self.chronicle: list[dict[str, Any]] = []

    def update(self, engine: Any) -> None:
        tick = engine.tick
        creatures = engine.creatures
        if not creatures:
            return

        signals: set[str] = set()
        if tick > 0 and tick % 96 == 0:
            signals.add("season-turn")
        for event in engine.environment.active_events:
            if event.kind in {"drought", "heat", "storm"}:
                signals.add(event.kind)
        if any(creature.fight_wins_tick for creature in creatures.values()):
            signals.add("victory")

        for signal in sorted(signals):
            if tick - self.last_signal_tick.get(signal, -10_000) > 8:
                self.signal_count[signal] = self.signal_count.get(signal, 0) + 1
                self.last_signal_tick[signal] = tick
            for creature_id in sorted(creatures):
                exposure = self.observations.setdefault(creature_id, {})
                exposure[signal] = exposure.get(signal, 0) + 1

        active_signals = {tradition.signal for tradition in self.traditions}
        candidates = [
            signal
            for signal, count in self.signal_count.items()
            if count >= 3 and signal not in active_signals
        ]
        if len(creatures) >= 5 and candidates and engine.rng.random() < 0.012:
            signal = min(candidates, key=lambda item: (-self.signal_count[item], item))
            eligible = [
                creature
                for creature in creatures.values()
                if self.observations.get(creature.id, {}).get(signal, 0) >= 3
            ]
            if len(eligible) >= 5:
                founder = max(
                    eligible,
                    key=lambda creature: (
                        creature.temperament.sociability + 0.15 * creature.fights_won,
                        -creature.id,
                    ),
                )
                name, ritual = RITUALS[signal]
                tradition = Tradition(
                    id=self.next_id,
                    signal=signal,
                    name=name,
                    ritual=ritual,
                    founder_id=founder.id,
                    founded_tick=tick,
                    followers={creature.id for creature in eligible},
                )
                self.next_id += 1
                self.traditions.append(tradition)
                for creature in eligible:
                    creature.belief_id = tradition.id
                self._record(
                    tick,
                    "belief-founded",
                    f"{tradition.name} formed after repeated shared observations.",
                    tradition.id,
                )

        self._spread(engine)
        self._rituals(engine)
        alive_ids = set(creatures)
        for tradition in self.traditions:
            tradition.followers.intersection_update(alive_ids)

    def _spread(self, engine: Any) -> None:
        index = SpatialHash(60.0)
        index.rebuild({key: item.position for key, item in engine.creatures.items()})
        for tradition in self.traditions:
            believers = sorted(
                item for item in tradition.followers if item in engine.creatures
            )
            for believer_id in believers:
                believer = engine.creatures[believer_id]
                for candidate_id in index.query_radius(believer.position, 60.0):
                    candidate = engine.creatures[candidate_id]
                    if candidate.belief_id is not None:
                        continue
                    if engine.rng.random() < 0.003 + 0.018 * candidate.temperament.sociability:
                        candidate.belief_id = tradition.id
                        tradition.followers.add(candidate_id)

    def _rituals(self, engine: Any) -> None:
        for tradition in self.traditions:
            if engine.tick <= tradition.founded_tick or engine.tick % 48:
                continue
            present = [
                engine.creatures[item]
                for item in sorted(tradition.followers)
                if item in engine.creatures
            ]
            if len(present) < 3:
                continue
            tradition.ritual_count += 1
            tradition.last_ritual_tick = engine.tick
            for creature in present:
                creature.ritual_ticks += 1
            self._record(
                engine.tick,
                "ritual",
                f"{tradition.name}: {tradition.ritual} ({len(present)} present).",
                tradition.id,
            )

    def _record(self, tick: int, kind: str, text: str, tradition_id: int | None) -> None:
        self.chronicle.append(
            {"tick": tick, "kind": kind, "text": text, "tradition_id": tradition_id}
        )
        if len(self.chronicle) > 200:
            del self.chronicle[:-200]

    def to_dict(self) -> dict[str, Any]:
        return {
            "traditions": [item.to_dict() for item in self.traditions],
            "observations": {
                str(key): dict(value) for key, value in sorted(self.observations.items())
            },
            "signal_count": dict(self.signal_count),
            "last_signal_tick": dict(self.last_signal_tick),
            "next_id": self.next_id,
            "chronicle": list(self.chronicle),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CultureLedger:
        ledger = cls()
        if not data:
            return ledger
        ledger.traditions = [Tradition.from_dict(item) for item in data.get("traditions", [])]
        ledger.observations = {
            int(key): {str(signal): int(count) for signal, count in value.items()}
            for key, value in data.get("observations", {}).items()
        }
        ledger.signal_count = {
            str(key): int(value) for key, value in data.get("signal_count", {}).items()
        }
        ledger.last_signal_tick = {
            str(key): int(value) for key, value in data.get("last_signal_tick", {}).items()
        }
        ledger.next_id = int(data.get("next_id", 1))
        ledger.chronicle = [dict(item) for item in data.get("chronicle", [])]
        return ledger
