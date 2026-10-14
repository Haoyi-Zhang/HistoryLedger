"""Fresh portable diagnostic evidence; never rewrite a retained result tree."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from rivet.diagnostic_experiments import csv_text, same_information_rows
from rivet.boundary_experiments import load_oracle
from rivet.global_aliases import global_rank_diagnostics_units
from rivet.influence import strict_winner_flip_radius
from rivet.io import atomic_write_json, atomic_write_text, load_histories
from rivet.leadership import leadership_diagnostic
from test_leadership import brute_radii, consumer, fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.relative_to((ROOT / "results").resolve())
    if out.exists():
        raise SystemExit("output directory exists; choose a fresh name")
    out.mkdir(parents=True)
    started = time.perf_counter()
    receipt = {"status": "FAIL", "utc_time": datetime.now(timezone.utc).isoformat(),
               "command": [sys.executable, "-B", "scripts/validate_leadership.py", *sys.argv[1:]],
               "environment": {"python": sys.version, "platform": platform.platform(), "workers": 1},
               "scope": "seven authored oracle fixtures, 40 retained normalized histories, 400 existing transformed endpoints; no upstream execution or broad native evaluation"}
    try:
        stream = io.StringIO()
        tests = unittest.defaultTestLoader.loadTestsFromName("test_leadership")
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
        atomic_write_text(out / "tests.txt", stream.getvalue())
        receipt["tests"] = {"run": result.testsRun, "failures": len(result.failures),
                            "errors": len(result.errors), "skipped": len(result.skipped)}
        if not result.wasSuccessful() or result.skipped:
            raise RuntimeError("focused tests did not all execute successfully")
        records, controls = [], []
        for case in fixtures():
            record = leadership_diagnostic(case)
            oracle, assignments = brute_radii(record["events"])
            checked = consumer.verify(record)
            assert checked["radii"] == oracle == consumer.direct_radii(record["events"])
            controls.append({"raw_input": case.to_dict(), "diagnostic": record,
                             "oracle": oracle, "assignments_examined": assignments, "replay": checked})
        atomic_write_text(out / "owned-controls.json", json.dumps(controls, indent=2, sort_keys=True, default=str) + "\n")
        alias_oracle = load_oracle(ROOT / "replayer/alias_rank_oracle.py")
        alias_controls = []
        for weights, groups in [
                ({"T": 5, "B": 3, "C": 3}, [("T",), ("B", "C")]),
                ({"T": 6, "B": 3, "C": 3}, [("T",), ("B", "C")]),
                ({"A": 0, "B": 0, "C": 1}, [("A", "B"), ("C",)]),
                ({"A": 4, "B": 1, "C": 3, "D": 3}, [("A", "B"), ("C", "D")])]:
            optimized = global_rank_diagnostics_units(weights, groups).intervals
            expected = alias_oracle.exact_bounds_all(weights, groups)
            assert optimized == expected
            alias_controls.append({"weights": weights, "components": groups,
                                   "rank_only": optimized, "whole_set_oracle": expected})
        atomic_write_json(out / "identity-controls.json", alias_controls)
        with (ROOT / "results/winner_flip_radius.csv").open(newline="", encoding="utf-8") as handle:
            retained = {row["history_id"]: row for row in csv.DictReader(handle)}
        for case in load_histories(ROOT / "data/public_windows.json"):
            record = leadership_diagnostic(case)
            checked = consumer.verify(record)
            direct = consumer.direct_radii(record["events"])
            assert checked["radii"] == direct
            old = strict_winner_flip_radius(case)
            query = record["queries"]["strict_overtake"]
            assert query["minimum_relabels"] == old.minimum_relabels == int(retained[case.history_id]["minimum_relabels"])
            assert query["challenger"] == old.challenger == retained[case.history_id]["challenger"]
            assert query["witness_atoms"] == list(old.witness_atoms) == retained[case.history_id]["witness_atoms"].split(";")
            records.append(record)
        atomic_write_text(out / "public-diagnostics.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
        same = same_information_rows(ROOT)
        text = csv_text(same)
        assert text == (ROOT / "results/same_information.csv").read_text(encoding="utf-8")
        atomic_write_text(out / "same-information.csv", text)
        certified = [row for row in same if row["certificate_valid"]]
        receipt.update(status="PASS", oracle_fixtures=len(controls),
                       oracle_assignments=sum(row["assignments_examined"] for row in controls),
                       identity_controls=len(alias_controls), identity_targets=sum(len(row["weights"]) for row in alias_controls),
                       histories=len(records), positive_events=sum(len(r["events"]) for r in records),
                       same_information_endpoints=len(same), same_information_certified_pairs=len(certified),
                       score_and_bucket_equalities=sum(r["ledger_score_preserved"] and r["attribution_buckets_preserved"] for r in certified),
                       strict_radius_distribution={str(k):sum(r["queries"]["strict_overtake"]["minimum_relabels"] == k for r in records)
                                                   for k in sorted({r["queries"]["strict_overtake"]["minimum_relabels"] for r in records})},
                       loss_radius_distribution={str(k):sum(r["queries"]["loss_of_unique"]["minimum_relabels"] == k for r in records)
                                                 for k in sorted({r["queries"]["loss_of_unique"]["minimum_relabels"] for r in records})},
                       tie_before_strict_histories=sum(r["queries"]["loss_of_unique"]["minimum_relabels"] < r["queries"]["strict_overtake"]["minimum_relabels"] for r in records),
                       historical_outputs_overwritten=False, upstream_programs_executed=False)
        tracked = ["src/rivet/leadership.py", "replayer/leadership.py", "scripts/validate_leadership.py", "tests/test_leadership.py",
                   "replayer/alias_rank_oracle.py", "src/rivet/global_aliases.py",
                   "src/rivet/influence.py", "src/rivet/diagnostic_experiments.py", "src/rivet/provenance_baseline.py",
                   "src/rivet/score.py", "src/rivet/aliases.py", "src/rivet/certificate.py", "src/rivet/model.py",
                   "src/rivet/numeric.py", "src/rivet/transforms.py", "src/rivet/io.py", "src/rivet/__init__.py",
                   "src/rivet/boundary_experiments.py", "src/rivet/extract_public.py", "data/public_windows.json",
                   "results/winner_flip_radius.csv", "results/same_information.csv"]
        receipt["source_and_input_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in tracked}
    except Exception as error:
        receipt["error"] = repr(error)
        raise
    finally:
        receipt["elapsed_seconds"] = time.perf_counter() - started
        atomic_write_json(out / "receipt.json", receipt)
    print(json.dumps({key:receipt[key] for key in ("status", "tests", "oracle_fixtures", "histories", "same_information_certified_pairs", "strict_radius_distribution", "loss_radius_distribution", "tie_before_strict_histories")}))


if __name__ == "__main__":
    main()
