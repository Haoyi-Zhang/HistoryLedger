from dataclasses import replace
from itertools import product
from pathlib import Path
import unittest

from rivet.boundary_experiments import component_partitions, load_oracle
from rivet.certificate import certify_rewrite
from rivet.diagnostic_experiments import same_information_rows, output_size_rows
from rivet.global_aliases import (
    exact_global_rank_intervals_units, global_rank_diagnostics_units,
)
from rivet.model import Atom, Commit, History
from rivet.provenance_baseline import provenance_ledger
from rivet.score import analyze_history

ROOT = Path(__file__).resolve().parents[1]


class DiagnosticTests(unittest.TestCase):
    def test_same_information_public_pairs(self):
        rows = same_information_rows(ROOT)
        accepted = [row for row in rows if row["certificate_valid"]]
        self.assertEqual(400, len(rows))
        self.assertEqual(320, len(accepted))
        self.assertTrue(all(r["ledger_score_preserved"] and r["attribution_buckets_preserved"]
                            for r in accepted))
        self.assertTrue(all(r["same_information_score_match"] and r["status_match"] for r in rows))

    def test_same_buckets_do_not_certify_event_correspondence(self):
        left = History("h", (Commit("c", "integrator", (
            Atom("e1", "f", 3, "A"), Atom("e2", "f", 1, "A"),
        )),))
        right = replace(left, commits=(replace(left.commits[0], atoms=(
            replace(left.commits[0].atoms[0], weight=2),
            replace(left.commits[0].atoms[1], weight=2),
        )),))
        self.assertEqual(provenance_ledger(left).score_units, provenance_ledger(right).score_units)
        self.assertEqual(provenance_ledger(left).attribution_buckets,
                         provenance_ledger(right).attribution_buckets)
        self.assertFalse(certify_rewrite(left, right).valid)

    def test_local_connectivity_uses_inactive_aliases(self):
        h = History("h", (Commit("c", "integrator", (
            Atom("a", "f", 2, "A"), Atom("z", "f", 1, "Z"),
        )),), must_link=(("A", "X"),), may_link=(("X", "Z"),))
        for history in (h, replace(h, must_link=())):
            plain, main = provenance_ledger(history), analyze_history(history)
            self.assertEqual(main.score_units, plain.score_units)
            self.assertEqual(main.status, plain.status)
        self.assertNotEqual(provenance_ledger(h).status, provenance_ledger(replace(h, must_link=())).status)

    def test_missing_origins_malformed_and_empty(self):
        h = History("h", (Commit("c", "container", (Atom("e", "f", 1, None),)),))
        self.assertEqual("ABSTAIN_ORIGIN", provenance_ledger(h).status)
        self.assertEqual({}, provenance_ledger(h).score_units)
        bad = replace(h, commits=(replace(h.commits[0], atoms=(Atom("e", "f", -1, "A"),)),))
        self.assertEqual("MALFORMED_EVIDENCE", provenance_ledger(bad).status)
        self.assertEqual({}, provenance_ledger(History("empty", ())).score_units)

    def test_zero_mass_domain_against_independent_oracle(self):
        oracle = load_oracle(ROOT / "replayer/alias_rank_oracle.py")
        targets = 0
        for n in range(1, 5):
            labels = tuple(f"A{i}" for i in range(n))
            for masses in product((0, 1, 2), repeat=n):
                weights = dict(zip(labels, masses))
                for groups in component_partitions(labels):
                    answer = global_rank_diagnostics_units(weights, groups)
                    self.assertEqual(oracle.exact_bounds_all(weights, groups), answer.intervals)
                    targets += n
        self.assertEqual(5304, targets)

    def test_other_components_and_strict_ties(self):
        self.assertEqual((1, 2), global_rank_diagnostics_units(
            {"T": 5, "B": 3, "C": 3}, [("T",), ("B", "C")]).intervals["T"])
        self.assertEqual((1, 1), global_rank_diagnostics_units(
            {"T": 6, "B": 3, "C": 3}, [("T",), ("B", "C")]).intervals["T"])

    def test_large_integer_and_label_order(self):
        weights = {" A ": 10**100 + 1, "B": 10**100, "C": 0}
        groups = [(" A ",), ("B", "C")]
        result = global_rank_diagnostics_units(weights, groups)
        self.assertEqual((1, 1), result.intervals[" A "])
        self.assertEqual(result, global_rank_diagnostics_units(dict(reversed(list(weights.items()))),
                                                              list(reversed(groups))))

    def test_cap_and_input_refusals(self):
        for weights, groups, cap in [
            ({"A": 1}, [("A", "A")], 7),
            ({"A": True}, [("A",)], 7),
            ({"A": -1}, [("A",)], 7),
            ({"A": 1, "B": 2}, [("A",)], 7),
            ({"A": 1}, [("A",)], 8),
            ({str(i): 1 for i in range(8)}, [tuple(str(i) for i in range(8))], 7),
        ]:
            with self.subTest(weights=weights, cap=cap), self.assertRaises(ValueError):
                global_rank_diagnostics_units(weights, groups, maximum_component_size=cap)

    def test_compact_output_agrees_with_witness_api(self):
        rows = output_size_rows()
        self.assertEqual([7, 56, 224], [r["roots"] for r in rows])
        self.assertEqual([98, 6272, 100352], [r["witness_root_references"] for r in rows])
        self.assertEqual([14, 112, 448], [r["diagnostic_rank_endpoints"] for r in rows])

    def test_pattern_counts_do_not_depend_on_warm_cache(self):
        weights = {"A": 1, "B": 2, "C": 1, "D": 2}
        groups = [("A", "B"), ("C", "D")]
        first = global_rank_diagnostics_units(weights, groups)
        exact_global_rank_intervals_units(weights, groups)
        self.assertEqual(first, global_rank_diagnostics_units(weights, groups))
