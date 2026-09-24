from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Iterator

from .numeric import sum_weight_units, units_to_weight, weight_units


class UnionFind:
    def __init__(self, items: Iterable[str] = ()) -> None:
        self.parent: dict[str, str] = {item: item for item in items}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            next_item = self.parent[item]
            self.parent[item] = root
            item = next_item
        return root

    def union(self, left: str, right: str) -> None:
        root_left, root_right = self.find(left), self.find(right)
        if root_left == root_right:
            return
        keep, drop = sorted((root_left, root_right))
        self.parent[drop] = keep

    def groups(self) -> dict[str, set[str]]:
        groups: dict[str, set[str]] = {}
        for item in self.parent:
            groups.setdefault(self.find(item), set()).add(item)
        return groups


@dataclass(frozen=True)
class AliasSummary:
    collapsed_scores: dict[str, float]
    collapsed_units: dict[str, int]
    component_members: dict[str, tuple[str, ...]]
    unresolved_components: tuple[tuple[str, ...], ...]
    score_intervals: dict[str, tuple[float, float]]
    score_interval_units: dict[str, tuple[int, int]]
    certified_pairs: tuple[tuple[str, str, str], ...]
    abstained_pairs: tuple[tuple[str, str, str], ...]


def collapse_must_link_term_units(
    score_terms: dict[str, Iterable[object]],
    must_link: Iterable[tuple[str, str]],
) -> tuple[dict[str, int], dict[str, str], dict[str, tuple[str, ...]]]:
    """Collapse aliases and sum exact integer event units."""
    uf = UnionFind(score_terms)
    for left, right in must_link:
        uf.union(left, right)
    alias_to_root = {alias: uf.find(alias) for alias in uf.parent}
    grouped: dict[str, list[object]] = {}
    for alias, values in score_terms.items():
        grouped.setdefault(alias_to_root[alias], []).extend(values)
    collapsed_units = {
        root: sum_weight_units(values) for root, values in grouped.items()
    }
    members = {root: tuple(sorted(group)) for root, group in uf.groups().items()}
    return collapsed_units, alias_to_root, members


def collapse_must_link_terms(
    score_terms: dict[str, Iterable[object]],
    must_link: Iterable[tuple[str, str]],
) -> tuple[dict[str, float], dict[str, str], dict[str, tuple[str, ...]]]:
    """Collapse aliases before summing, avoiding intermediate numeric rounding."""
    collapsed_units, alias_to_root, members = collapse_must_link_term_units(
        score_terms, must_link
    )
    collapsed = {root: units_to_weight(units) for root, units in collapsed_units.items()}
    return collapsed, alias_to_root, members


def collapse_must_links(
    scores: dict[str, float], must_link: Iterable[tuple[str, str]]
) -> tuple[dict[str, float], dict[str, str], dict[str, tuple[str, ...]]]:
    return collapse_must_link_terms(
        {alias: (value,) for alias, value in scores.items()}, must_link
    )


def summarize_alias_terms(
    score_terms: dict[str, Iterable[object]],
    must_link: Iterable[tuple[str, str]],
    may_link: Iterable[tuple[str, str]],
) -> AliasSummary:
    collapsed_units, alias_to_root, must_members = collapse_must_link_term_units(
        score_terms, must_link
    )
    collapsed = {
        root: units_to_weight(units) for root, units in collapsed_units.items()
    }
    component_uf = UnionFind(collapsed_units)
    for left, right in may_link:
        left_root = alias_to_root.get(left, left)
        right_root = alias_to_root.get(right, right)
        component_uf.union(left_root, right_root)

    components = component_uf.groups()
    component_members: dict[str, tuple[str, ...]] = {}
    unresolved_components: list[tuple[str, ...]] = []
    interval_units: dict[str, tuple[int, int]] = {}
    intervals: dict[str, tuple[float, float]] = {}
    scored_roots = set(collapsed_units)
    for component_root, roots in components.items():
        aliases = tuple(
            sorted(alias for root in roots for alias in must_members.get(root, (root,)))
        )
        component_members[component_root] = aliases
        active_roots = tuple(sorted(roots & scored_roots))
        if len(active_roots) > 1:
            unresolved_components.append(active_roots)
        total_units = sum(collapsed_units.get(root, 0) for root in roots)
        for root in roots:
            lower_units = collapsed_units.get(root, 0)
            interval_units[root] = (lower_units, total_units)
            intervals[root] = (
                units_to_weight(lower_units),
                units_to_weight(total_units),
            )

    certified: list[tuple[str, str, str]] = []
    abstained: list[tuple[str, str, str]] = []
    roots = sorted(collapsed_units)
    for left, right in combinations(roots, 2):
        if component_uf.find(left) == component_uf.find(right):
            abstained.append((left, right, "aliases may denote one actor"))
            continue
        left_interval, right_interval = interval_units[left], interval_units[right]
        if left_interval[0] > right_interval[1]:
            certified.append((left, right, ">"))
        elif right_interval[0] > left_interval[1]:
            certified.append((left, right, "<"))
        elif left_interval[0] == left_interval[1] == right_interval[0] == right_interval[1]:
            certified.append((left, right, "="))
        else:
            abstained.append((left, right, "score intervals overlap"))

    return AliasSummary(
        collapsed_scores=dict(sorted(collapsed.items())),
        collapsed_units=dict(sorted(collapsed_units.items())),
        component_members=dict(sorted(component_members.items())),
        unresolved_components=tuple(sorted(unresolved_components)),
        score_intervals=dict(sorted(intervals.items())),
        score_interval_units=dict(sorted(interval_units.items())),
        certified_pairs=tuple(certified),
        abstained_pairs=tuple(abstained),
    )


def summarize_alias_uncertainty(
    scores: dict[str, float],
    must_link: Iterable[tuple[str, str]],
    may_link: Iterable[tuple[str, str]],
) -> AliasSummary:
    return summarize_alias_terms(
        {alias: (value,) for alias, value in scores.items()}, must_link, may_link
    )


def set_partitions(items: tuple[str, ...]) -> Iterator[tuple[tuple[str, ...], ...]]:
    """Generate each set partition exactly once in canonical order."""
    if not items:
        yield tuple()
        return
    first, rest = items[0], items[1:]
    for partition in set_partitions(rest):
        yield ((first,),) + partition
        for index in range(len(partition)):
            merged = tuple(sorted((first,) + partition[index]))
            candidate = list(partition)
            candidate[index] = merged
            candidate.sort(key=lambda block: (block[0], len(block), block))
            yield tuple(candidate)


def exact_rank_interval_units(
    score_units: dict[str, int],
    component: Iterable[str],
    target: str,
    *,
    maximum_component_size: int = 7,
) -> tuple[int, int, int]:
    """Return an exact competition-rank interval on canonical integer units.

    The component is treated as a complete may-link component: every set
    partition is an admissible identity resolution.  A target's competition
    rank is one plus the number of strictly larger resolved actor blocks.  The
    routine is exact only through ``maximum_component_size`` and refuses a
    larger component rather than sampling or truncating it.
    """
    aliases = tuple(sorted(component))
    if isinstance(maximum_component_size, bool) or not isinstance(maximum_component_size, int):
        raise ValueError("maximum_component_size must be an integer")
    if maximum_component_size < 1:
        raise ValueError("maximum_component_size must be positive")
    if len(aliases) > maximum_component_size:
        raise ValueError(
            f"component has {len(aliases)} aliases; exact cap is {maximum_component_size}"
        )
    if len(set(aliases)) != len(aliases):
        raise ValueError("component contains duplicate aliases")
    if target not in aliases:
        raise ValueError(f"target {target!r} not in component")
    for alias, units in score_units.items():
        if not isinstance(alias, str) or not alias.strip():
            raise ValueError("score labels must be nonblank strings")
        if isinstance(units, bool) or not isinstance(units, int):
            raise ValueError(f"score for {alias!r} must use integer units")
        if units < 0:
            raise ValueError(f"score for {alias!r} must be non-negative")

    outside = {alias: value for alias, value in score_units.items() if alias not in aliases}
    best: int | None = None
    worst: int | None = None
    count = 0
    for partition in set_partitions(aliases):
        count += 1
        block_scores: dict[tuple[str, ...], int] = {
            block: sum(score_units.get(alias, 0) for alias in block) for block in partition
        }
        target_block = next(block for block in partition if target in block)
        target_score = block_scores[target_block]
        competitors = list(outside.values()) + [
            value for block, value in block_scores.items() if block != target_block
        ]
        rank = 1 + sum(value > target_score for value in competitors)
        best = rank if best is None else min(best, rank)
        worst = rank if worst is None else max(worst, rank)
    if best is None or worst is None:
        raise AssertionError("nonempty alias component produced no partition")
    return best, worst, count


def exact_rank_interval(
    scores: dict[str, float],
    component: Iterable[str],
    target: str,
    *,
    maximum_component_size: int = 7,
) -> tuple[int, int, int]:
    """Float-facing wrapper for :func:`exact_rank_interval_units`."""
    return exact_rank_interval_units(
        {alias: weight_units(value) for alias, value in scores.items()},
        component,
        target,
        maximum_component_size=maximum_component_size,
    )
