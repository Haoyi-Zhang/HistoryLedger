"""Ordinary same-information aggregation; not a rewrite certificate.

Shares the input validator and numeric convention with Rivet, but uses graph
traversal rather than its class/summation routines. All weights, origins, entity
declarations and identity links are available to both. No origin is inferred
from a container author. Buckets retain actor/entity totals, not event maps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .certificate import validate_history
from .model import History
from .numeric import weight_units


def _classes(labels: Iterable[str], pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    graph: dict[str, set[str]] = {label: set() for label in labels}
    for left, right in pairs:
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set()).add(left)
    roots: dict[str, str] = {}
    for start in sorted(graph):
        if start in roots:
            continue
        pending, reached = [start], set()
        while pending:
            label = pending.pop()
            if label in reached:
                continue
            reached.add(label)
            pending.extend(graph[label] - reached)
        representative = min(reached)
        roots.update((label, representative) for label in reached)
    return roots


@dataclass(frozen=True)
class ProvenanceLedger:
    status: str
    score_units: dict[str, int]
    attribution_buckets: dict[tuple[str, str], int]
    components: tuple[tuple[str, ...], ...]


def provenance_ledger(history: History) -> ProvenanceLedger:
    """Sum supplied event origins and expose supplied identity ambiguity.

    Matching totals or buckets does not establish per-event correspondence,
    validate origins, or authenticate extraction. Empty/missing-origin inputs
    have the same declared decision policy as the main analysis. The shared
    status tag CERTIFIED means resolved point-score eligibility here, not that
    this aggregator has checked a rewrite certificate.
    """
    validation = validate_history(history)
    if validation.malformed:
        return ProvenanceLedger("MALFORMED_EVIDENCE", {}, {}, ())
    if validation.unresolved_atoms:
        return ProvenanceLedger("ABSTAIN_ORIGIN", {}, {}, ())
    roots = _classes(history.aliases(), history.must_link)
    entities = _classes((atom.entity for atom in history.atoms()),
                        history.entity_equivalence)
    scores: dict[str, int] = {}
    buckets: dict[tuple[str, str], int] = {}
    for atom in history.atoms(include_cosmetic=False):
        actor = roots[atom.origin]
        units = weight_units(atom.weight)
        scores[actor] = scores.get(actor, 0) + units
        key = (actor, entities[atom.entity])
        buckets[key] = buckets.get(key, 0) + units
    connectivity = _classes(roots.values(),
                            ((roots[left], roots[right]) for left, right in history.may_link))
    active: dict[str, list[str]] = {}
    for actor in sorted(scores):
        active.setdefault(connectivity[actor], []).append(actor)
    components = tuple(sorted(tuple(group) for group in active.values()))
    status = "PARTIAL_ALIAS_ABSTENTION" if any(len(g) > 1 for g in components) else "CERTIFIED"
    return ProvenanceLedger(status, dict(sorted(scores.items())),
                            dict(sorted(buckets.items())), components)
