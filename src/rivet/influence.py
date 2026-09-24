from __future__ import annotations

from dataclasses import dataclass

from .aliases import collapse_must_link_term_units
from .model import History
from .numeric import units_to_weight, weight_units
from .score import analyze_history


@dataclass(frozen=True)
class ScoreInfluence:
    """Exact score interval under an event-origin reassignment budget.

    The attacker may relabel the origin of at most ``budget`` structural events
    to another observed actor class but cannot change event identifiers,
    entities, or weights.  This is an explicit attribution-tampering model, not
    a certified rewrite.
    """

    actor: str
    budget: int
    original: float
    minimum: float
    maximum: float
    removable_mass: float
    acquirable_mass: float
    original_units: int
    minimum_units: int
    maximum_units: int
    removable_units: int
    acquirable_units: int


def _resolved_origins(history: History) -> tuple[dict[str, int], dict[str, str]]:
    """Return resolved actor totals and the alias-to-class map.

    Influence questions concern a named actor class.  They are intentionally
    undefined when the evidence is malformed, a positive event lacks an
    origin, or a may-link leaves actor identity unresolved.
    """
    analysis = analyze_history(history)
    if analysis.status == "MALFORMED_EVIDENCE":
        raise ValueError("history evidence is malformed")
    if analysis.status == "ABSTAIN_ORIGIN":
        raise ValueError("origin provenance is incomplete")
    if analysis.status == "PARTIAL_ALIAS_ABSTENTION":
        raise ValueError("actor identity is unresolved by may-link declarations")

    grouped: dict[str, list[object]] = {}
    for atom in history.atoms(include_cosmetic=False):
        if atom.origin is None:
            raise AssertionError("resolved structural atom unexpectedly lacks origin")
        grouped.setdefault(atom.origin, []).append(atom.weight)
    collapsed, root_for, _members = collapse_must_link_term_units(
        grouped, history.must_link
    )
    if collapsed != analysis.score_units:
        raise AssertionError("analysis and influence canonicalization disagree")
    return analysis.score_units, root_for


def score_influence(history: History, actor: str, budget: int) -> ScoreInfluence:
    if isinstance(budget, bool) or not isinstance(budget, int):
        raise ValueError("budget must be an integer")
    if budget < 0:
        raise ValueError("budget must be non-negative")
    score_units, root_for = _resolved_origins(history)
    canonical_actor = root_for.get(actor, actor)
    if canonical_actor not in score_units:
        raise ValueError(f"unknown actor class: {actor}")

    owned_units: list[int] = []
    other_units: list[int] = []
    for atom in history.atoms(include_cosmetic=False):
        if atom.origin is None:
            raise AssertionError("resolved structural atom unexpectedly lacks origin")
        units = weight_units(atom.weight)
        if root_for.get(atom.origin, atom.origin) == canonical_actor:
            owned_units.append(units)
        else:
            other_units.append(units)

    # Perform the optimization entirely on exact integer multiples of the
    # frozen weight quantum.  Public float fields are converted only once at
    # the return boundary, avoiding a float-to-decimal round trip.
    original_units = sum(owned_units)
    removable_units = (
        sum(sorted(owned_units, reverse=True)[:budget])
        if len(score_units) > 1
        else 0
    )
    acquirable_units = sum(sorted(other_units, reverse=True)[:budget])
    minimum_units = max(0, original_units - removable_units)
    maximum_units = original_units + acquirable_units
    original = units_to_weight(original_units)
    removable = units_to_weight(removable_units)
    acquirable = units_to_weight(acquirable_units)
    minimum = units_to_weight(minimum_units)
    maximum = units_to_weight(maximum_units)
    return ScoreInfluence(
        actor=canonical_actor,
        budget=budget,
        original=original,
        minimum=minimum,
        maximum=maximum,
        removable_mass=removable,
        acquirable_mass=acquirable,
        original_units=original_units,
        minimum_units=minimum_units,
        maximum_units=maximum_units,
        removable_units=removable_units,
        acquirable_units=acquirable_units,
    )


@dataclass(frozen=True)
class RankInfluence:
    actor: str
    budget: int
    best_rank: int
    worst_rank: int
    score: ScoreInfluence


def rank_influence(history: History, actor: str, budget: int) -> RankInfluence:
    """Return a sound rank interval under the shared tampering budget.

    Each actor's score interval is computed exactly in isolation.  Combining
    those intervals relaxes the single shared budget, so the returned rank
    interval is conservative rather than necessarily attainable at both ends.
    """
    actor_score = score_influence(history, actor, budget)
    analysis = analyze_history(history)
    canonical_actor = actor_score.actor
    competitors = [name for name in analysis.score_units if name != canonical_actor]
    competitor_scores = [score_influence(history, name, budget) for name in competitors]
    best = 1 + sum(bound.minimum > actor_score.maximum for bound in competitor_scores)
    worst = 1 + sum(bound.maximum > actor_score.minimum for bound in competitor_scores)
    return RankInfluence(canonical_actor, budget, best, worst, actor_score)


@dataclass(frozen=True)
class PairwiseWinnerFlip:
    """Exact minimum relabelings needed for one challenger to beat a leader."""

    leader: str
    challenger: str
    initial_gap: float
    initial_gap_units: int
    minimum_relabels: int
    gain_before: float
    selected_gain: float
    gain_before_units: int
    selected_gain_units: int
    winning_margin: float
    winning_margin_units: int
    witness_atoms: tuple[str, ...]


@dataclass(frozen=True)
class WinnerFlipRadius:
    """Exact strict-winner fragility under origin-label tampering.

    ``minimum_relabels`` is ``None`` only when the resolved history contains a
    single actor class, so no observed challenger exists.  Otherwise the
    witness relabels every listed event directly to ``challenger``.
    """

    leader: str
    leader_score: float
    leader_score_units: int
    minimum_relabels: int | None
    challenger: str | None
    initial_gap: float | None
    initial_gap_units: int | None
    winning_margin: float | None
    winning_margin_units: int | None
    witness_atoms: tuple[str, ...]
    pairwise: tuple[PairwiseWinnerFlip, ...]


def strict_winner_flip_radius(
    history: History,
    leader: str | None = None,
) -> WinnerFlipRadius:
    """Compute the exact minimum origin-label changes that dethrone a winner.

    The tampering model is the one used by :func:`score_influence`: one action
    changes the origin class of one positive structural event to another
    observed class, while its identifier, entity, and weight remain fixed.
    The supplied (or inferred) leader must be the unique current score winner.

    For a challenger ``c`` with initial deficit ``d``, moving a leader-owned
    event of weight ``w`` to ``c`` closes ``2w`` of the deficit.  Moving an
    event owned by a third actor to ``c`` closes ``w``; changing a
    challenger-owned event cannot help.  Consequently the exact radius is the
    shortest prefix of these gains, sorted descending, whose sum is strictly
    greater than ``d``.  The preceding prefix certifies minimality.
    """
    score_units, root_for = _resolved_origins(history)
    if not score_units:
        raise ValueError("history has no scored actor class")

    if leader is None:
        maximum = max(score_units.values())
        leaders = sorted(actor for actor, score in score_units.items() if score == maximum)
        if len(leaders) != 1:
            raise ValueError("strict winner-flip radius requires a unique current winner")
        canonical_leader = leaders[0]
    else:
        canonical_leader = root_for.get(leader, leader)
        if canonical_leader not in score_units:
            raise ValueError(f"unknown actor class: {leader}")
        if any(
            score >= score_units[canonical_leader]
            for actor, score in score_units.items()
            if actor != canonical_leader
        ):
            raise ValueError("supplied leader is not the unique current winner")

    events: list[tuple[str, str, int]] = []
    for atom in history.atoms(include_cosmetic=False):
        if atom.origin is None:
            raise AssertionError("resolved structural atom unexpectedly lacks origin")
        events.append(
            (
                atom.atom_id,
                root_for.get(atom.origin, atom.origin),
                weight_units(atom.weight),
            )
        )

    pairwise: list[PairwiseWinnerFlip] = []
    for challenger in sorted(actor for actor in score_units if actor != canonical_leader):
        gap_units = score_units[canonical_leader] - score_units[challenger]
        gains = sorted(
            (
                (
                    2 * units if owner == canonical_leader else units,
                    atom_id,
                )
                for atom_id, owner, units in events
                if owner != challenger
            ),
            key=lambda item: (-item[0], item[1]),
        )
        cumulative = 0
        previous = 0
        witness: list[str] = []
        for gain, atom_id in gains:
            if gain <= 0:
                continue
            previous = cumulative
            cumulative += gain
            witness.append(atom_id)
            if cumulative > gap_units:
                break
        if cumulative <= gap_units:
            # Positive leader mass always makes a challenger reachable by
            # sending all leader events to that challenger.  Keep an explicit
            # assertion so a future model change cannot silently violate it.
            raise AssertionError("no strict winner-flip witness exists")
        pairwise.append(
            PairwiseWinnerFlip(
                leader=canonical_leader,
                challenger=challenger,
                initial_gap=units_to_weight(gap_units),
                initial_gap_units=gap_units,
                minimum_relabels=len(witness),
                gain_before=units_to_weight(previous),
                selected_gain=units_to_weight(cumulative),
                gain_before_units=previous,
                selected_gain_units=cumulative,
                winning_margin=units_to_weight(cumulative - gap_units),
                winning_margin_units=cumulative - gap_units,
                witness_atoms=tuple(witness),
            )
        )

    if not pairwise:
        return WinnerFlipRadius(
            leader=canonical_leader,
            leader_score=units_to_weight(score_units[canonical_leader]),
            leader_score_units=score_units[canonical_leader],
            minimum_relabels=None,
            challenger=None,
            initial_gap=None,
            initial_gap_units=None,
            winning_margin=None,
            winning_margin_units=None,
            witness_atoms=tuple(),
            pairwise=tuple(),
        )

    best = min(pairwise, key=lambda result: (result.minimum_relabels, result.challenger))
    return WinnerFlipRadius(
        leader=canonical_leader,
        leader_score=units_to_weight(score_units[canonical_leader]),
        leader_score_units=score_units[canonical_leader],
        minimum_relabels=best.minimum_relabels,
        challenger=best.challenger,
        initial_gap=best.initial_gap,
        initial_gap_units=best.initial_gap_units,
        winning_margin=best.winning_margin,
        winning_margin_units=best.winning_margin_units,
        witness_atoms=best.witness_atoms,
        pairwise=tuple(pairwise),
    )
