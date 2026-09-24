from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Iterable

from .model import Atom, Commit, History
from .numeric import decimal_weight

_ALLOWED_KINDS = frozenset({"structural", "cosmetic"})


@dataclass(frozen=True)
class CertificateResult:
    valid: bool
    reasons: tuple[str, ...]
    unresolved_atoms: tuple[str, ...]
    malformed: bool = False


def _nonblank_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_relation_pairs(
    label: str,
    pairs: Iterable[tuple[str, str]],
    malformed: list[str],
) -> None:
    seen: set[tuple[str, str]] = set()
    for index, pair in enumerate(pairs, 1):
        if not isinstance(pair, tuple) or len(pair) != 2:
            malformed.append(f"{label} relation {index} is not a pair")
            continue
        left, right = pair
        if not _nonblank_text(left) or not _nonblank_text(right):
            malformed.append(f"{label} relation {index} contains a blank label")
            continue
        canonical = tuple(sorted((left, right)))
        if left == right:
            malformed.append(f"{label} relation {index} is reflexive")
        if canonical in seen:
            malformed.append(f"duplicate {label} relation: {canonical[0]}, {canonical[1]}")
        seen.add(canonical)


def _dag_reasons(commits: tuple[Commit, ...], malformed: list[str]) -> None:
    valid_commit_ids = [
        commit.commit_id for commit in commits if _nonblank_text(commit.commit_id)
    ]
    counts = Counter(valid_commit_ids)
    duplicates = sorted(commit_id for commit_id, count in counts.items() if count > 1)
    if duplicates:
        malformed.append("duplicate commit identifiers: " + ", ".join(duplicates))

    known = set(valid_commit_ids)
    indegree: dict[str, int] = {commit_id: 0 for commit_id in known}
    children: dict[str, set[str]] = defaultdict(set)
    for commit in commits:
        commit_id = commit.commit_id
        location = commit_id if _nonblank_text(commit_id) else "<blank-or-invalid>"
        if not _nonblank_text(commit_id):
            malformed.append("blank or invalid commit identifier")
        if not _nonblank_text(commit.alias):
            malformed.append(f"blank or invalid commit alias at {location}")

        seen_predecessors: set[str] = set()
        predecessors = commit.predecessors if isinstance(commit.predecessors, tuple) else tuple()
        for predecessor in predecessors:
            if not _nonblank_text(predecessor):
                malformed.append(f"blank or invalid predecessor at {location}")
                continue
            if predecessor in seen_predecessors:
                malformed.append(f"duplicate predecessor at {location}")
                continue
            seen_predecessors.add(predecessor)
            if predecessor not in known:
                malformed.append(f"missing predecessor {predecessor} at {location}")
                continue
            if predecessor == commit_id:
                malformed.append(f"self predecessor at {location}")
            if _nonblank_text(commit_id) and commit_id in indegree:
                children[predecessor].add(commit_id)
                indegree[commit_id] += 1

    # Duplicate commit identifiers already make the graph malformed and prevent
    # an unambiguous graph walk. All other diagnostics above are still useful.
    if duplicates:
        return
    queue = deque(sorted(commit_id for commit_id, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in sorted(children.get(current, ())):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(indegree):
        malformed.append("commit predecessor graph contains a cycle")


def validate_history(history: History) -> CertificateResult:
    malformed: list[str] = []
    unresolved: list[str] = []

    if not isinstance(history, History):
        return CertificateResult(
            False,
            ("history object has an invalid type",),
            tuple(),
            malformed=True,
        )
    if not _nonblank_text(history.history_id):
        malformed.append("blank history identifier")

    if not isinstance(history.commits, tuple):
        malformed.append("commits field is not a tuple")
        commits: tuple[Commit, ...] = tuple()
    else:
        valid_commits: list[Commit] = []
        for index, commit in enumerate(history.commits, 1):
            if not isinstance(commit, Commit):
                malformed.append(f"commit entry {index} has an invalid type")
                continue
            if not isinstance(commit.atoms, tuple):
                malformed.append(f"atoms field at commit {index} is not a tuple")
            if not isinstance(commit.predecessors, tuple):
                malformed.append(f"predecessors field at commit {index} is not a tuple")
            valid_commits.append(commit)
        commits = tuple(valid_commits)

    relation_fields: dict[str, tuple[tuple[str, str], ...]] = {}
    for label, value in (
        ("must-link", history.must_link),
        ("may-link", history.may_link),
        ("entity-equivalence", history.entity_equivalence),
    ):
        if not isinstance(value, tuple):
            malformed.append(f"{label} field is not a tuple")
            relation_fields[label] = tuple()
        else:
            relation_fields[label] = value
    if not isinstance(history.metadata, dict):
        malformed.append("metadata field is not a mapping")

    _dag_reasons(commits, malformed)
    for label, pairs in relation_fields.items():
        _validate_relation_pairs(label, pairs, malformed)

    must_link = relation_fields["must-link"]
    may_link = relation_fields["may-link"]
    must_pairs = {
        tuple(sorted(pair))
        for pair in must_link
        if isinstance(pair, tuple) and len(pair) == 2 and all(_nonblank_text(x) for x in pair)
    }
    may_pairs = {
        tuple(sorted(pair))
        for pair in may_link
        if isinstance(pair, tuple) and len(pair) == 2 and all(_nonblank_text(x) for x in pair)
    }
    for left, right in sorted(must_pairs & may_pairs):
        malformed.append(f"alias pair is both must-link and may-link: {left}, {right}")

    parent: dict[str, str] = {}

    def find_alias(alias: str) -> str:
        parent.setdefault(alias, alias)
        root = alias
        while parent[root] != root:
            root = parent[root]
        while parent[alias] != alias:
            next_alias = parent[alias]
            parent[alias] = root
            alias = next_alias
        return root

    def union_aliases(left: str, right: str) -> None:
        left_root, right_root = find_alias(left), find_alias(right)
        if left_root != right_root:
            keep, drop = sorted((left_root, right_root))
            parent[drop] = keep

    for pair in must_link:
        if isinstance(pair, tuple) and len(pair) == 2 and all(_nonblank_text(x) for x in pair):
            union_aliases(*pair)
    for pair in may_link:
        if isinstance(pair, tuple) and len(pair) == 2 and all(_nonblank_text(x) for x in pair):
            left, right = pair
            if find_alias(left) == find_alias(right):
                malformed.append(
                    f"may-link endpoints are already must-linked: {left}, {right}"
                )

    atoms: list[Atom] = []
    for commit_index, commit in enumerate(commits, 1):
        if not isinstance(commit.atoms, tuple):
            continue
        for atom_index, atom in enumerate(commit.atoms, 1):
            if not isinstance(atom, Atom):
                malformed.append(
                    f"event entry {atom_index} at commit {commit_index} has an invalid type"
                )
                continue
            atoms.append(atom)

    identifiers = [atom.atom_id for atom in atoms if _nonblank_text(atom.atom_id)]
    duplicates = sorted(atom_id for atom_id, count in Counter(identifiers).items() if count > 1)
    if duplicates:
        malformed.append("duplicate normalized event identifiers: " + ", ".join(duplicates))

    for atom in atoms:
        location = atom.atom_id if _nonblank_text(atom.atom_id) else "<blank>"
        if not _nonblank_text(atom.atom_id):
            malformed.append("blank normalized event identifier")
        if not _nonblank_text(atom.entity):
            malformed.append(f"blank entity at {location}")
        if not isinstance(atom.kind, str) or atom.kind not in _ALLOWED_KINDS:
            malformed.append(f"unknown event kind at {location}: {atom.kind!r}")
        try:
            weight = decimal_weight(atom.weight)
        except ValueError:
            malformed.append(f"nonfinite or nonnumeric weight at {location}")
            continue
        if weight < 0:
            malformed.append(f"negative weight at {location}")
        if atom.kind == "structural" and weight <= 0:
            malformed.append(f"nonpositive structural weight at {location}")
        if atom.kind == "cosmetic" and weight != 0:
            malformed.append(f"nonzero cosmetic weight at {location}")
        for field_name, value in (("raw_lines", atom.raw_lines), ("raw_tokens", atom.raw_tokens)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                malformed.append(f"invalid {field_name} at {location}")
        if atom.kind == "structural":
            if atom.origin is None or (isinstance(atom.origin, str) and not atom.origin.strip()):
                unresolved.append(location)
            elif not _nonblank_text(atom.origin):
                malformed.append(f"invalid origin label at {location}")
        elif atom.origin is not None and not _nonblank_text(atom.origin):
            malformed.append(f"invalid cosmetic origin label at {location}")

    reasons = list(dict.fromkeys(malformed))
    if unresolved:
        reasons.append("origin provenance is absent for structural events")
    return CertificateResult(
        valid=not reasons,
        reasons=tuple(reasons),
        unresolved_atoms=tuple(sorted(set(unresolved))),
        malformed=bool(malformed),
    )


def _relation_roots(
    histories: tuple[History, ...],
    pair_selector: Callable[[History], Iterable[tuple[str, str]]],
    item_selector: Callable[[History], Iterable[str]],
) -> dict[str, str]:
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        root = item
        while parent[root] != root:
            root = parent[root]
        while parent[item] != item:
            next_item = parent[item]
            parent[item] = root
            item = next_item
        return root

    def union(left: str, right: str) -> None:
        a, b = find(left), find(right)
        if a != b:
            keep, drop = sorted((a, b))
            parent[drop] = keep

    for history in histories:
        for item in item_selector(history):
            find(item)
        for left, right in pair_selector(history):
            union(left, right)
    return {item: find(item) for item in parent}


def _compatibility_reasons(
    original: History,
    rewritten: History,
    *,
    label: str,
    pair_selector: Callable[[History], Iterable[tuple[str, str]]],
    item_selector: Callable[[History], Iterable[str]],
) -> list[str]:
    combined = _relation_roots((original, rewritten), pair_selector, item_selector)
    reasons: list[str] = []
    for side_name, history in (("original", original), ("rewritten", rewritten)):
        local = _relation_roots((history,), pair_selector, item_selector)
        roots_by_combined: dict[str, set[str]] = defaultdict(set)
        for item in item_selector(history):
            roots_by_combined[combined.get(item, item)].add(local.get(item, item))
        if any(len(local_roots) > 1 for local_roots in roots_by_combined.values()):
            reasons.append(
                f"{label} declarations merge distinct {side_name} classes across the comparison"
            )
    return reasons


def _active_may_partition(
    history: History,
    alias_roots: dict[str, str],
) -> tuple[tuple[str, ...], ...]:
    """Return the may-link connectivity partition restricted to active classes.

    May-link edges can use aliases that carry no event mass.  Such aliases are
    retained while computing connectivity, then removed from the reported
    blocks.  Thus two different edge spellings are equivalent when they induce
    the same partition over score-bearing must-link classes.
    """
    active = {
        alias_roots.get(atom.origin, atom.origin)
        for atom in history.atoms(include_cosmetic=False)
        if atom.origin is not None
    }
    parent: dict[str, str] = {}

    def find(item: str) -> str:
        parent.setdefault(item, item)
        root = item
        while parent[root] != root:
            root = parent[root]
        while parent[item] != item:
            next_item = parent[item]
            parent[item] = root
            item = next_item
        return root

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            keep, drop = sorted((left_root, right_root))
            parent[drop] = keep

    for root in active:
        find(root)
    for left, right in history.may_link:
        union(alias_roots.get(left, left), alias_roots.get(right, right))

    blocks: dict[str, set[str]] = defaultdict(set)
    for root in active:
        blocks[find(root)].add(root)
    return tuple(sorted(tuple(sorted(block)) for block in blocks.values()))


def certify_rewrite(
    original: History,
    rewritten: History,
    *,
    event_map: Iterable[tuple[str, str]] | None = None,
) -> CertificateResult:
    original_validation = validate_history(original)
    rewritten_validation = validate_history(rewritten)
    unresolved = sorted(
        set(original_validation.unresolved_atoms) | set(rewritten_validation.unresolved_atoms)
    )

    malformed_reasons: list[str] = []
    if original_validation.malformed:
        malformed_reasons.extend(f"original malformed: {reason}" for reason in original_validation.reasons)
    if rewritten_validation.malformed:
        malformed_reasons.extend(f"rewritten malformed: {reason}" for reason in rewritten_validation.reasons)
    if malformed_reasons:
        return CertificateResult(
            False,
            tuple(dict.fromkeys(malformed_reasons)),
            tuple(unresolved),
            malformed=True,
        )

    reasons: list[str] = []
    if original_validation.unresolved_atoms:
        reasons.append("original origin provenance is incomplete")
    if rewritten_validation.unresolved_atoms:
        reasons.append("rewritten origin provenance is incomplete")

    origin_items = lambda history: (
        atom.origin
        for atom in history.atoms(include_cosmetic=False)
        if atom.origin is not None and atom.origin.strip()
    )
    entity_items = lambda history: (
        atom.entity for atom in history.atoms(include_cosmetic=False)
    )
    reasons.extend(
        _compatibility_reasons(
            original,
            rewritten,
            label="alias",
            pair_selector=lambda history: history.must_link,
            item_selector=origin_items,
        )
    )
    reasons.extend(
        _compatibility_reasons(
            original,
            rewritten,
            label="entity",
            pair_selector=lambda history: history.entity_equivalence,
            item_selector=entity_items,
        )
    )

    entity_roots = _relation_roots(
        (original, rewritten),
        lambda history: history.entity_equivalence,
        entity_items,
    )
    alias_roots = _relation_roots(
        (original, rewritten),
        lambda history: history.must_link,
        origin_items,
    )
    if _active_may_partition(original, alias_roots) != _active_may_partition(
        rewritten, alias_roots
    ):
        reasons.append("active may-link uncertainty partition changed")

    def canonical_map(history: History) -> dict[str, tuple[str, object, str | None]]:
        result: dict[str, tuple[str, object, str | None]] = {}
        for atom in history.atoms(include_cosmetic=False):
            if atom.atom_id in result:
                # Local validation normally catches this.  Keep the comparison
                # defensive in case callers bypass or mutate that surface.
                reasons.append(f"event {atom.atom_id} occurs more than once")
                continue
            entity = entity_roots.get(atom.entity, atom.entity)
            canonical_origin = (
                alias_roots.get(atom.origin, atom.origin) if atom.origin is not None else None
            )
            result[atom.atom_id] = (entity, decimal_weight(atom.weight), canonical_origin)
        return result

    left = canonical_map(original)
    right = canonical_map(rewritten)

    pairs: list[tuple[str, str]] = []
    if event_map is None:
        shared = sorted(set(left) & set(right))
        pairs.extend((atom_id, atom_id) for atom_id in shared)
        mapped_left = set(shared)
        mapped_right = set(shared)
    else:
        try:
            supplied_pairs = tuple(event_map)
        except TypeError:
            supplied_pairs = tuple()
            reasons.append("event map is not iterable")
        mapped_left: set[str] = set()
        mapped_right: set[str] = set()
        for index, pair in enumerate(supplied_pairs, 1):
            if not isinstance(pair, tuple) or len(pair) != 2:
                reasons.append(f"event-map entry {index} is not a pair")
                continue
            source, target = pair
            if not _nonblank_text(source) or not _nonblank_text(target):
                reasons.append(f"event-map entry {index} contains a blank identifier")
                continue
            if source in mapped_left:
                reasons.append(f"event map repeats source {source}")
                continue
            if target in mapped_right:
                reasons.append(f"event map repeats target {target}")
                continue
            mapped_left.add(source)
            mapped_right.add(target)
            pairs.append((source, target))

    missing = sorted(set(left) - mapped_left)
    extra = sorted(set(right) - mapped_right)
    unknown_sources = sorted(mapped_left - set(left))
    unknown_targets = sorted(mapped_right - set(right))
    if missing:
        reasons.append("unmapped original structural events: " + ", ".join(missing))
    if extra:
        reasons.append("unmapped rewritten structural events: " + ", ".join(extra))
    if unknown_sources:
        reasons.append("event map names absent original events: " + ", ".join(unknown_sources))
    if unknown_targets:
        reasons.append("event map names absent rewritten events: " + ", ".join(unknown_targets))

    for source_id, target_id in sorted(pairs):
        if source_id not in left or target_id not in right:
            continue
        left_entity, left_weight, left_origin = left[source_id]
        right_entity, right_weight, right_origin = right[target_id]
        location = source_id if source_id == target_id else f"{source_id}->{target_id}"
        if left_entity != right_entity:
            reasons.append(f"entity changed without declaration at {location}")
        if left_weight != right_weight:
            reasons.append(f"weight changed at {location}")
        if left_origin != right_origin:
            reasons.append(f"origin changed at {location}")
    if unresolved:
        reasons.append("origin provenance is absent for structural events")
    return CertificateResult(
        not reasons,
        tuple(dict.fromkeys(reasons)),
        tuple(unresolved),
        malformed=False,
    )
