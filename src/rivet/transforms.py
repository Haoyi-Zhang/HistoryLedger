from __future__ import annotations

from dataclasses import replace
from itertools import count

from .aliases import UnionFind
from .model import Atom, Commit, History
from .numeric import sum_weight_units


def _fresh_name(prefix: str, used: set[str], start: int = 1) -> str:
    """Reserve a deterministic unused label, including declaration-only labels."""
    index = start
    while f"{prefix}{index:04d}" in used:
        index += 1
    label = f"{prefix}{index:04d}"
    used.add(label)
    return label


def _linear_predecessors(commits: list[Commit]) -> tuple[Commit, ...]:
    result: list[Commit] = []
    previous: str | None = None
    for commit in commits:
        predecessors = (previous,) if previous is not None else tuple()
        result.append(replace(commit, predecessors=predecessors))
        previous = commit.commit_id
    return tuple(result)


def split_commits(history: History) -> History:
    commits: list[Commit] = []
    serial = count(1)
    for commit in history.commits:
        structural = list(commit.atoms)
        if len(structural) < 2:
            commits.append(replace(commit, commit_id=f"S{next(serial):03d}"))
            continue
        left = tuple(structural[::2])
        right = tuple(structural[1::2])
        commits.append(Commit(f"S{next(serial):03d}", commit.alias, left))
        commits.append(Commit(f"S{next(serial):03d}", commit.alias, right))
    return replace(history, history_id=history.history_id + "-split", commits=_linear_predecessors(commits))


def squash_pairs(history: History, *, retain_origins: bool = True) -> History:
    commits: list[Commit] = []
    serial = count(1)
    index = 0
    while index < len(history.commits):
        first = history.commits[index]
        if index + 1 >= len(history.commits):
            commits.append(replace(first, commit_id=f"Q{next(serial):03d}"))
            break
        second = history.commits[index + 1]
        alias = first.alias if first.alias == second.alias else "integrator"
        atoms: list[Atom] = []
        for atom in first.atoms + second.atoms:
            atoms.append(atom if retain_origins else replace(atom, origin=None))
        commits.append(Commit(f"Q{next(serial):03d}", alias, tuple(atoms)))
        index += 2
    suffix = "-squash-certified" if retain_origins else "-squash-unobserved"
    return replace(history, history_id=history.history_id + suffix, commits=_linear_predecessors(commits))


def squash_cross_origin(history: History, *, retain_origins: bool = False) -> History:
    """Squash the shortest contiguous multi-commit span with two origins.

    The negative variant removes event-level origins only inside a span that
    demonstrably crosses origin classes.  This avoids treating an arbitrary
    same-origin pair squash as evidence for the provenance-erasure boundary.
    """
    classes = UnionFind(history.aliases())
    for left, right in history.must_link:
        classes.union(left, right)

    best: tuple[int, int] | None = None
    for start in range(len(history.commits)):
        origins: set[str] = set()
        for end in range(start, len(history.commits)):
            origins.update(
                classes.find(atom.origin)
                for atom in history.commits[end].atoms
                if atom.kind == "structural" and atom.origin is not None
            )
            span_length = end - start + 1
            if span_length >= 2 and len(origins) >= 2:
                candidate = (start, end + 1)
                if best is None or (span_length, start) < (best[1] - best[0], best[0]):
                    best = candidate
                break
    if best is None:
        raise ValueError("history has no contiguous multi-commit cross-origin span")

    start, end = best
    block = history.commits[start:end]
    atoms = tuple(
        atom
        if retain_origins or atom.kind == "cosmetic"
        else replace(atom, origin=None)
        for commit in block
        for atom in commit.atoms
    )
    combined = Commit("cross-origin", "integrator", atoms)
    commits = list(history.commits[:start]) + [combined] + list(history.commits[end:])
    commits = [replace(commit, commit_id=f"X{index:03d}") for index, commit in enumerate(commits, 1)]
    metadata = dict(history.metadata)
    metadata["cross_origin_span_commits"] = end - start
    suffix = "-cross-origin-certified" if retain_origins else "-cross-origin-unobserved"
    return replace(
        history,
        history_id=history.history_id + suffix,
        commits=_linear_predecessors(commits),
        metadata=metadata,
    )


def reorder_independent(history: History) -> History:
    commits = list(history.commits)
    index = 0
    while index + 1 < len(commits):
        if commits[index].entities.isdisjoint(commits[index + 1].entities):
            commits[index], commits[index + 1] = commits[index + 1], commits[index]
            index += 2
        else:
            index += 1
    commits = [replace(commit, commit_id=f"R{idx:03d}") for idx, commit in enumerate(commits, 1)]
    return replace(history, history_id=history.history_id + "-reorder", commits=_linear_predecessors(commits))


def add_cosmetic_padding(history: History, lines_per_commit: int = 12) -> History:
    commits: list[Commit] = []
    used = {atom.atom_id for atom in history.atoms()}
    for index, commit in enumerate(history.commits, 1):
        cosmetic = Atom(
            atom_id=_fresh_name("Z", used, index),
            entity=f"cosmetic-{index:04d}",
            weight=0.0,
            origin=commit.alias,
            raw_lines=lines_per_commit,
            raw_tokens=0,
            kind="cosmetic",
        )
        commits.append(replace(commit, atoms=commit.atoms + (cosmetic,)))
    return replace(history, history_id=history.history_id + "-formatting", commits=tuple(commits))


def add_empty_commits(history: History) -> History:
    commits: list[Commit] = []
    serial = count(1)
    for commit in history.commits:
        commits.append(replace(commit, commit_id=f"P{next(serial):03d}"))
        commits.append(Commit(f"P{next(serial):03d}", commit.alias, tuple()))
    return replace(history, history_id=history.history_id + "-padding", commits=_linear_predecessors(commits))


def move_entities(history: History) -> History:
    entities = sorted({atom.entity for atom in history.atoms(include_cosmetic=False)})
    used = {atom.entity for atom in history.atoms()}
    used.update(label for pair in history.entity_equivalence for label in pair)
    mapping = {entity: _fresh_name("moved-", used, index)
               for index, entity in enumerate(entities, 1)}
    commits: list[Commit] = []
    for commit in history.commits:
        commits.append(
            replace(
                commit,
                atoms=tuple(
                    replace(atom, entity=mapping.get(atom.entity, atom.entity)) for atom in commit.atoms
                ),
            )
        )
    equivalence = history.entity_equivalence + tuple((old, new) for old, new in mapping.items())
    return replace(
        history,
        history_id=history.history_id + "-move",
        commits=tuple(commits),
        entity_equivalence=equivalence,
    )


def _alias_split_candidate(
    history: History,
    target: str,
) -> tuple[int, tuple[str, ...], str, str] | None:
    """Describe a pure two-child split for one raw score-bearing alias."""
    related = {
        alias
        for pair in history.must_link + history.may_link
        for alias in pair
    }
    if target in related:
        return None

    left, right = target + "-x", target + "-y"
    known_aliases = set(history.aliases())
    if left in known_aliases or right in known_aliases or left == right:
        return None

    evidence_commits: list[str] = []
    event_weights: list[object] = []
    for commit in history.commits:
        target_events = tuple(
            atom
            for atom in commit.atoms
            if atom.kind == "structural" and atom.origin == target
        )
        if not target_events:
            continue
        if commit.alias != target:
            # Renaming only the target's own commit containers would leave part
            # of its event mass under another container, so the split would not
            # isolate identity representation from integration representation.
            return None
        evidence_commits.append(commit.commit_id)
        event_weights.extend(atom.weight for atom in target_events)

    if len(evidence_commits) < 2:
        return None
    return sum_weight_units(event_weights), tuple(evidence_commits), left, right


def _choose_alias_split(
    history: History,
    target: str | None,
) -> tuple[str, tuple[str, ...], str, str, int]:
    if target is not None:
        plan = _alias_split_candidate(history, target)
        if plan is None:
            raise ValueError(
                f"alias {target!r} does not admit an isolated two-child split"
            )
        mass, commits, left, right = plan
        return target, commits, left, right, mass

    candidates: list[tuple[int, str, tuple[str, ...], str, str]] = []
    raw_origins = sorted(
        {
            atom.origin
            for atom in history.atoms(include_cosmetic=False)
            if atom.origin is not None
        }
    )
    for alias in raw_origins:
        plan = _alias_split_candidate(history, alias)
        if plan is None:
            continue
        mass, commits, left, right = plan
        candidates.append((mass, alias, commits, left, right))
    if not candidates:
        raise ValueError("history has no alias admitting an isolated two-child split")
    mass, alias, commits, left, right = min(
        candidates,
        key=lambda item: (-item[0], item[1]),
    )
    return alias, commits, left, right, mass


def split_alias_ambiguous(history: History, target: str | None = None) -> History:
    target, evidence_commits, left, right, target_units = _choose_alias_split(
        history, target
    )
    evidence_set = set(evidence_commits)
    commits: list[Commit] = []
    active_index = 0
    for commit in history.commits:
        if commit.alias != target:
            commits.append(commit)
            continue
        replacement = left if active_index % 2 == 0 else right
        if commit.commit_id in evidence_set:
            # Only score-bearing commits advance the alternation.  Empty or
            # container-only records inherit the current child without moving
            # the evidence schedule, so both children remain score-bearing.
            active_index += 1
        commits.append(
            replace(
                commit,
                alias=replacement,
                atoms=tuple(
                    replace(atom, origin=replacement if atom.origin == target else atom.origin)
                    for atom in commit.atoms
                ),
            )
        )
    if active_index < 2:
        raise AssertionError("alias split did not activate both child aliases")
    metadata = dict(history.metadata)
    metadata.update(
        {
            "alias_target": target,
            "alias_children": [left, right],
            "alias_target_units": target_units,
            "alias_evidence_commits": list(evidence_commits),
        }
    )
    return replace(
        history,
        history_id=history.history_id + "-alias-ambiguous",
        commits=tuple(commits),
        may_link=history.may_link + ((left, right),),
        metadata=metadata,
    )


def split_alias_certified(history: History, target: str | None = None) -> History:
    ambiguous = split_alias_ambiguous(history, target)
    pair = ambiguous.may_link[-1]
    target = str(ambiguous.metadata["alias_target"])
    left, right = pair
    return replace(
        ambiguous,
        history_id=history.history_id + "-alias-certified",
        may_link=ambiguous.may_link[:-1],
        must_link=history.must_link + ((target, left), (target, right), (left, right)),
    )

def rename_event_identifiers(
    history: History,
) -> tuple[History, tuple[tuple[str, str], ...]]:
    """Rename structural event identifiers and return the explicit bijection."""
    mapping: list[tuple[str, str]] = []
    renamed: dict[str, str] = {}
    used = {atom.atom_id for atom in history.atoms()}
    for index, atom in enumerate(history.atoms(include_cosmetic=False), 1):
        new_identifier = _fresh_name("N", used, index)
        renamed[atom.atom_id] = new_identifier
        mapping.append((atom.atom_id, new_identifier))
    commits = tuple(
        replace(
            commit,
            atoms=tuple(
                replace(atom, atom_id=renamed[atom.atom_id])
                if atom.kind != "cosmetic"
                else atom
                for atom in commit.atoms
            ),
        )
        for commit in history.commits
    )
    return (
        replace(history, history_id=history.history_id + "-event-map", commits=commits),
        tuple(mapping),
    )
