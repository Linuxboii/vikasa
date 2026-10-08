"""Bidirectional ancestry records independent of creature lifetime."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Any


class LineageStore:
    def __init__(self) -> None:
        self._parents: dict[int, tuple[int, int]] = {}
        self._children: dict[int, set[int]] = defaultdict(set)
        self._birth_ticks: dict[int, int] = {}
        self._generations: dict[int, int] = {}

    def record(self, child: int, parents: tuple[int, int], *, birth_tick: int) -> None:
        if child in self._parents:
            raise ValueError(f"Child {child} already has lineage data")
        if child in parents:
            raise ValueError(f"Creature {child} cannot be its own parent")
        invalid_id = child < 0 or len(parents) != 2 or any(parent < 0 for parent in parents)
        if invalid_id or birth_tick < 0:
            raise ValueError("Lineage IDs and birth tick must be non-negative")
        self._parents[child] = tuple(parents)
        self._birth_ticks[child] = birth_tick
        for affected in {child, *self.descendants(child)}:
            self._generations.pop(affected, None)
        for parent in parents:
            self._children[parent].add(child)

    def generation_of(self, creature_id: int) -> int:
        """Maximum ancestral depth; founders are generation zero, not age cohorts."""
        pending = [(creature_id, False)]
        visiting: set[int] = set()
        while pending:
            current, expanded = pending.pop()
            if current in self._generations:
                continue
            parents = self._parents.get(current)
            if parents is None:
                self._generations[current] = 0
            elif expanded:
                self._generations[current] = 1 + max(self._generations[p] for p in parents)
                visiting.remove(current)
            else:
                if current in visiting:
                    raise ValueError("Cyclic lineage cannot have a generation depth")
                visiting.add(current)
                pending.append((current, True))
                pending.extend((parent, False) for parent in parents)
        return self._generations[creature_id]

    def parents_of(self, creature_id: int) -> tuple[int, int] | None:
        return self._parents.get(creature_id)

    def children_of(self, creature_id: int) -> tuple[int, ...]:
        return tuple(sorted(self._children.get(creature_id, ())))

    def birth_tick(self, creature_id: int) -> int | None:
        return self._birth_ticks.get(creature_id)

    def ancestors(self, creature_id: int, max_depth: int | None = None) -> set[int]:
        return self._walk((creature_id,), self.parents_of, max_depth)

    def descendants(self, creature_id: int, max_depth: int | None = None) -> set[int]:
        return self._walk((creature_id,), self.children_of, max_depth)

    @staticmethod
    def _walk(
        roots: Iterable[int],
        neighbors: Any,
        max_depth: int | None,
    ) -> set[int]:
        found: set[int] = set()
        queue = deque((root, 0) for root in roots)
        while queue:
            current, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            adjacent = neighbors(current) or ()
            for item in adjacent:
                if item not in found:
                    found.add(item)
                    queue.append((item, depth + 1))
        return found

    def validate(self) -> list[str]:
        errors: list[str] = []
        for child, parents in self._parents.items():
            for parent in parents:
                if child not in self._children.get(parent, set()):
                    errors.append(f"missing reverse edge {parent}->{child}")
        for parent, children in self._children.items():
            for child in children:
                if parent not in (self._parents.get(child) or ()):
                    errors.append(f"orphan reverse edge {parent}->{child}")
        return errors

    def to_records(self) -> list[dict[str, int]]:
        return [
            {
                "child": child,
                "parent_a": parents[0],
                "parent_b": parents[1],
                "birth_tick": self._birth_ticks[child],
            }
            for child, parents in sorted(self._parents.items())
        ]

    @classmethod
    def from_records(cls, records: Iterable[dict[str, int]]) -> LineageStore:
        store = cls()
        for record in records:
            store.record(
                int(record["child"]),
                (int(record["parent_a"]), int(record["parent_b"])),
                birth_tick=int(record["birth_tick"]),
            )
        return store
