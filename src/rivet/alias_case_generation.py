"""Generate deterministic bounded alias-oracle problem members.

Generation is split into resumable root-count chunks so a clean reproduction
can stay below the execution environment's per-command budget.  The independent
consumer in ``replayer/alias_rank_oracle.py`` performs the exhaustive check.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Iterable

from .boundary_experiments import component_partitions
from .io import atomic_output_path
from .global_aliases import exact_global_rank_intervals_units

MASS_ALPHABETS = {n: (1, 2, 3) for n in range(1, 7)}
MASS_ALPHABETS[7] = (1, 2)


def generate_member(root: Path, root_count: int) -> tuple[Path, int, int]:
    if root_count not in MASS_ALPHABETS:
        raise ValueError("root count must be from one through seven")
    labels = [f"A{i}" for i in range(root_count)]
    member_dir = root / "results" / "global_alias_oracle"
    member_dir.mkdir(parents=True, exist_ok=True)
    path = member_dir / f"roots-{root_count}.jsonl.gz"
    problems = cases = 0
    with atomic_output_path(path) as temporary:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1
            ) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream:
                    for groups in component_partitions(tuple(labels)):
                        components = [list(block) for block in groups]
                        for values in product(MASS_ALPHABETS[root_count], repeat=root_count):
                            weights = dict(zip(labels, values))
                            answers = exact_global_rank_intervals_units(weights, components)
                            row = {
                                "weights": weights,
                                "components": components,
                                "answers": {
                                    target: asdict(answers[target]) for target in labels
                                },
                            }
                            stream.write(
                                json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                            )
                            problems += 1
                            cases += root_count
    return path, problems, cases


def generate_members(root: Path, root_counts: Iterable[int]) -> dict[str, dict[str, int]]:
    counts = tuple(root_counts)
    if not counts or len(counts) != len(set(counts)):
        raise ValueError("root-count chunk must be nonempty and unique")
    result: dict[str, dict[str, int]] = {}
    for root_count in counts:
        path, problems, cases = generate_member(root, root_count)
        result[str(root_count)] = {
            "problems": problems,
            "cases": cases,
            "bytes": path.stat().st_size,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("root_counts", type=int, nargs="+")
    args = parser.parse_args()
    print(json.dumps(generate_members(args.artifact_root, args.root_counts), sort_keys=True))
