from __future__ import annotations

import math
import csv
import io
import unittest
from dataclasses import replace
from itertools import combinations
from pathlib import Path

from rivet.certificate import certify_rewrite
from rivet.experiments import public_evaluation, summarize_public
from rivet.influence import strict_winner_flip_radius
from rivet.model import Atom, Commit, History
from rivet.score import analyze_history, baseline_scores, kendall_tau_b_units, top_alias
from rivet.transforms import split_commits
from rivet.witness import exact_minimal_atom_witness


def two_actor_history() -> History:
    return History("two", (Commit("c", "A", (
        Atom("a", "f", 3, "A"), Atom("z", "g", 1, "Z"),
    )),))


class LocalAliasContracts(unittest.TestCase):
    def test_pair_report_can_be_omitted_without_changing_decisions(self):
        for history in (two_actor_history(), replace(two_actor_history(), may_link=(("A", "Z"),))):
            full = analyze_history(history)
            compact = analyze_history(history, include_pairwise=False)
            self.assertEqual(full.status, compact.status)
            self.assertEqual(full.score_units, compact.score_units)
            self.assertEqual(full.ranking, compact.ranking)
            self.assertEqual(full.aliases.score_interval_units, compact.aliases.score_interval_units)
            self.assertEqual(full.aliases.unresolved_components, compact.aliases.unresolved_components)
            self.assertEqual((), compact.aliases.certified_pairs)
            self.assertEqual((), compact.aliases.abstained_pairs)

    def test_common_class_ties_do_not_guarantee_local_display_order(self):
        left = History("left", (Commit("c", "B", (
            Atom("eb", "F", 1, "B"), Atom("ec", "F", 1, "C"),
        )),))
        right = replace(left, history_id="right", must_link=(("A", "C"),))
        self.assertTrue(certify_rewrite(left, right).valid)
        old, new = analyze_history(left), analyze_history(right)
        self.assertEqual({"B":10**12, "C":10**12}, old.score_units)
        self.assertEqual({"A":10**12, "B":10**12}, new.score_units)
        self.assertEqual("B", old.ranking[0][0])
        self.assertEqual("A", new.ranking[0][0])
        # The declaration bridges C to A. Class scores and competition ranks
        # are invariant, but endpoint-local spelling order is not.
        self.assertEqual({"B":old.score_units["B"], "A":old.score_units["C"]}, new.score_units)

    def test_zero_mass_must_bridge_change_rejected_in_both_directions(self):
        old = replace(two_actor_history(), must_link=(("A", "X"),),
                      may_link=(("X", "Z"),))
        new = replace(old, must_link=())
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", analyze_history(old).status)
        self.assertEqual("CERTIFIED", analyze_history(new).status)
        for left, right in ((old, new), (new, old)):
            result = certify_rewrite(left, right)
            self.assertFalse(result.valid)
            self.assertIn("merge distinct", " ".join(result.reasons))

    def test_rewritten_only_must_bridge_cannot_join_old_components(self):
        old = replace(two_actor_history(), may_link=(("A", "X"), ("Y", "Z")))
        new = replace(old, must_link=(("X", "Y"),))
        for left, right in ((old, new), (new, old)):
            self.assertFalse(certify_rewrite(left, right).valid)

    def test_equivalent_inactive_intermediaries_remain_legal(self):
        old = replace(two_actor_history(), must_link=(("X", "Y"),),
                      may_link=(("A", "X"), ("Y", "Z")))
        new = replace(two_actor_history(), may_link=(("A", "Q"), ("Q", "Z")))
        for left, right in ((old, new), (new, old)):
            result = certify_rewrite(left, right)
            self.assertTrue(result.valid, result.reasons)
            self.assertEqual(analyze_history(left).status, analyze_history(right).status)

    def test_inactive_declared_classes_cannot_be_merged_by_bridge(self):
        old = replace(two_actor_history(), may_link=(("X", "Y"),))
        new = replace(two_actor_history(), must_link=(("X", "Y"),))
        self.assertFalse(certify_rewrite(old, new).valid)

    def test_small_local_declarations_match_analysis_regimes(self):
        # Every valid certificate on this finite surface must preserve the
        # independently computed endpoint status, not just combined-root status.
        pairs = tuple(combinations(("A", "X", "Y", "Z"), 2))
        histories = []
        for must in ((),) + tuple((pair,) for pair in pairs):
            for mask in range(1 << len(pairs)):
                history = replace(two_actor_history(), must_link=must,
                                  may_link=tuple(pair for i, pair in enumerate(pairs)
                                                 if mask & (1 << i)))
                if analyze_history(history).status != "MALFORMED_EVIDENCE":
                    histories.append(history)
        for history in histories:
            for other in (two_actor_history(), replace(history, must_link=())):
                if certify_rewrite(history, other).valid:
                    self.assertEqual(analyze_history(history).status,
                                     analyze_history(other).status)


class VectorContracts(unittest.TestCase):
    def test_zero_scalar_nonzero_vector_is_refused_even_if_retained(self):
        old = History("vector", (Commit("c", "A", (
            Atom("p", "f", 2, "A"), Atom("zero", "f", 0, "A", kind="cosmetic"),
        )),))
        new = old.restrict_atoms(("p",))
        self.assertTrue(certify_rewrite(old, new).valid)  # scalar only
        features = {"p": (2, 1), "zero": (0, 1)}
        for right, right_features in ((new, {"p": (2, 1)}), (old, features)):
            result = certify_rewrite(old, right, original_features=features,
                                     rewritten_features=right_features)
            self.assertFalse(result.valid)
            self.assertIn("zero-scalar event has nonzero feature vector", " ".join(result.reasons))

    def test_zero_vector_padding_and_mapped_features_certify(self):
        old = History("vector", (Commit("c", "A", (
            Atom("p", "f", 2, "A"), Atom("zero", "f", 0, None, kind="cosmetic"),
        )),))
        new = History("renamed", (Commit("d", "A", (Atom("q", "f", 2, "A"),)),))
        result = certify_rewrite(old, new, event_map=(("p", "q"),),
                                 original_features={"p": (2, 1), "zero": (0, 0)},
                                 rewritten_features={"q": (2, 1)})
        self.assertTrue(result.valid, result.reasons)

    def test_feature_changes_fail_despite_equal_scalars(self):
        history = two_actor_history()
        result = certify_rewrite(history, history,
                                 original_features={"a": (3, 1), "z": (1, 0)},
                                 rewritten_features={"a": (3, 2), "z": (1, 0)})
        self.assertFalse(result.valid)
        self.assertIn("feature vector changed at a", result.reasons)

    def test_feature_maps_must_be_total_finite_and_same_dimension(self):
        history = two_actor_history()
        valid = {"a": (3, 1), "z": (1, 0)}
        for features in (None, {"a": (3, 1)}, {**valid, "absent": (0, 0)},
                         {"a": (3,), "z": (1, 0)}, {"a": (), "z": (1, 0)},
                         {"a": (math.inf, 1), "z": (1, 0)},
                         {"a": (-1, 1), "z": (1, 0)}):
            with self.subTest(features=features):
                self.assertFalse(certify_rewrite(history, history,
                                 original_features=valid, rewritten_features=features).valid)


class TauContracts(unittest.TestCase):
    @staticmethod
    def reference_tau(left, right):
        pairs = tuple(combinations(sorted(set(left) | set(right)), 2))
        ties_left = sum(left.get(a, 0) == left.get(b, 0) for a, b in pairs)
        ties_right = sum(right.get(a, 0) == right.get(b, 0) for a, b in pairs)
        numerator = sum(
            ((left.get(a, 0) > left.get(b, 0)) - (left.get(a, 0) < left.get(b, 0))) *
            ((right.get(a, 0) > right.get(b, 0)) - (right.get(a, 0) < right.get(b, 0)))
            for a, b in pairs
        )
        product = (len(pairs) - ties_left) * (len(pairs) - ties_right)
        return numerator / math.sqrt(product) if product else None

    def test_public_correlations_match_reference_pair_formula(self):
        from rivet.io import load_histories
        from rivet.numeric import weight_units
        from rivet.experiments import BASELINES
        from rivet.transforms import (
            add_cosmetic_padding, add_empty_commits, move_entities,
            rename_event_identifiers, reorder_independent, split_alias_ambiguous,
            split_alias_certified, squash_cross_origin, squash_pairs,
        )
        root = Path(__file__).resolve().parents[1]
        by_key = {(r["history_id"], r["transformation"], r["method"]): r
                  for r in csv.DictReader((root / "results/public_transform_results.csv")
                                         .read_text(encoding="utf-8").splitlines())}
        checked = 0
        for history in load_histories(root / "data/public_windows.json"):
            rewrites = {
                "split": split_commits(history),
                "squash-certified": squash_pairs(history),
                "reorder-independent": reorder_independent(history),
                "formatting": add_cosmetic_padding(history),
                "empty-commit-padding": add_empty_commits(history),
                "file-move": move_entities(history),
                "event-map": rename_event_identifiers(history)[0],
                "alias-certified": split_alias_certified(history),
                "alias-ambiguous": split_alias_ambiguous(history),
                "squash-without-origin": squash_cross_origin(history),
            }
            for transformation, rewritten in rewrites.items():
                for method in ("rivet",) + BASELINES:
                    row = by_key[history.history_id, transformation, method]
                    if method == "rivet":
                        left, right = analyze_history(history), analyze_history(rewritten)
                        if right.status != "CERTIFIED":
                            self.assertEqual("", row["kendall_tau_b"])
                            checked += 1
                            continue
                        left_units, right_units = left.score_units, right.score_units
                    else:
                        left_units = {a: weight_units(v) for a, v in baseline_scores(history, method).items()}
                        right_units = {a: weight_units(v) for a, v in baseline_scores(rewritten, method).items()}
                    expected = self.reference_tau(left_units, right_units)
                    if expected is None:
                        self.assertEqual("", row["kendall_tau_b"])
                    else:
                        self.assertAlmostEqual(expected, float(row["kendall_tau_b"]), places=14)
                    checked += 1
        self.assertEqual(2400, checked)

    def test_all_public_rows_and_summaries_recompute_from_input(self):
        from rivet.io import load_histories
        root = Path(__file__).resolve().parents[1]
        rows, _ = public_evaluation(load_histories(root / "data/public_windows.json"))
        summary = summarize_public(rows)
        for name, items in (("public_transform_results.csv", rows), ("public_summary.csv", summary)):
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=sorted({k for row in items for k in row}))
            writer.writeheader()
            writer.writerows(items)
            expected = list(csv.DictReader(io.StringIO(buffer.getvalue())))
            actual = list(csv.DictReader((root / "results" / name).read_text(encoding="utf-8").splitlines()))
            self.assertEqual(expected, actual)
        self.assertEqual((2288, 32, 80), tuple(sum(row[k] for row in summary) for k in
                         ("tau_b_defined_count", "tau_b_undefined_count", "tau_b_unavailable_count")))

    def test_zero_denominators_are_undefined(self):
        for left, right in (({}, {}), ({"A": 1}, {"A": 1}),
                            ({"A": 1, "Z": 1}, {"A": 1, "Z": 1}),
                            ({"A": 1, "Z": 1}, {"A": 2, "Z": 1}),
                            ({"A": 2, "Z": 1}, {"A": 1, "Z": 1})):
            self.assertIsNone(kendall_tau_b_units(left, right))

    def test_union_absence_ties_and_integer_signs(self):
        self.assertEqual(-1, kendall_tau_b_units({"A": 1}, {"Z": 1}))
        huge = 10**30
        self.assertEqual(-1, kendall_tau_b_units({"A": huge, "Z": huge + 1},
                                               {"A": huge + 1, "Z": huge}))
        self.assertAlmostEqual(2 / math.sqrt(6), kendall_tau_b_units(
            {"A": 3, "B": 2, "C": 1}, {"A": 2, "B": 2, "C": 1}))

    def test_summary_excludes_undefined_and_separates_unavailable(self):
        row = dict(transformation="query", method="rivet", certificate_valid=1,
                   score_equal=1, mass_conserved=1, normalized_l1=0, top_changed=0)
        rows = [{**row, "status": "CERTIFIED", "kendall_tau_b": value}
                for value in (None, "", 0.5, 1.0)]
        rows.append({**row, "status": "ABSTAIN_ORIGIN", "kendall_tau_b": ""})
        result = summarize_public(rows)[0]
        self.assertEqual(0.75, result["mean_kendall_tau_b"])
        self.assertEqual((2, 2, 1), tuple(result[key] for key in
                         ("tau_b_defined_count", "tau_b_undefined_count", "tau_b_unavailable_count")))


class WitnessContracts(unittest.TestCase):
    def test_always_true_and_empty_only_return_empty_witness(self):
        history = two_actor_history()
        for predicate in (lambda left, right: True,
                          lambda left, right: not left.atoms()):
            self.assertEqual((), exact_minimal_atom_witness(history, history, predicate))

    def test_nonempty_predicate_returns_minimum(self):
        history = two_actor_history()
        self.assertEqual(("z",), exact_minimal_atom_witness(history, history,
                         lambda left, right: any(a.atom_id == "z" for a in left.atoms())))

    def test_no_solution_is_distinct_from_empty(self):
        history = two_actor_history()
        self.assertIsNone(exact_minimal_atom_witness(history, history,
                          lambda left, right: False))

    def test_empty_universe_checks_predicate_once(self):
        history = History("empty", ())
        calls = []
        def predicate(left, right):
            calls.append(left.atoms())
            return True
        self.assertEqual((), exact_minimal_atom_witness(history, history, predicate))
        self.assertEqual([()], calls)
        self.assertIsNone(exact_minimal_atom_witness(history, history, lambda l, r: False))

    def test_container_change_has_empty_witness(self):
        history = History("containers", (
            Commit("a", "A", (Atom("a1", "f", 1, "A"), Atom("a2", "g", 1, "A"))),
            Commit("b", "B", (Atom("b", "h", 1, "B"),)),
            Commit("c", "B", (Atom("c", "i", 1, "B"),)),
        ))
        rewritten = split_commits(history)
        self.assertEqual((), exact_minimal_atom_witness(history, rewritten,
                         lambda l, r: top_alias(baseline_scores(l, "commit_count")) !=
                                      top_alias(baseline_scores(r, "commit_count"))))

    def test_over_cap_refuses_before_testing_empty_subset(self):
        history = History("large", (Commit("c", "A", tuple(
            Atom(str(i), "f", 1, "A") for i in range(15))),))
        def predicate(left, right):
            self.fail("predicate must not execute outside the search cap")
        with self.assertRaises(ValueError):
            exact_minimal_atom_witness(history, history, predicate)
        # Fourteen is the default witness cap, not the hard alias-search cap.
        # This explicit larger universe stops at the empty subset: no expensive
        # 15-event search is performed by the regression.
        self.assertEqual((), exact_minimal_atom_witness(
            history, history, lambda left, right: True, maximum_atoms=15))


class StrictOvertakingContract(unittest.TestCase):
    def test_three_one_unit_scores_tie_before_strict_overtake(self):
        history = History("strict", (Commit("c", "A", tuple(
            Atom(str(i), "f", 1, "A" if i < 3 else "B") for i in range(4))),))
        result = strict_winner_flip_radius(history)
        self.assertEqual(2, result.minimum_relabels)
        pair = result.pairwise[0]
        self.assertEqual(pair.initial_gap_units, pair.gain_before_units)
        self.assertGreater(pair.selected_gain_units, pair.initial_gap_units)


if __name__ == "__main__":
    unittest.main()
