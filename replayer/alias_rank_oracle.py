"""Independent bounded whole-set partition oracle; no scoring-engine imports.

The frozen universe exhausts ternary masses through six roots and binary masses
at the seven-root implementation cap.  Each JSONL problem row contains every
target answer for one mass vector and one declared component partition.  Cases
may be supplied as plain JSONL or deterministic gzip-compressed JSONL.
"""
from __future__ import annotations

import argparse
import gzip
import json
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import TextIO

MAX_ROOTS = 7
MASS_ALPHABETS = {
    1: (1, 2, 3),
    2: (1, 2, 3),
    3: (1, 2, 3),
    4: (1, 2, 3),
    5: (1, 2, 3),
    6: (1, 2, 3),
    7: (1, 2),
}
BELL_COUNTS = {1: 1, 2: 2, 3: 5, 4: 15, 5: 52, 6: 203, 7: 877}
EXPECTED_PROBLEMS_BY_ROOTS = {
    n: (len(MASS_ALPHABETS[n]) ** n) * BELL_COUNTS[n]
    for n in range(1, MAX_ROOTS + 1)
}
EXPECTED_CASES_BY_ROOTS = {
    n: n * EXPECTED_PROBLEMS_BY_ROOTS[n]
    for n in range(1, MAX_ROOTS + 1)
}
EXPECTED_PROBLEMS = sum(EXPECTED_PROBLEMS_BY_ROOTS.values())
EXPECTED_CASES = sum(EXPECTED_CASES_BY_ROOTS.values())


@lru_cache(maxsize=None)
def partitions(n: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Enumerate canonical set partitions as restricted-growth strings.

    Direct products are intentionally different from the incremental-insertion
    producer and from the subset recurrence used by the optimized algorithm.
    """
    if not 1 <= n <= MAX_ROOTS:
        raise ValueError("whole-set oracle admits one through seven roots")
    result: list[tuple[tuple[int, ...], ...]] = []
    for labels in product(range(n), repeat=n):
        maximum = -1
        valid = True
        for label in labels:
            if label > maximum + 1:
                valid = False
                break
            maximum = max(maximum, label)
        if valid:
            result.append(
                tuple(
                    tuple(i for i, label in enumerate(labels) if label == group)
                    for group in range(maximum + 1)
                )
            )
    output = tuple(result)
    if len(output) != BELL_COUNTS[n] or len(output) != len(set(output)):
        raise AssertionError("whole-set partition enumeration changed")
    return output


def _component_signature(components: list[list[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(tuple(sorted(group)) for group in components))


def _component_index_signature(
    components: list[list[str]], roots: tuple[str, ...]
) -> tuple[tuple[int, ...], ...]:
    index = {root: position for position, root in enumerate(roots)}
    try:
        signature = tuple(
            sorted(tuple(sorted(index[label] for label in group)) for group in components)
        )
    except KeyError as error:
        raise ValueError("components contain an unknown root") from error
    if tuple(sorted(position for group in signature for position in group)) != tuple(
        range(len(roots))
    ):
        raise ValueError("components must partition every root")
    return signature


@lru_cache(maxsize=None)
def partition_masks(n: int) -> tuple[tuple[int, ...], ...]:
    """Encode the independently enumerated whole-set partitions as bit masks."""
    return tuple(
        tuple(sum(1 << index for index in block) for block in candidate)
        for candidate in partitions(n)
    )


@lru_cache(maxsize=None)
def admissible_mask_partitions(
    n: int,
    signature: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, ...], ...]:
    """Return mask partitions that refine a declared index-component partition."""
    if tuple(sorted(index for group in signature for index in group)) != tuple(range(n)):
        raise ValueError("components must partition every root")
    group_of = [0] * n
    for group_index, group in enumerate(signature):
        for index in group:
            group_of[index] = group_index
    accepted = []
    for candidate in partition_masks(n):
        valid = True
        for mask in candidate:
            seen_group = -1
            remaining = mask
            while remaining:
                bit = remaining & -remaining
                index = bit.bit_length() - 1
                group = group_of[index]
                if seen_group < 0:
                    seen_group = group
                elif group != seen_group:
                    valid = False
                    break
                remaining ^= bit
            if not valid:
                break
        if valid:
            accepted.append(candidate)
    if not accepted:
        raise AssertionError("every valid component partition has a refinement")
    return tuple(accepted)


def _exact_bounds_prepared(
    weights: tuple[int, ...],
    signature: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, int], ...]:
    """Brute-force every admissible whole-set partition using numeric masks.

    This remains a direct exhaustive partition consumer: it does not use the
    optimizer's component recurrence or best-rank formula.  The bit-mask form
    removes repeated string and dictionary work from the finite oracle only.
    """
    n = len(weights)
    subset_mass = [0] * (1 << n)
    for mask in range(1, 1 << n):
        bit = mask & -mask
        subset_mass[mask] = subset_mass[mask ^ bit] + weights[bit.bit_length() - 1]
    minima = [n + 1] * n
    maxima = [0] * n
    for blocks in admissible_mask_partitions(n, signature):
        masses = [subset_mass[mask] for mask in blocks]
        ranks = [1 + sum(other > mass for other in masses) for mass in masses]
        for mask, rank in zip(blocks, ranks):
            remaining = mask
            while remaining:
                bit = remaining & -remaining
                index = bit.bit_length() - 1
                if rank < minima[index]:
                    minima[index] = rank
                if rank > maxima[index]:
                    maxima[index] = rank
                remaining ^= bit
    if any(best > worst for best, worst in zip(minima, maxima)):
        raise AssertionError("oracle did not encounter a target partition")
    return tuple(zip(minima, maxima))


@lru_cache(maxsize=None)
def admissible_partitions(
    n: int,
    signature: tuple[tuple[str, ...], ...],
) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Return whole-set partitions that refine the declared components."""
    roots = tuple(f"A{i}" for i in range(n))
    group_of = {
        label: group_index
        for group_index, group in enumerate(signature)
        for label in group
    }
    if set(group_of) != set(roots):
        raise ValueError("components must partition every root")
    accepted = []
    for candidate in partitions(n):
        if all(len({group_of[roots[index]] for index in block}) == 1 for block in candidate):
            accepted.append(candidate)
    if not accepted:
        raise AssertionError("every valid component partition has a refinement")
    return tuple(accepted)


def _rank_of_prepared(
    weights: dict[str, int],
    group_of: dict[str, int],
    target: str,
    partition: list[list[str]] | tuple[tuple[str, ...], ...],
) -> int:
    members = [label for block in partition for label in block]
    if len(members) != len(set(members)) or set(members) != set(weights):
        raise ValueError("witness is not a partition of the roots")
    if any(
        not block or len({group_of[label] for label in block}) != 1
        for block in partition
    ):
        raise ValueError("witness crosses a component or contains an empty block")
    masses = [sum(weights[label] for label in block) for block in partition]
    target_mass = next(
        mass for block, mass in zip(partition, masses) if target in block
    )
    return 1 + sum(mass > target_mass for mass in masses)


def rank_of(
    weights: dict[str, int],
    components: list[list[str]],
    target: str,
    partition: list[list[str]] | tuple[tuple[str, ...], ...],
) -> int:
    group_of = {
        label: group
        for group, component in enumerate(components)
        for label in component
    }
    if set(group_of) != set(weights):
        raise ValueError("components do not cover the roots")
    return _rank_of_prepared(weights, group_of, target, partition)


def exact_bounds_all(
    weights: dict[str, int],
    components: list[list[str]],
) -> dict[str, tuple[int, int]]:
    """Brute-force every target over every admissible whole-set partition."""
    roots = tuple(sorted(weights))
    signature = _component_index_signature(components, roots)
    bounds = _exact_bounds_prepared(tuple(weights[root] for root in roots), signature)
    return {root: bounds[index] for index, root in enumerate(roots)}


def exact_bounds(
    weights: dict[str, int],
    components: list[list[str]],
    target: str,
) -> tuple[int, int]:
    return exact_bounds_all(weights, components)[target]


def _validate_answer(answer: object, n: int) -> None:
    if not isinstance(answer, dict):
        raise ValueError("target answer must be an object")
    for which in ("best", "worst"):
        rank = answer.get(which + "_rank")
        if type(rank) is not int or not 1 <= rank <= n:
            raise ValueError("invalid reported rank")
        partition = answer.get(which + "_partition")
        if not isinstance(partition, list):
            raise ValueError("reported witness must be a partition list")
    transitions = answer.get("subset_transitions")
    if type(transitions) is not int or transitions < 0:
        raise ValueError("invalid transition count")


def _case_key(row: dict) -> tuple:
    """Validate membership in the finite declared oracle universe."""
    weights = row.get("weights")
    if not isinstance(weights, dict) or not 1 <= len(weights) <= MAX_ROOTS:
        raise ValueError("oracle admits one through seven roots")
    n = len(weights)
    roots = [f"A{i}" for i in range(n)]
    alphabet = MASS_ALPHABETS[n]
    if set(weights) != set(roots) or any(
        type(weights[root]) is not int or weights[root] not in alphabet
        for root in roots
    ):
        raise ValueError("case is outside the frozen root or mass alphabet")
    groups = row.get("components")
    if not isinstance(groups, list) or any(
        not isinstance(group, list)
        or not group
        or any(not isinstance(label, str) for label in group)
        for group in groups
    ):
        raise ValueError("components must be nonempty lists of labels")
    members = [label for group in groups for label in group]
    if len(members) != len(set(members)) or set(members) != set(roots):
        raise ValueError("components must partition every root")
    answers = row.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(roots):
        raise ValueError("problem row must report every target exactly once")
    for root in roots:
        _validate_answer(answers[root], n)
    return tuple(weights[root] for root in roots), _component_signature(groups)


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def _scan(
    path: Path,
    expected_problem_counts: dict[int, int],
    expected_case_counts: dict[int, int],
) -> dict[str, int]:
    problem_count = case_count = mismatches = invalid_witnesses = 0
    seen: set[tuple] = set()
    problem_counts = {n: 0 for n in expected_problem_counts}
    case_counts = {n: 0 for n in expected_case_counts}
    try:
        with _open_text(path) as stream:
            for line in stream:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("case must be an object")
                key = _case_key(row)
                if key in seen:
                    raise ValueError("duplicate oracle problem")
                seen.add(key)
                weight_tuple, label_signature = key
                n = len(row["weights"])
                if n not in expected_problem_counts:
                    raise ValueError("oracle member contains an unexpected root count")
                problem_count += 1
                if problem_count > sum(expected_problem_counts.values()):
                    raise ValueError("oracle problem limit exceeded")
                problem_counts[n] += 1
                case_counts[n] += n
                case_count += n

                roots = tuple(f"A{i}" for i in range(n))
                index_signature = tuple(
                    tuple(int(label[1:]) for label in group)
                    for group in label_signature
                )
                prepared_bounds = _exact_bounds_prepared(weight_tuple, index_signature)
                actual = {root: prepared_bounds[index] for index, root in enumerate(roots)}
                group_of = {
                    label: group
                    for group, component in enumerate(row["components"])
                    for label in component
                }
                for target, answer in row["answers"].items():
                    if actual[target] != (answer["best_rank"], answer["worst_rank"]):
                        mismatches += 1
                    for which in ("best", "worst"):
                        try:
                            rank = _rank_of_prepared(
                                row["weights"], group_of, target,
                                answer[which + "_partition"],
                            )
                            invalid_witnesses += int(rank != answer[which + "_rank"])
                        except (ValueError, KeyError, TypeError, StopIteration):
                            invalid_witnesses += 1
    except (EOFError, gzip.BadGzipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("corrupt oracle member") from exc
    if problem_counts != expected_problem_counts or case_counts != expected_case_counts:
        raise ValueError("incomplete oracle case coverage")
    return {
        "problems": problem_count,
        "cases": case_count,
        "bound_mismatches": mismatches,
        "invalid_witnesses": invalid_witnesses,
    }


def check_member(path: Path, root_count: int) -> dict[str, int]:
    if root_count not in EXPECTED_PROBLEMS_BY_ROOTS:
        raise ValueError("root count must be from one through seven")
    result = _scan(
        path,
        {root_count: EXPECTED_PROBLEMS_BY_ROOTS[root_count]},
        {root_count: EXPECTED_CASES_BY_ROOTS[root_count]},
    )
    return {"root_count": root_count, **result}


def check(path: Path) -> dict[str, int]:
    return _scan(path, EXPECTED_PROBLEMS_BY_ROOTS, EXPECTED_CASES_BY_ROOTS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--root-count", type=int)
    args = parser.parse_args()
    result = (
        check_member(args.results, args.root_count)
        if args.root_count is not None
        else check(args.results)
    )
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(
        0
        if not result["bound_mismatches"] and not result["invalid_witnesses"]
        else 1
    )
