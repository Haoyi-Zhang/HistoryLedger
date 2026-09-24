from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

from .numeric import canonical_weight


@dataclass(frozen=True)
class Atom:
    """A normalized change event.

    ``origin`` records the alias that introduced the event.  It is deliberately
    distinct from the alias on the containing commit: a squash or integration
    commit can contain events that originated with several aliases.
    """

    atom_id: str
    entity: str
    weight: float
    origin: str | None
    raw_lines: int = 0
    raw_tokens: int = 0
    kind: str = "structural"

    def canonical(self) -> tuple[str, float, str | None, str]:
        return (self.atom_id, canonical_weight(self.weight), self.origin, self.kind)


@dataclass(frozen=True)
class Commit:
    commit_id: str
    alias: str
    atoms: tuple[Atom, ...] = field(default_factory=tuple)
    predecessors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def entities(self) -> frozenset[str]:
        return frozenset(atom.entity for atom in self.atoms if atom.kind != "cosmetic")


@dataclass(frozen=True)
class History:
    history_id: str
    commits: tuple[Commit, ...]
    must_link: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    may_link: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    entity_equivalence: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def aliases(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for commit in self.commits:
            seen.setdefault(commit.alias, None)
            for atom in commit.atoms:
                if atom.origin is not None:
                    seen.setdefault(atom.origin, None)
        for left, right in self.must_link + self.may_link:
            seen.setdefault(left, None)
            seen.setdefault(right, None)
        return tuple(seen)

    def atoms(self, *, include_cosmetic: bool = True) -> tuple[Atom, ...]:
        atoms: list[Atom] = []
        for commit in self.commits:
            for atom in commit.atoms:
                if include_cosmetic or atom.kind != "cosmetic":
                    atoms.append(atom)
        return tuple(atoms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_id": self.history_id,
            "commits": [
                {
                    "commit_id": c.commit_id,
                    "alias": c.alias,
                    "predecessors": list(c.predecessors),
                    "atoms": [asdict(a) for a in c.atoms],
                }
                for c in self.commits
            ],
            "must_link": [list(pair) for pair in self.must_link],
            "may_link": [list(pair) for pair in self.may_link],
            "entity_equivalence": [list(pair) for pair in self.entity_equivalence],
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "History":
        commits = []
        for raw_commit in data["commits"]:
            commits.append(
                Commit(
                    commit_id=raw_commit["commit_id"],
                    alias=raw_commit["alias"],
                    predecessors=tuple(raw_commit.get("predecessors", [])),
                    atoms=tuple(Atom(**raw_atom) for raw_atom in raw_commit.get("atoms", [])),
                )
            )
        return History(
            history_id=data["history_id"],
            commits=tuple(commits),
            must_link=tuple(tuple(pair) for pair in data.get("must_link", [])),
            may_link=tuple(tuple(pair) for pair in data.get("may_link", [])),
            entity_equivalence=tuple(
                tuple(pair) for pair in data.get("entity_equivalence", [])
            ),
            metadata=data.get("metadata", {}),
        )

    def restrict_atoms(self, atom_ids: Iterable[str]) -> "History":
        keep = frozenset(atom_ids)
        commits = tuple(
            Commit(
                commit_id=c.commit_id,
                alias=c.alias,
                predecessors=c.predecessors,
                atoms=tuple(a for a in c.atoms if a.atom_id in keep),
            )
            for c in self.commits
        )
        return History(
            history_id=self.history_id,
            commits=commits,
            must_link=self.must_link,
            may_link=self.may_link,
            metadata=self.metadata,
            entity_equivalence=self.entity_equivalence,
        )
