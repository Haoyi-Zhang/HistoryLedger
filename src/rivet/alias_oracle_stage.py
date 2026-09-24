"""Run one bounded independent alias-oracle verification stage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .boundary_experiments import load_oracle
from .io import atomic_write_json

STAGES = {"low": tuple(range(1, 7)), "cap": (7,)}


def run(root: Path, stage: str) -> dict[str, object]:
    if stage not in STAGES:
        raise ValueError("oracle stage must be low or cap")
    oracle = load_oracle(root / "replayer" / "alias_rank_oracle.py")
    member_dir = root / "results" / "global_alias_oracle"
    members: dict[str, dict[str, int]] = {}
    aggregate = {
        "problems": 0,
        "cases": 0,
        "bound_mismatches": 0,
        "invalid_witnesses": 0,
    }
    for root_count in STAGES[stage]:
        path = member_dir / f"roots-{root_count}.jsonl.gz"
        if not path.is_file():
            raise ValueError(f"missing oracle member: {path.name}")
        result = oracle.check_member(path, root_count)
        members[str(root_count)] = result
        for key in aggregate:
            aggregate[key] += result[key]
    if aggregate["bound_mismatches"] or aggregate["invalid_witnesses"]:
        raise AssertionError(aggregate)
    receipt = {
        "stage": stage,
        "root_counts": list(STAGES[stage]),
        "members": members,
        "aggregate": aggregate,
    }
    member_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(member_dir / f"check-{stage}.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("stage", choices=tuple(STAGES))
    args = parser.parse_args()
    print(json.dumps(run(args.artifact_root, args.stage), sort_keys=True))
