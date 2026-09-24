"""Exact competition-rank bounds with all may-link components unresolved.

Inputs are nonnegative canonical integer-unit masses of must-link roots. Every
partition within a component is allowed; no block can cross components. This
is not identity inference. The component cap bounds exponential subset search.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence

Partition = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class GlobalRankInterval:
    best_rank: int
    worst_rank: int
    best_partition: Partition
    worst_partition: Partition
    subset_transitions: int


def _canonical(blocks: Sequence[Sequence[str]]) -> Partition:
    return tuple(sorted(tuple(sorted(block)) for block in blocks))


@lru_cache(maxsize=None)
def _max_above_pattern(
    masses: tuple[int, ...], threshold: int
) -> tuple[int, tuple[tuple[int, ...], ...], int]:
    """Solve one ordered mass pattern by a least-member subset recurrence.

    The finite-oracle generators revisit the same small mass patterns under many
    label spellings and component layouts.  Caching only the ordered integer
    masses and threshold preserves the exact recurrence and tie-breaking while
    avoiding repeated exponential work.  Returned blocks use local indices, so
    the cache contains no repository or identity labels.
    """
    n = len(masses)
    if not n:
        return 0, (), 0
    size = 1 << n
    subset_mass = [0] * size
    best = [0] * size
    choice = [0] * size
    states = 0
    for mask in range(1, size):
        bit = mask & -mask
        subset_mass[mask] = subset_mass[mask ^ bit] + masses[bit.bit_length() - 1]
        # Every partition has exactly one block containing its least member.
        # All complementary masks are numerically smaller and already solved.
        subset = mask
        optimum = -1
        chosen = 0
        while subset:
            if subset & bit:
                states += 1
                score = int(subset_mass[subset] > threshold) + best[mask ^ subset]
                if score > optimum or (score == optimum and subset < chosen):
                    optimum, chosen = score, subset
            subset = (subset - 1) & mask
        best[mask], choice[mask] = optimum, chosen
    blocks: list[tuple[int, ...]] = []
    remaining = size - 1
    while remaining:
        block = choice[remaining]
        blocks.append(tuple(i for i in range(n) if block & (1 << i)))
        remaining ^= block
    return best[-1], tuple(sorted(blocks)), states


def _max_above(
    weights: Mapping[str, int], members: tuple[str, ...], threshold: int
) -> tuple[int, Partition, int]:
    """Optimize a whole partition and map a cached mass pattern to labels."""
    masses = tuple(weights[label] for label in members)
    optimum, index_blocks, states = _max_above_pattern(masses, threshold)
    blocks = tuple(tuple(members[index] for index in block) for block in index_blocks)
    return optimum, _canonical(blocks), states


def _validated_groups(
    score_units: Mapping[str, int],
    components: Sequence[Sequence[str]],
    maximum_component_size: int,
) -> tuple[tuple[str, ...], ...]:
    if (isinstance(maximum_component_size, bool)
            or not isinstance(maximum_component_size, int)
            or not 1 <= maximum_component_size <= 7):
        raise ValueError("component limit must be an integer from one through seven")
    if not score_units or any(not isinstance(k, str) or not k.strip() for k in score_units):
        raise ValueError("score roots must be nonblank labels")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0
           for v in score_units.values()):
        raise ValueError("scores must be nonnegative integer units")
    groups = []
    seen: set[str] = set()
    for raw in components:
        if isinstance(raw, (str, bytes)):
            raise ValueError("each component must be a sequence of labels")
        group = tuple(raw)
        if not group or len(group) > maximum_component_size:
            raise ValueError("component is empty or exceeds the exact-search cap")
        for label in group:
            if not isinstance(label, str) or label not in score_units or label in seen:
                raise ValueError("components must partition the score roots")
            seen.add(label)
        groups.append(tuple(sorted(group)))
    if seen != set(score_units):
        raise ValueError("components must cover every score root")
    groups.sort()
    return tuple(groups)


def _exact_for_target(
    score_units: Mapping[str, int],
    groups: tuple[tuple[str, ...], ...],
    target: str,
    cache: dict[tuple[tuple[str, ...], int], tuple[int, Partition, int]] | None = None,
) -> GlobalRankInterval:
    if not isinstance(target, str) or target not in score_units:
        raise ValueError("target is absent")
    target_group = next(g for g in groups if target in g)
    maximum_target = sum(score_units[label] for label in target_group)
    minimum_target = score_units[target]
    best_rank = worst_rank = 1
    best_blocks: list[tuple[str, ...]] = [target_group]
    worst_blocks: list[tuple[str, ...]] = [(target,)]
    examined = 0
    for group in groups:
        if group != target_group:
            if max(score_units[label] for label in group) > maximum_target:
                best_rank += 1
                best_blocks.append(group)
            else:
                best_blocks.extend((label,) for label in group)
        remainder = tuple(label for label in group if label != target)
        key = (remainder, minimum_target)
        if cache is not None and key in cache:
            above, blocks, states = cache[key]
        else:
            above, blocks, states = _max_above(score_units, remainder, minimum_target)
            if cache is not None:
                cache[key] = (above, blocks, states)
        worst_rank += above
        worst_blocks.extend(blocks)
        examined += states
    return GlobalRankInterval(best_rank, worst_rank, _canonical(best_blocks),
                              _canonical(worst_blocks), examined)


def exact_global_rank_interval_units(
    score_units: Mapping[str, int],
    components: Sequence[Sequence[str]],
    target: str,
    *,
    maximum_component_size: int = 7,
) -> GlobalRankInterval:
    """Return exact extrema and attaining partitions, or refuse invalid scope.

    ``components`` must partition every supplied must-link root exactly once,
    including singleton components. Labels and masses are checked before any
    exponential work. Booleans are not integer-unit values or size limits.
    """
    groups = _validated_groups(score_units, components, maximum_component_size)
    return _exact_for_target(score_units, groups, target)


def exact_global_rank_intervals_units(
    score_units: Mapping[str, int],
    components: Sequence[Sequence[str]],
    *,
    maximum_component_size: int = 7,
) -> dict[str, GlobalRankInterval]:
    """Return all target intervals after one validation pass.

    This batch surface is mathematically identical to invoking
    :func:`exact_global_rank_interval_units` for every root.  It shares only
    target-independent subset subproblems, so every returned witness and
    transition count remains target specific.
    """
    groups = _validated_groups(score_units, components, maximum_component_size)
    cache: dict[tuple[tuple[str, ...], int], tuple[int, Partition, int]] = {}
    return {
        target: _exact_for_target(score_units, groups, target, cache)
        for target in sorted(score_units)
    }
