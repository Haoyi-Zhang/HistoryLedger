"""Same-information controls and bounded rank diagnostics, offline only.

Prints results as JSON by default. --write regenerates the three result files;
--check recomputes deterministic results and checks retained files. Timings are
optional host observations and are excluded from deterministic comparisons.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import platform
import statistics
import time
from pathlib import Path

from .boundary_experiments import load_oracle
from .certificate import certify_rewrite
from .global_aliases import (
    _max_above_pattern, exact_global_rank_intervals_units,
    global_rank_diagnostics_units,
)
from .io import atomic_write_text, load_histories
from .provenance_baseline import provenance_ledger
from .score import analyze_history
from .transforms import (
    add_cosmetic_padding, add_empty_commits, move_entities,
    rename_event_identifiers, reorder_independent, split_alias_ambiguous,
    split_alias_certified, split_commits, squash_cross_origin, squash_pairs,
)


def same_information_rows(root: Path) -> list[dict]:
    rows = []
    for history in load_histories(root / "data/public_windows.json"):
        original = provenance_ledger(history)
        renamed, event_map = rename_event_identifiers(history)
        variants = {
            "split": (split_commits(history), None),
            "squash-certified": (squash_pairs(history), None),
            "reorder-independent": (reorder_independent(history), None),
            "formatting": (add_cosmetic_padding(history), None),
            "empty-commit-padding": (add_empty_commits(history), None),
            "file-move": (move_entities(history), None),
            "event-map": (renamed, event_map),
            "alias-certified": (split_alias_certified(history), None),
            "alias-ambiguous": (split_alias_ambiguous(history), None),
            "squash-without-origin": (squash_cross_origin(history), None),
        }
        for name, (changed, mapping) in variants.items():
            plain = provenance_ledger(changed)
            main = analyze_history(changed, include_pairwise=False)
            certificate = certify_rewrite(history, changed, event_map=mapping)
            row = {
                "history_id": history.history_id, "transformation": name,
                "certificate_valid": int(certificate.valid),
                "ledger_status": plain.status, "rivet_status": main.status,
                "same_information_score_match": int(plain.score_units == main.score_units),
                "status_match": int(plain.status == main.status),
                "ledger_score_preserved": int(plain.score_units == original.score_units),
                "attribution_buckets_preserved": int(
                    plain.attribution_buckets == original.attribution_buckets),
            }
            if not row["same_information_score_match"] or not row["status_match"]:
                raise AssertionError(row)
            if certificate.valid and not (row["ledger_score_preserved"]
                                          and row["attribution_buckets_preserved"]):
                raise AssertionError(row)
            rows.append(row)
    return rows


def rank_oracle_rows(root: Path) -> list[dict]:
    """Fresh direct finite oracle, not reliance on a previous receipt."""
    oracle = load_oracle(root / "replayer/alias_rank_oracle.py")
    rows = []
    for n in range(1, 8):
        problems = targets = mismatches = 0
        seen = set()
        member = root / f"results/global_alias_oracle/roots-{n}.jsonl.gz"
        with gzip.open(member, "rt", encoding="utf-8") as stream:
            for line in stream:
                case = json.loads(line)
                key = oracle._case_key(case)
                if len(case["weights"]) != n or key in seen:
                    raise AssertionError("duplicate or wrong-domain problem")
                seen.add(key)
                expected = oracle.exact_bounds_all(case["weights"], case["components"])
                diagnostic = global_rank_diagnostics_units(case["weights"], case["components"])
                mismatches += sum(diagnostic.intervals[t] != expected[t] for t in expected)
                problems += 1
                targets += n
        if (problems != oracle.EXPECTED_PROBLEMS_BY_ROOTS[n]
                or targets != oracle.EXPECTED_CASES_BY_ROOTS[n] or mismatches):
            raise AssertionError((n, problems, targets, mismatches))
        rows.append(dict(roots=n, problems=problems, targets=targets,
                         diagnostic_oracle_mismatches=mismatches))
        print(json.dumps({"completed_rank_stratum": rows[-1]}), flush=True)
    return rows


def output_size_rows() -> list[dict]:
    """Controlled repeated-pattern examples; no exhaustive large-root claim."""
    rows = []
    for component_count in (1, 8, 32):
        groups = [tuple(f"G{g:02d}A{i}" for i in range(7))
                  for g in range(component_count)]
        weights = {label: 1 + i % 5 for group in groups for i, label in enumerate(group)}
        full = exact_global_rank_intervals_units(weights, groups)
        compact = global_rank_diagnostics_units(weights, groups)
        if compact.intervals != {t: (v.best_rank, v.worst_rank) for t, v in full.items()}:
            raise AssertionError("rank-only and witness APIs disagree")
        rows.append(dict(
            roots=len(weights), components=component_count,
            maximum_component_size=7,
            witness_root_references=sum(len(block) for v in full.values()
                                        for p in (v.best_partition, v.worst_partition)
                                        for block in p),
            diagnostic_rank_endpoints=2 * len(compact.intervals),
            distinct_mass_patterns=compact.mass_patterns,
            logical_subset_transitions=compact.subset_transitions,
            rank_api_mismatches=0,
        ))
    return rows


def timing_observations(repetitions: int = 7) -> dict:
    observations = []
    for component_count in (1, 8, 32):
        groups = [tuple(f"G{g:02d}A{i}" for i in range(7))
                  for g in range(component_count)]
        weights = {label: 1 + i % 5 for group in groups for i, label in enumerate(group)}
        for cache_mode in ("cold", "warm"):
            samples = {"witness_batch": [], "rank_only": []}
            functions = [("witness_batch", exact_global_rank_intervals_units),
                         ("rank_only", global_rank_diagnostics_units)]
            for repetition in range(repetitions):
                # Alternate order and make each sample's cache state explicit.
                for name, function in functions[::1 if repetition % 2 == 0 else -1]:
                    _max_above_pattern.cache_clear()
                    if cache_mode == "warm":
                        function(weights, groups)
                    start = time.perf_counter_ns()
                    function(weights, groups)
                    samples[name].append(time.perf_counter_ns() - start)
            observations.append({
                "roots": len(weights), "cache": cache_mode,
                "repetitions": repetitions, "raw_nanoseconds": samples,
                "median_nanoseconds": {name: statistics.median(values)
                                       for name, values in samples.items()},
            })
    return {"platform": platform.platform(), "python": platform.python_version(),
            "scope": "controlled repeated-pattern inputs; no corpus scalability estimate",
            "observations": observations}


def csv_text(rows: list[dict]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def run(root: Path, *, include_timings: bool = False) -> dict:
    same = same_information_rows(root)
    oracle = rank_oracle_rows(root)
    sizes = output_size_rows()
    certified = [row for row in same if row["certificate_valid"]]
    summary = {
        "same_information": {
            "comparisons": len(same), "score_matches": sum(r["same_information_score_match"] for r in same),
            "status_matches": sum(r["status_match"] for r in same),
            "certified_pairs": len(certified),
            "ledger_score_equalities": sum(r["ledger_score_preserved"] for r in certified),
            "attribution_bucket_equalities": sum(r["attribution_buckets_preserved"] for r in certified),
            "ledger_origin_abstentions": sum(r["ledger_status"] == "ABSTAIN_ORIGIN" for r in same),
            "ledger_alias_abstentions": sum(r["ledger_status"] == "PARTIAL_ALIAS_ABSTENTION" for r in same),
            "shared_components": ["input validation", "canonical integer-unit convention"],
        },
        "rank_oracle": {"problems": sum(r["problems"] for r in oracle),
                        "targets": sum(r["targets"] for r in oracle),
                        "mismatches": sum(r["diagnostic_oracle_mismatches"] for r in oracle),
                        "strata": oracle},
        "output_size_controls": sizes,
    }
    files = {
        "same_information.csv": csv_text(same),
        "rank_diagnostic_oracle.csv": csv_text(oracle),
        "diagnostic_summary.json": json.dumps(summary, indent=2, sort_keys=True) + "\n",
    }
    result = {"files": files, "summary": summary}
    if include_timings:
        result["timings"] = timing_observations()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--timings", action="store_true")
    args = parser.parse_args()
    result = run(args.artifact_root, include_timings=args.timings)
    for name, content in result["files"].items():
        path = args.artifact_root / "results" / name
        if args.write:
            atomic_write_text(path, content)
        elif args.check and path.read_text(encoding="utf-8") != content:
            raise SystemExit("retained diagnostic result differs: " + name)
    print(json.dumps(result if not args.check else result["summary"], sort_keys=True))
