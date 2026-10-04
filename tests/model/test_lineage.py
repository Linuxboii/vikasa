from __future__ import annotations

import pytest

from evolution_sim.model.lineage import LineageStore


def populated_lineage() -> LineageStore:
    lineage = LineageStore()
    lineage.record(3, (1, 2), birth_tick=10)
    lineage.record(4, (2, 3), birth_tick=20)
    lineage.record(5, (3, 4), birth_tick=30)
    return lineage


def test_lineage_records_both_directions_in_stable_order() -> None:
    lineage = populated_lineage()

    assert lineage.parents_of(3) == (1, 2)
    assert lineage.children_of(2) == (3, 4)
    assert lineage.children_of(99) == ()
    assert lineage.validate() == []


def test_ancestor_and_descendant_queries_are_cycle_safe() -> None:
    lineage = populated_lineage()

    assert lineage.ancestors(5, max_depth=2) == {1, 2, 3, 4}
    assert lineage.descendants(1) == {3, 4, 5}


def test_duplicate_child_or_self_parent_is_rejected() -> None:
    lineage = populated_lineage()

    with pytest.raises(ValueError, match="already"):
        lineage.record(3, (1, 2), birth_tick=99)
    with pytest.raises(ValueError, match="own parent"):
        lineage.record(8, (7, 8), birth_tick=99)


def test_records_round_trip_without_losing_ticks() -> None:
    source = populated_lineage()
    restored = LineageStore.from_records(source.to_records())

    assert restored.to_records() == source.to_records()
    assert restored.birth_tick(5) == 30
