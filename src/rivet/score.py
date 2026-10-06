from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from .aliases import AliasSummary, summarize_alias_terms
from .certificate import CertificateResult, validate_history
from .model import History
from .numeric import sum_weights, weight_units


@dataclass(frozen=True)
class AnalysisResult:
    status: str
    scores: dict[str, float]
    score_units: dict[str, int]
    ranking: tuple[tuple[str, float], ...]
    certificate: CertificateResult
    aliases: AliasSummary | None


def rank(scores: dict[str, float]) -> tuple[tuple[str, float], ...]:
    units = {alias: weight_units(value) for alias, value in scores.items()}
    return tuple(
        (alias, scores[alias])
        for alias in sorted(scores, key=lambda alias: (-units[alias], alias))
    )


def analyze_history(history: History) -> AnalysisResult:
    certificate = validate_history(history)
    if certificate.malformed:
        return AnalysisResult(
            status="MALFORMED_EVIDENCE",
            scores={},
            score_units={},
            ranking=tuple(),
            certificate=certificate,
            aliases=None,
        )
    if certificate.unresolved_atoms:
        return AnalysisResult(
            status="ABSTAIN_ORIGIN",
            scores={},
            score_units={},
            ranking=tuple(),
            certificate=certificate,
            aliases=None,
        )
    grouped: dict[str, list[float]] = defaultdict(list)
    for atom in history.atoms(include_cosmetic=False):
        if atom.origin is None:
            raise AssertionError("validated structural atom unexpectedly lacks origin")
        grouped[atom.origin].append(atom.weight)
    aliases = summarize_alias_terms(grouped, history.must_link, history.may_link)
    status = (
        "PARTIAL_ALIAS_ABSTENTION"
        if aliases.unresolved_components
        else "CERTIFIED"
    )
    ranking = (
        tuple(
            (alias, aliases.collapsed_scores[alias])
            for alias in sorted(
                aliases.collapsed_units,
                key=lambda alias: (-aliases.collapsed_units[alias], alias),
            )
        )
        if status == "CERTIFIED"
        else tuple()
    )
    return AnalysisResult(
        status=status,
        scores=aliases.collapsed_scores,
        score_units=aliases.collapsed_units,
        ranking=ranking,
        certificate=certificate,
        aliases=aliases,
    )


def baseline_scores(history: History, method: str) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    if method == "commit_count":
        for commit in history.commits:
            if commit.atoms or history.metadata.get("count_empty_commits", True):
                scores[commit.alias] += 1.0
    elif method == "line_count":
        for commit in history.commits:
            scores[commit.alias] += sum(atom.raw_lines for atom in commit.atoms)
    elif method == "token_count":
        for commit in history.commits:
            scores[commit.alias] += sum(atom.raw_tokens for atom in commit.atoms)
    elif method == "structural_no_origin":
        for commit in history.commits:
            scores[commit.alias] += sum_weights(
                atom.weight for atom in commit.atoms if atom.kind != "cosmetic"
            )
    elif method == "entity_degree":
        alias_entities: dict[str, set[str]] = defaultdict(set)
        entity_aliases: dict[str, set[str]] = defaultdict(set)
        for commit in history.commits:
            for atom in commit.atoms:
                if atom.kind == "cosmetic":
                    continue
                alias_entities[commit.alias].add(atom.entity)
                entity_aliases[atom.entity].add(commit.alias)
        for alias, entities in alias_entities.items():
            scores[alias] = sum(1.0 + len(entity_aliases[entity]) for entity in entities)
    else:
        raise ValueError(f"unknown baseline: {method}")
    return dict(sorted(scores.items()))


def top_alias_units(scores: dict[str, int]) -> str | None:
    if not scores:
        return None
    return min(((-scores[alias], alias) for alias in scores))[1]


def top_alias(scores: dict[str, float]) -> str | None:
    return top_alias_units(
        {alias: weight_units(value) for alias, value in scores.items()}
    )


def normalized_l1_units(left_units: dict[str, int], right_units: dict[str, int]) -> float:
    if left_units == right_units:
        return 0.0
    aliases = sorted(set(left_units) | set(right_units))
    left_total = sum(left_units.values())
    right_total = sum(right_units.values())
    if left_total == 0 and right_total == 0:
        return 0.0
    distance = Fraction(0)
    for alias in aliases:
        left_share = (
            Fraction(left_units.get(alias, 0), left_total)
            if left_total
            else Fraction(0)
        )
        right_share = (
            Fraction(right_units.get(alias, 0), right_total)
            if right_total
            else Fraction(0)
        )
        distance += abs(left_share - right_share)
    return float(distance / 2)


def normalized_l1(left: dict[str, float], right: dict[str, float]) -> float:
    return normalized_l1_units(
        {alias: weight_units(value) for alias, value in left.items()},
        {alias: weight_units(value) for alias, value in right.items()},
    )


def kendall_tau_b_units(left_units: dict[str, int], right_units: dict[str, int]) -> float | None:
    """Standard tau-b on the alias union, with absent scores set to zero.

    Pair signs and ties use exact integers. Return None if the denominator is
    zero (including fewer than two aliases); do not impute a correlation.
    """
    aliases = sorted(set(left_units) | set(right_units))
    concordant = 0
    discordant = 0
    ties_left_only = 0
    ties_right_only = 0
    for i, first in enumerate(aliases):
        for second in aliases[i + 1 :]:
            ldiff = left_units.get(first, 0) - left_units.get(second, 0)
            rdiff = right_units.get(first, 0) - right_units.get(second, 0)
            lsign = (ldiff > 0) - (ldiff < 0)
            rsign = (rdiff > 0) - (rdiff < 0)
            if lsign == 0 and rsign != 0:
                ties_left_only += 1
            elif rsign == 0 and lsign != 0:
                ties_right_only += 1
            elif lsign == rsign and lsign != 0:
                concordant += 1
            elif lsign == -rsign and lsign != 0:
                discordant += 1
    denominator = (
        (concordant + discordant + ties_left_only)
        * (concordant + discordant + ties_right_only)
    ) ** 0.5
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def kendall_tau_b(left: dict[str, float], right: dict[str, float]) -> float | None:
    return kendall_tau_b_units(
        {alias: weight_units(value) for alias, value in left.items()},
        {alias: weight_units(value) for alias, value in right.items()},
    )
