from __future__ import annotations

from itertools import combinations
from typing import Callable

from .model import History


def exact_minimal_atom_witness(
    original: History,
    rewritten: History,
    predicate: Callable[[History, History], bool],
    *,
    maximum_atoms: int = 14,
) -> tuple[str, ...]:
    """Find a minimum-cardinality atom subset satisfying ``predicate``.

    The routine is exact over at most ``maximum_atoms`` shared structural atom
    identifiers. Larger surfaces are rejected rather than truncated, so every
    returned witness is exact for the complete supplied universe.
    """
    identifiers = sorted(
        set(atom.atom_id for atom in original.atoms(include_cosmetic=False))
        & set(atom.atom_id for atom in rewritten.atoms(include_cosmetic=False))
    )
    if isinstance(maximum_atoms, bool) or not isinstance(maximum_atoms, int):
        raise ValueError("maximum_atoms must be an integer")
    if maximum_atoms < 1:
        raise ValueError("maximum_atoms must be positive")
    if len(identifiers) > maximum_atoms:
        raise ValueError(
            f"shared event surface has {len(identifiers)} atoms; exact cap is {maximum_atoms}"
        )
    for size in range(1, len(identifiers) + 1):
        for subset in combinations(identifiers, size):
            left = original.restrict_atoms(subset)
            right = rewritten.restrict_atoms(subset)
            if predicate(left, right):
                return subset
    return tuple()
