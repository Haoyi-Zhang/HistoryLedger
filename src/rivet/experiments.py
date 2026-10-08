from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import replace
from itertools import product
from pathlib import Path
from typing import Any, Iterable

from .aliases import exact_rank_interval_units
from .certificate import certify_rewrite
from .influence import rank_influence, strict_winner_flip_radius
from .io import atomic_output_path, atomic_write_json, load_histories
from .model import Atom, Commit, History
from .numeric import (
    format_units,
    format_weight,
    sum_weight_units,
    sum_weights,
    units_to_weight,
    weight_units,
)
from .score import (
    analyze_history,
    baseline_scores,
    kendall_tau_b,
    kendall_tau_b_units,
    normalized_l1,
    normalized_l1_units,
    top_alias,
    top_alias_units,
)
from .transforms import (
    add_cosmetic_padding,
    add_empty_commits,
    move_entities,
    rename_event_identifiers,
    reorder_independent,
    split_alias_ambiguous,
    split_alias_certified,
    split_commits,
    squash_cross_origin,
    squash_pairs,
)

BASELINES = (
    "commit_count",
    "line_count",
    "token_count",
    "structural_no_origin",
    "entity_degree",
)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty result {path}")
    columns = sorted({column for row in rows for column in row})
    with atomic_output_path(path) as temporary:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in columns})


def score_equal(
    left: dict[str, float],
    right: dict[str, float],
    tolerance: float | None = None,
) -> bool:
    if set(left) != set(right):
        return False
    if tolerance is None:
        return all(left[key] == right[key] for key in left)
    return all(
        math.isclose(left[key], right[key], rel_tol=tolerance, abs_tol=tolerance)
        for key in left
    )


def component_total(history: History, analysis_scores: dict[str, float]) -> tuple[str | None, float | None]:
    target = history.metadata.get("alias_target")
    children = history.metadata.get("alias_children")
    if not target or not children:
        return None, None
    child_total = sum_weights(analysis_scores.get(child, 0.0) for child in children)
    return str(target), child_total


def public_evaluation(histories: list[History]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    engine_times: list[dict[str, Any]] = []
    for history in histories:
        start = time.perf_counter()
        original_analysis = analyze_history(history)
        original_elapsed = (time.perf_counter() - start) * 1000.0
        if original_analysis.status != "CERTIFIED":
            raise AssertionError(f"original history not certified: {history.history_id}")
        engine_times.append(
            {
                "history_id": history.history_id,
                "surface": "engine-original",
                "milliseconds": original_elapsed,
                "events": len(history.atoms(include_cosmetic=False)),
            }
        )
        renamed_history, renamed_map = rename_event_identifiers(history)
        transformations = {
            "split": (split_commits(history), None),
            "squash-certified": (squash_pairs(history, retain_origins=True), None),
            "reorder-independent": (reorder_independent(history), None),
            "formatting": (add_cosmetic_padding(history), None),
            "empty-commit-padding": (add_empty_commits(history), None),
            "file-move": (move_entities(history), None),
            "event-map": (renamed_history, renamed_map),
            "alias-certified": (split_alias_certified(history), None),
            "alias-ambiguous": (split_alias_ambiguous(history), None),
            "squash-without-origin": (
                squash_cross_origin(history, retain_origins=False),
                None,
            ),
        }
        for name, (transformed, event_map) in transformations.items():
            cert_start = time.perf_counter()
            certificate = certify_rewrite(history, transformed, event_map=event_map)
            analysis = analyze_history(transformed)
            elapsed = (time.perf_counter() - cert_start) * 1000.0
            engine_times.append(
                {
                    "history_id": history.history_id,
                    "surface": name,
                    "milliseconds": elapsed,
                    "events": len(transformed.atoms(include_cosmetic=False)),
                }
            )
            rivet_equal = original_analysis.score_units == analysis.score_units
            mass_conserved = (
                sum(original_analysis.score_units.values())
                == sum(analysis.score_units.values())
            )
            point_ranking_available = analysis.status == "CERTIFIED"
            rows.append(
                {
                    "history_id": history.history_id,
                    "transformation": name,
                    "method": "rivet",
                    "certificate_valid": int(certificate.valid),
                    "status": analysis.status,
                    "score_equal": int(rivet_equal),
                    "mass_conserved": int(mass_conserved),
                    "top_changed": "" if not point_ranking_available else int(
                        top_alias_units(original_analysis.score_units)
                        != top_alias_units(analysis.score_units)
                    ),
                    "kendall_tau_b": "" if not point_ranking_available else kendall_tau_b_units(
                        original_analysis.score_units, analysis.score_units
                    ),
                    "normalized_l1": "" if not point_ranking_available else normalized_l1_units(
                        original_analysis.score_units, analysis.score_units
                    ),
                    "unresolved_atoms": len(certificate.unresolved_atoms),
                }
            )
            for method in BASELINES:
                original_scores = baseline_scores(history, method)
                transformed_scores = baseline_scores(transformed, method)
                rows.append(
                    {
                        "history_id": history.history_id,
                        "transformation": name,
                        "method": method,
                        "certificate_valid": int(certificate.valid),
                        "status": "SCORED",
                        "score_equal": int(
                            score_equal(original_scores, transformed_scores, tolerance=1e-9)
                        ),
                        "mass_conserved": int(math.isclose(
                            sum_weights(original_scores.values()),
                            sum_weights(transformed_scores.values()),
                            rel_tol=1e-9,
                            abs_tol=1e-9,
                        )),
                        "top_changed": int(top_alias(original_scores) != top_alias(transformed_scores)),
                        "kendall_tau_b": kendall_tau_b(original_scores, transformed_scores),
                        "normalized_l1": normalized_l1(original_scores, transformed_scores),
                        "unresolved_atoms": len(certificate.unresolved_atoms),
                    }
                )
    return rows, engine_times


def summarize_public(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(str(row["transformation"]), str(row["method"]))].append(row)
    summary: list[dict[str, Any]] = []
    for (transformation, method), members in sorted(groups.items()):
        numeric_tau = [float(row["kendall_tau_b"]) for row in members
                       if row["kendall_tau_b"] not in ("", None)]
        tau_unavailable = sum(
            str(row["status"]) not in {"CERTIFIED", "SCORED"} for row in members
        )
        numeric_l1 = [float(row["normalized_l1"]) for row in members if row["normalized_l1"] != ""]
        numeric_top = [int(row["top_changed"]) for row in members if row["top_changed"] != ""]
        summary.append(
            {
                "transformation": transformation,
                "method": method,
                "histories": len(members),
                "certificate_rate": sum(int(row["certificate_valid"]) for row in members) / len(members),
                "score_equality_rate": sum(int(row["score_equal"]) for row in members) / len(members),
                "mass_conservation_rate": sum(int(row["mass_conserved"]) for row in members) / len(members),
                "top_change_rate": statistics.mean(numeric_top) if numeric_top else "",
                "mean_kendall_tau_b": statistics.mean(numeric_tau) if numeric_tau else "",
                "tau_b_defined_count": len(numeric_tau),
                "tau_b_undefined_count": len(members) - tau_unavailable - len(numeric_tau),
                "tau_b_unavailable_count": tau_unavailable,
                "mean_normalized_l1": statistics.mean(numeric_l1) if numeric_l1 else "",
                "abstention_rate": sum(
                    str(row["status"]).startswith("ABSTAIN")
                    or str(row["status"]).startswith("PARTIAL")
                    for row in members
                )
                / len(members),
            }
        )
    return summary


def influence_evaluation(histories: list[History]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for history in histories:
        analysis = analyze_history(history)
        actor = top_alias_units(analysis.score_units)
        if actor is None:
            continue
        total_units = sum(analysis.score_units.values())
        original_rank = 1 + sum(
            value > analysis.score_units[actor]
            for name, value in analysis.score_units.items()
            if name != actor
        )
        for budget in (0, 1, 2, 3, 5):
            bound = rank_influence(history, actor, budget)
            rows.append(
                {
                    "history_id": history.history_id,
                    "actor": actor,
                    "budget": budget,
                    "original_rank": original_rank,
                    "best_rank_bound": bound.best_rank,
                    "worst_rank_bound": bound.worst_rank,
                    "original_score": bound.score.original,
                    "minimum_score": bound.score.minimum,
                    "maximum_score": bound.score.maximum,
                    "removable_mass": bound.score.removable_mass,
                    "acquirable_mass": bound.score.acquirable_mass,
                    "score_span_fraction": (
                        (bound.score.maximum_units - bound.score.minimum_units)
                        / total_units
                        if total_units
                        else 0.0
                    ),
                }
            )
    return rows


def _random_positive_partition(
    total_units: int,
    parts: int,
    rng: random.Random,
) -> tuple[int, ...]:
    """Split exact units into positive integer parts without mass drift."""
    if isinstance(total_units, bool) or not isinstance(total_units, int) or total_units < 1:
        raise ValueError("total_units must be a positive integer")
    if isinstance(parts, bool) or not isinstance(parts, int) or parts < 1:
        raise ValueError("parts must be a positive integer")
    if total_units < parts:
        raise ValueError("positive partition has more parts than available units")
    if parts == 1:
        return (total_units,)
    cuts = sorted(rng.sample(range(1, total_units), parts - 1))
    boundaries = (0, *cuts, total_units)
    return tuple(boundaries[index + 1] - boundaries[index] for index in range(parts))


def winner_flip_evaluation(histories: list[History]) -> list[dict[str, Any]]:
    """Measure exact strict-winner fragility for every resolved public history."""
    rows: list[dict[str, Any]] = []
    for history in histories:
        analysis = analyze_history(history)
        result = strict_winner_flip_radius(history)
        event_count = len(history.atoms(include_cosmetic=False))
        if result.minimum_relabels is None or result.challenger is None:
            rows.append(
                {
                    "history_id": history.history_id,
                    "actor_classes": len(analysis.score_units),
                    "structural_events": event_count,
                    "leader": result.leader,
                    "leader_score": result.leader_score,
                    "minimum_relabels": "",
                    "radius_fraction": "",
                    "challenger": "",
                    "initial_gap": "",
                    "winning_margin": "",
                    "witness_atoms": "",
                }
            )
            continue
        rows.append(
            {
                "history_id": history.history_id,
                "actor_classes": len(analysis.score_units),
                "structural_events": event_count,
                "leader": result.leader,
                "leader_score": result.leader_score,
                "minimum_relabels": result.minimum_relabels,
                "radius_fraction": result.minimum_relabels / event_count,
                "challenger": result.challenger,
                "initial_gap": result.initial_gap,
                "winning_margin": result.winning_margin,
                "witness_atoms": ";".join(result.witness_atoms),
            }
        )
    return rows


def _replace_atom(
    history: History,
    atom_id: str,
    replacement: Atom | None,
) -> History:
    commits: list[Commit] = []
    found = False
    for commit in history.commits:
        atoms: list[Atom] = []
        for atom in commit.atoms:
            if atom.atom_id == atom_id:
                if found:
                    raise AssertionError("mutation target is not unique")
                found = True
                if replacement is not None:
                    atoms.append(replacement)
            else:
                atoms.append(atom)
        commits.append(replace(commit, atoms=tuple(atoms)))
    if not found:
        raise AssertionError("mutation target is absent")
    return replace(history, commits=tuple(commits))


def certificate_mutation_evaluation(histories: list[History]) -> list[dict[str, Any]]:
    """Inject one obligation violation at a time into each public certificate."""
    rows: list[dict[str, Any]] = []
    for history in histories:
        analysis = analyze_history(history)
        atoms = history.atoms(include_cosmetic=False)
        if not atoms:
            raise AssertionError("mutation campaign requires a structural event")
        target = atoms[0]
        actors = tuple(sorted(analysis.score_units))
        if len(actors) < 2 or target.origin is None:
            raise AssertionError("mutation campaign requires two resolved actor classes")
        alternate_origin = next(actor for actor in actors if actor != target.origin)

        added = Atom(
            atom_id=f"injected-{history.history_id}",
            entity=target.entity,
            weight=target.weight,
            origin=target.origin,
            raw_lines=target.raw_lines,
            raw_tokens=target.raw_tokens,
        )
        first_commit = history.commits[0]
        mutations = {
            "missing-event": _replace_atom(history, target.atom_id, None),
            "extra-event": replace(
                history,
                commits=(replace(first_commit, atoms=first_commit.atoms + (added,)),)
                + history.commits[1:],
            ),
            "one-quantum-weight": _replace_atom(
                history,
                target.atom_id,
                replace(
                    target,
                    weight=format_units(weight_units(target.weight) + 1),  # type: ignore[arg-type]
                ),
            ),
            "origin-substitution": _replace_atom(
                history,
                target.atom_id,
                replace(target, origin=alternate_origin),
            ),
            "undeclared-entity-substitution": _replace_atom(
                history,
                target.atom_id,
                replace(target, entity=f"tampered-{target.entity}"),
            ),
            "cross-history-alias-merge": replace(
                history,
                must_link=history.must_link + ((actors[0], actors[1]),),
            ),
            "may-link-regime-change": replace(
                history,
                may_link=history.may_link + ((actors[0], actors[1]),),
            ),
        }
        for fault, mutated in mutations.items():
            certificate = certify_rewrite(history, mutated)
            rows.append(
                {
                    "history_id": history.history_id,
                    "fault": fault,
                    "detected": int(not certificate.valid),
                    "malformed": int(certificate.malformed),
                    "diagnostic": " | ".join(certificate.reasons),
                }
            )
    return rows


def alias_sensitivity(histories: list[History], trials_per_size: int = 80) -> list[dict[str, Any]]:
    rng = random.Random("rivet-alias-study")
    source_score_units = [analyze_history(history).score_units for history in histories]
    rows: list[dict[str, Any]] = []
    for component_size in range(2, 8):
        for trial in range(trials_per_size):
            base = dict(source_score_units[trial % len(source_score_units)])
            target = min(base, key=lambda actor: (-base[actor], actor))
            target_units = base.pop(target)
            aliases = tuple(f"{target}-s{index + 1}" for index in range(component_size))
            split_units = _random_positive_partition(target_units, component_size, rng)
            scores = dict(base)
            scores.update(zip(aliases, split_units))
            if sum(split_units) != target_units:
                raise AssertionError("alias partition failed to conserve exact score mass")
            anchor = aliases[0]
            best, worst, resolutions = exact_rank_interval_units(scores, aliases, anchor)
            rows.append(
                {
                    "component_size": component_size,
                    "trial": trial + 1,
                    "outside_actors": len(base),
                    "anchor_share": split_units[0] / target_units,
                    "anchor_score": units_to_weight(split_units[0]),
                    "anchor_score_units": split_units[0],
                    "best_rank": best,
                    "worst_rank": worst,
                    "rank_width": worst - best,
                    "resolutions": resolutions,
                    "component_score": units_to_weight(target_units),
                    "component_score_units": target_units,
                    "partition_total_units": sum(split_units),
                }
            )
    return rows


def compositions(length: int) -> Iterable[tuple[int, ...]]:
    if length == 0:
        yield tuple()
        return
    for mask in range(1 << max(0, length - 1)):
        parts: list[int] = []
        current = 1
        for index in range(length - 1):
            if mask & (1 << index):
                parts.append(current)
                current = 1
            else:
                current += 1
        parts.append(current)
        yield tuple(parts)


def tiny_history(actors: tuple[str, ...], weights: tuple[int, ...], parts: tuple[int, ...], serial: int) -> History | None:
    commits: list[Commit] = []
    cursor = 0
    previous: str | None = None
    for commit_index, size in enumerate(parts, 1):
        block_actors = actors[cursor : cursor + size]
        if len(set(block_actors)) != 1:
            return None
        alias = block_actors[0]
        atoms = tuple(
            Atom(
                atom_id=f"E{cursor + offset + 1:02d}",
                entity=f"F{(cursor + offset) % 3 + 1}",
                weight=float(weights[cursor + offset]),
                origin=alias,
                raw_lines=weights[cursor + offset],
                raw_tokens=weights[cursor + offset],
            )
            for offset in range(size)
        )
        commit_id = f"C{commit_index:02d}"
        commits.append(
            Commit(commit_id, alias, atoms, (previous,) if previous is not None else tuple())
        )
        previous = commit_id
        cursor += size
    return History(f"tiny-{serial:06d}", tuple(commits))


def exhaustive_tiny(max_atoms: int = 4) -> dict[str, Any]:
    actors_domain = ("A", "B", "C")
    obligations = 0
    histories = 0
    certified_failures = 0
    origin_abstention_failures = 0
    winner_flip_oracle_cases = 0
    winner_flip_oracle_failures = 0
    baseline_counterexamples = defaultdict(int)
    serial = 0
    transformations = {
        "split": lambda h: (split_commits(h), None),
        "squash-certified": lambda h: (squash_pairs(h, retain_origins=True), None),
        "reorder-independent": lambda h: (reorder_independent(h), None),
        "formatting": lambda h: (add_cosmetic_padding(h), None),
        "empty-commit-padding": lambda h: (add_empty_commits(h), None),
        "file-move": lambda h: (move_entities(h), None),
        "event-map": rename_event_identifiers,
    }
    for atom_count in range(1, max_atoms + 1):
        for actors in product(actors_domain, repeat=atom_count):
            for weights in product((1, 2), repeat=atom_count):
                for parts in compositions(atom_count):
                    serial += 1
                    history = tiny_history(actors, weights, parts, serial)
                    if history is None:
                        continue
                    histories += 1
                    original = analyze_history(history)
                    for name, transform in transformations.items():
                        obligations += 1
                        changed, event_map = transform(history)
                        certificate = certify_rewrite(
                            history, changed, event_map=event_map
                        )
                        result = analyze_history(changed)
                        if not certificate.valid or original.score_units != result.score_units:
                            certified_failures += 1
                        for method in BASELINES:
                            if not score_equal(
                                baseline_scores(history, method),
                                baseline_scores(changed, method),
                                tolerance=1e-9,
                            ):
                                baseline_counterexamples[f"{name}:{method}"] += 1
                    if len(set(actors)) >= 2:
                        obligations += 1
                        lost = squash_cross_origin(history, retain_origins=False)
                        if analyze_history(lost).status != "ABSTAIN_ORIGIN":
                            origin_abstention_failures += 1

                    actor_units = original.score_units
                    if len(actor_units) >= 2:
                        maximum = max(actor_units.values())
                        leaders = [
                            actor for actor, score in actor_units.items() if score == maximum
                        ]
                        if len(leaders) == 1:
                            winner_flip_oracle_cases += 1
                            leader = leaders[0]
                            computed = strict_winner_flip_radius(history).minimum_relabels
                            event_list = history.atoms(include_cosmetic=False)
                            destinations = tuple(sorted(actor_units))
                            brute: int | None = None
                            for reassignment in product(destinations, repeat=len(event_list)):
                                changed = sum(
                                    destination != atom.origin
                                    for atom, destination in zip(event_list, reassignment)
                                )
                                if brute is not None and changed >= brute:
                                    continue
                                candidate = {actor: 0 for actor in destinations}
                                for atom, destination in zip(event_list, reassignment):
                                    candidate[destination] += weight_units(atom.weight)
                                if any(
                                    candidate[actor] > candidate[leader]
                                    for actor in destinations
                                    if actor != leader
                                ):
                                    brute = changed
                            if brute != computed:
                                winner_flip_oracle_failures += 1
    return {
        "max_atoms": max_atoms,
        "histories": histories,
        "obligations": obligations,
        "certified_failures": certified_failures,
        "origin_abstention_failures": origin_abstention_failures,
        "winner_flip_oracle_cases": winner_flip_oracle_cases,
        "winner_flip_oracle_failures": winner_flip_oracle_failures,
        "baseline_counterexamples": dict(sorted(baseline_counterexamples.items())),
    }


def export_ledger(histories: list[History], ledger_path: Path, expected_path: Path) -> None:
    """Export exact scalar totals for histories whose actor classes are singletons.

    Class declarations are not represented by this CSV format. Refuse them
    before writing either output rather than silently fragmenting class scores.
    """
    for history in histories:
        if history.must_link or history.may_link:
            raise ValueError("scalar ledger requires singleton actor classes without alias declarations")
    rows: list[dict[str, Any]] = []
    expected_rows: list[list[Any]] = []
    score_accumulator: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for history in histories:
        for atom in history.atoms():
            row = {
                "history_id": history.history_id,
                "atom_id": atom.atom_id,
                "entity": atom.entity,
                "weight": format_weight(atom.weight),
                "origin": atom.origin or "",
                "kind": atom.kind,
            }
            rows.append(row)
            if atom.kind != "cosmetic" and atom.origin:
                score_accumulator[history.history_id][atom.origin].append(atom.weight)
            expected_rows.append(
                [
                    history.history_id,
                    atom.atom_id,
                    atom.entity,
                    format_weight(atom.weight),
                    atom.origin or "",
                    atom.kind,
                ]
            )
    with atomic_output_path(ledger_path) as temporary:
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("history_id", "atom_id", "entity", "weight", "origin", "kind"),
            )
            writer.writeheader()
            writer.writerows(rows)
    scores = {
        history_id: {
            alias: format_units(sum_weight_units(values))
            for alias, values in sorted(history_scores.items())
        }
        for history_id, history_scores in sorted(score_accumulator.items())
    }
    expected = {"rows": sorted(expected_rows), "scores": scores}
    atomic_write_json(expected_path, expected)


def replayer_command(replayer: Path, ledger: Path, expected: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(replayer), str(ledger), "--expected", str(expected)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def mutate_rows(rows: list[dict[str, str]], fault: str) -> list[dict[str, str]]:
    changed = [dict(row) for row in rows]
    target_index = next(index for index, row in enumerate(changed) if row["kind"] != "cosmetic")
    target = changed[target_index]
    if fault == "drop":
        del changed[target_index]
    elif fault == "duplicate":
        changed.insert(target_index, dict(target))
    elif fault == "weight":
        target["weight"] = str(float(target["weight"]) + 1.0)
    elif fault == "origin":
        target["origin"] = target["origin"] + "-other"
    elif fault == "missing-origin":
        target["origin"] = ""
    elif fault == "entity":
        target["entity"] = target["entity"] + "-moved"
    elif fault == "extra":
        extra = dict(target)
        extra["atom_id"] = extra["atom_id"] + "-extra"
        changed.append(extra)
    else:
        raise ValueError(fault)
    return changed


def replay_validation(
    ledger_path: Path, expected_path: Path, replayer: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with ledger_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = handle  # keep type checkers quiet about scope
    baseline_times: list[dict[str, Any]] = []
    start = time.perf_counter()
    baseline = replayer_command(replayer, ledger_path, expected_path)
    elapsed = (time.perf_counter() - start) * 1000.0
    baseline_times.append(
        {
            "history_id": "all-public",
            "surface": "independent-replayer",
            "milliseconds": elapsed,
            "events": len(rows),
        }
    )
    if baseline.returncode != 0:
        raise AssertionError(baseline.stdout + baseline.stderr)

    results: list[dict[str, Any]] = []
    faults = ("drop", "duplicate", "weight", "origin", "missing-origin", "entity", "extra")
    with tempfile.TemporaryDirectory(prefix="rivet-replay-") as temp_dir:
        temp = Path(temp_dir)
        for fault in faults:
            mutated = mutate_rows(rows, fault)
            mutated_path = temp / f"{fault}.csv"
            with mutated_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(mutated)
            completed = replayer_command(replayer, mutated_path, expected_path)
            payload = json.loads(completed.stdout)
            results.append(
                {
                    "fault": fault,
                    "detected": int(completed.returncode != 0 and payload["status"] == "FAIL"),
                    "diagnostic_count": len(payload["errors"]),
                    "first_diagnostic": payload["errors"][0] if payload["errors"] else "",
                }
            )
    return results, baseline_times


def handcrafted_witnesses() -> list[dict[str, Any]]:
    # Witnesses are compact constructive examples rather than claims about
    # minimum size outside the stated baseline and transformation.
    return [
        {
            "name": "cross-origin squash erases attribution",
            "actors": 2,
            "structural_events": 2,
            "commits_before": 2,
            "commits_after": 1,
            "result": "origin-aware analysis abstains; observed history admits two incompatible attributions",
        },
        {
            "name": "commit-count reversal under splitting",
            "actors": 2,
            "structural_events": 5,
            "commits_before": 3,
            "commits_after": 5,
            "result": "one actor changes from one to three commits and overtakes an actor with two commits",
        },
        {
            "name": "line-count reversal under formatting",
            "actors": 2,
            "structural_events": 2,
            "commits_before": 2,
            "commits_after": 2,
            "result": "a zero-weight cosmetic edit increases raw changed lines enough to reverse the baseline",
        },
        {
            "name": "alias fragmentation hides the leading actor",
            "actors": 2,
            "structural_events": 3,
            "commits_before": 3,
            "commits_after": 3,
            "result": "the leading actor is split into two unresolved aliases; individual rank is uncertifiable",
        },
    ]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("--replayer", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument(
        "--measure-runtime",
        action="store_true",
        help="write environment-sensitive timing diagnostics; omitted by default",
    )
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    histories = load_histories(args.data)

    public_rows, engine_times = public_evaluation(histories)
    public_summary = summarize_public(public_rows)
    alias_rows = alias_sensitivity(histories)
    influence_rows = influence_evaluation(histories)
    winner_flip_rows = winner_flip_evaluation(histories)
    certificate_mutation_rows = certificate_mutation_evaluation(histories)
    tiny = exhaustive_tiny()
    export_ledger(histories, args.ledger, args.expected)
    replay_rows, replay_times = replay_validation(args.ledger, args.expected, args.replayer)
    runtime_rows = engine_times + replay_times
    witnesses = handcrafted_witnesses()

    write_csv(args.results / "public_transform_results.csv", public_rows)
    write_csv(args.results / "public_summary.csv", public_summary)
    write_csv(args.results / "alias_sensitivity.csv", alias_rows)
    write_csv(args.results / "influence_bounds.csv", influence_rows)
    write_csv(args.results / "winner_flip_radius.csv", winner_flip_rows)
    write_csv(args.results / "certificate_mutations.csv", certificate_mutation_rows)
    write_csv(args.results / "replay_validation.csv", replay_rows)
    runtime_path = args.results / "runtime.csv"
    if args.measure_runtime:
        write_csv(runtime_path, runtime_rows)
    else:
        runtime_path.unlink(missing_ok=True)
    write_csv(args.results / "counterexample_witnesses.csv", witnesses)

    engine_only = [row["milliseconds"] for row in engine_times]
    summary = {
        "public_histories": len(histories),
        "tau_b_defined_count": sum(row["tau_b_defined_count"] for row in public_summary),
        "tau_b_undefined_count": sum(row["tau_b_undefined_count"] for row in public_summary),
        "tau_b_unavailable_count": sum(row["tau_b_unavailable_count"] for row in public_summary),
        "public_commits": sum(len(history.commits) for history in histories),
        "public_structural_events": sum(
            len(history.atoms(include_cosmetic=False)) for history in histories
        ),
        "public_actors_median": statistics.median(
            len(analyze_history(history).scores) for history in histories
        ),
        "certified_transform_obligations": sum(
            1
            for row in public_rows
            if row["method"] == "rivet"
            and row["transformation"]
            in {
                "split",
                "squash-certified",
                "reorder-independent",
                "formatting",
                "empty-commit-padding",
                "file-move",
                "event-map",
                "alias-certified",
            }
        ),
        "certified_transform_failures": sum(
            1
            for row in public_rows
            if row["method"] == "rivet"
            and row["transformation"]
            in {
                "split",
                "squash-certified",
                "reorder-independent",
                "formatting",
                "empty-commit-padding",
                "file-move",
                "event-map",
                "alias-certified",
            }
            and not (row["certificate_valid"] and row["score_equal"])
        ),
        "unobserved_squash_abstentions": sum(
            1
            for row in public_rows
            if row["method"] == "rivet"
            and row["transformation"] == "squash-without-origin"
            and row["status"] == "ABSTAIN_ORIGIN"
        ),
        "ambiguous_alias_partial_abstentions": sum(
            1
            for row in public_rows
            if row["method"] == "rivet"
            and row["transformation"] == "alias-ambiguous"
            and row["status"] == "PARTIAL_ALIAS_ABSTENTION"
        ),
        "replay_faults_detected": sum(row["detected"] for row in replay_rows),
        "replay_faults_injected": len(replay_rows),
        "tiny": tiny,
        "alias_trials": len(alias_rows),
        "alias_target_histories": len(histories),
        "alias_target_top_histories": sum(
            str(split_alias_ambiguous(history).metadata["alias_target"])
            == top_alias_units(analyze_history(history).score_units)
            for history in histories
        ),
        "alias_rank_width_median": statistics.median(row["rank_width"] for row in alias_rows),
        "alias_rank_width_p95": percentile([row["rank_width"] for row in alias_rows], 0.95),
        "budget_three_score_span_fraction_median": statistics.median(
            row["score_span_fraction"] for row in influence_rows if row["budget"] == 3
        ),
        "budget_three_worst_rank_bound_median": statistics.median(
            row["worst_rank_bound"] for row in influence_rows if row["budget"] == 3
        ),
        "winner_flip_histories": sum(
            row["minimum_relabels"] != "" for row in winner_flip_rows
        ),
        "winner_flip_one_label": sum(
            row["minimum_relabels"] == 1 for row in winner_flip_rows
        ),
        "winner_flip_radius_median": statistics.median(
            int(row["minimum_relabels"])
            for row in winner_flip_rows
            if row["minimum_relabels"] != ""
        ),
        "winner_flip_radius_p95": percentile(
            [
                float(row["minimum_relabels"])
                for row in winner_flip_rows
                if row["minimum_relabels"] != ""
            ],
            0.95,
        ),
        "winner_flip_radius_maximum": max(
            int(row["minimum_relabels"])
            for row in winner_flip_rows
            if row["minimum_relabels"] != ""
        ),
        "winner_flip_fraction_median": statistics.median(
            float(row["radius_fraction"])
            for row in winner_flip_rows
            if row["radius_fraction"] != ""
        ),
        "certificate_faults_injected": len(certificate_mutation_rows),
        "certificate_faults_detected": sum(
            int(row["detected"]) for row in certificate_mutation_rows
        ),
    }
    if args.measure_runtime:
        summary.update(
            {
                "engine_median_ms": statistics.median(engine_only),
                "engine_p95_ms": percentile(engine_only, 0.95),
                "replayer_ms": replay_times[0]["milliseconds"],
            }
        )
    atomic_write_json(args.results / "experiment_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
