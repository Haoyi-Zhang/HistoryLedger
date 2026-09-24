from __future__ import annotations

import math
import unittest
from dataclasses import replace
from itertools import product

from rivet.aliases import exact_rank_interval, exact_rank_interval_units
from rivet.certificate import certify_rewrite, validate_history
from rivet.experiments import alias_sensitivity, certificate_mutation_evaluation, score_equal
from rivet.influence import rank_influence, score_influence, strict_winner_flip_radius
from rivet.model import Atom, Commit, History
from rivet.numeric import format_units, sum_weight_units, sum_weights, weight_units
from rivet.score import analyze_history, baseline_scores, kendall_tau_b, normalized_l1
from rivet.transforms import (
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
from rivet.witness import exact_minimal_atom_witness


def fixture() -> History:
    atoms = (
        Atom("e1", "f1", 5.0, "A", raw_lines=5, raw_tokens=5),
        Atom("e2", "f2", 1.0, "A", raw_lines=1, raw_tokens=1),
        Atom("e3", "f3", 4.0, "B", raw_lines=4, raw_tokens=4),
        Atom("e4", "f4", 2.0, "B", raw_lines=2, raw_tokens=2),
    )
    commits = (
        Commit("c1", "A", atoms[:2]),
        Commit("c2", "B", atoms[2:], ("c1",)),
    )
    return History("fixture", commits)


class CertificateTests(unittest.TestCase):
    def test_base_history_valid(self) -> None:
        self.assertTrue(validate_history(fixture()).valid)

    def test_certified_rewrites_preserve_scores(self) -> None:
        history = fixture()
        original = analyze_history(history).scores
        rewrites = (
            split_commits(history),
            squash_pairs(history, retain_origins=True),
            reorder_independent(history),
            add_cosmetic_padding(history),
            add_empty_commits(history),
            move_entities(history),
        )
        for rewritten in rewrites:
            with self.subTest(rewrite=rewritten.history_id):
                self.assertTrue(certify_rewrite(history, rewritten).valid)
                self.assertEqual(original, analyze_history(rewritten).scores)

        alias_ready = replace(
            history,
            commits=(
                Commit("c1", "A", (history.commits[0].atoms[0],)),
                Commit("c2", "A", (history.commits[0].atoms[1],), ("c1",)),
                Commit("c3", "B", history.commits[1].atoms, ("c2",)),
            ),
        )
        alias_rewrite = split_alias_certified(alias_ready, "A")
        self.assertTrue(certify_rewrite(alias_ready, alias_rewrite).valid)
        self.assertEqual(
            analyze_history(alias_ready).scores,
            analyze_history(alias_rewrite).scores,
        )

    def test_explicit_event_bijection_allows_local_identifier_renaming(self) -> None:
        original = fixture()
        rewritten, event_map = rename_event_identifiers(original)
        self.assertFalse(certify_rewrite(original, rewritten).valid)
        certificate = certify_rewrite(original, rewritten, event_map=event_map)
        self.assertTrue(certificate.valid, certificate.reasons)
        self.assertEqual(
            analyze_history(original).score_units,
            analyze_history(rewritten).score_units,
        )

    def test_explicit_event_bijection_must_be_total_and_one_to_one(self) -> None:
        original = fixture()
        rewritten, event_map = rename_event_identifiers(original)
        incomplete = event_map[:-1]
        self.assertFalse(
            certify_rewrite(original, rewritten, event_map=incomplete).valid
        )
        duplicate_target = event_map[:-1] + ((event_map[-1][0], event_map[0][1]),)
        result = certify_rewrite(original, rewritten, event_map=duplicate_target)
        self.assertFalse(result.valid)
        self.assertIn("repeats target", " ".join(result.reasons))

    def test_certificate_composition_chain(self) -> None:
        original = fixture()
        middle = split_commits(original)
        final = squash_pairs(middle, retain_origins=True)
        self.assertTrue(certify_rewrite(original, middle).valid)
        self.assertTrue(certify_rewrite(middle, final).valid)
        self.assertTrue(certify_rewrite(original, final).valid)
        self.assertEqual(analyze_history(original).scores, analyze_history(final).scores)

    def test_alias_collapse_sums_event_terms_without_double_rounding(self) -> None:
        weights = (8606.484955102149, 6040.607912639551, 312.668864357908)
        commits = tuple(
            Commit(
                f"c{index}",
                "A",
                (Atom(f"e{index}", f"f{index}", weight, "A"),),
                tuple() if index == 1 else (f"c{index - 1}",),
            )
            for index, weight in enumerate(weights, 1)
        )
        history = History("rounding-regression", commits)
        rewritten = split_alias_certified(history, "A")
        self.assertTrue(certify_rewrite(history, rewritten).valid)
        self.assertEqual(analyze_history(history).scores, analyze_history(rewritten).scores)

    def test_provenance_erasure_forces_abstention(self) -> None:
        history = fixture()
        rewritten = squash_cross_origin(history, retain_origins=False)
        certificate = certify_rewrite(history, rewritten)
        self.assertFalse(certificate.valid)
        self.assertFalse(certificate.malformed)
        self.assertEqual("ABSTAIN_ORIGIN", analyze_history(rewritten).status)
        self.assertEqual({}, analyze_history(rewritten).scores)

    def test_ambiguous_alias_conserves_mass_but_not_ranking(self) -> None:
        base = fixture()
        history = replace(
            base,
            commits=(
                Commit("c1", "A", (base.commits[0].atoms[0],)),
                Commit("c2", "A", (base.commits[0].atoms[1],), ("c1",)),
                Commit("c3", "B", base.commits[1].atoms, ("c2",)),
            ),
        )
        rewritten = split_alias_ambiguous(history, "A")
        result = analyze_history(rewritten)
        self.assertFalse(certify_rewrite(history, rewritten).valid)
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", result.status)
        self.assertEqual(tuple(), result.ranking)
        self.assertEqual(1, len(result.aliases.unresolved_components))
        self.assertAlmostEqual(
            sum(analyze_history(history).scores.values()), sum(result.scores.values())
        )
        self.assertNotEqual(analyze_history(history).scores, result.scores)

    def test_cross_origin_transform_targets_a_real_boundary(self) -> None:
        history = History(
            "boundary",
            (
                Commit("c1", "A", (Atom("x1", "f1", 1.0, "A"),)),
                Commit("c2", "A", (Atom("x2", "f2", 1.0, "A"),), ("c1",)),
                Commit("c3", "B", (Atom("x3", "f3", 1.0, "B"),), ("c2",)),
            ),
        )
        changed = squash_cross_origin(history)
        origins = {atom.atom_id: atom.origin for atom in changed.atoms(include_cosmetic=False)}
        self.assertEqual("A", origins["x1"])
        self.assertIsNone(origins["x2"])
        self.assertIsNone(origins["x3"])
        self.assertEqual(2, changed.metadata["cross_origin_span_commits"])

    def test_cross_origin_transform_requires_two_origin_classes(self) -> None:
        history = History(
            "single-origin",
            (
                Commit("c1", "A", (Atom("x1", "f1", 1.0, "A"),)),
                Commit("c2", "A", (Atom("x2", "f2", 1.0, "A"),), ("c1",)),
            ),
        )
        with self.assertRaises(ValueError):
            squash_cross_origin(history)

    def test_cross_origin_transform_uses_must_link_classes(self) -> None:
        history = History(
            "must-linked-origin",
            (
                Commit("c1", "A", (Atom("x1", "f1", 1.0, "A"),)),
                Commit("c2", "A-alt", (Atom("x2", "f2", 1.0, "A-alt"),), ("c1",)),
            ),
            must_link=(("A", "A-alt"),),
        )
        with self.assertRaises(ValueError):
            squash_cross_origin(history)

    def test_may_link_decision_regime_change_is_not_certified(self) -> None:
        original = fixture()
        rewritten = replace(original, may_link=(("A", "B"),))
        result = certify_rewrite(original, rewritten)
        self.assertFalse(result.valid)
        self.assertIn("active may-link uncertainty partition changed", result.reasons)
        self.assertEqual("CERTIFIED", analyze_history(original).status)
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", analyze_history(rewritten).status)

    def test_equivalent_may_link_edge_spellings_are_certified(self) -> None:
        original = replace(
            fixture(),
            may_link=(("A", "bridge-one"), ("bridge-one", "B")),
        )
        rewritten = replace(
            original,
            may_link=(("A", "bridge-two"), ("bridge-two", "B")),
        )
        result = certify_rewrite(original, rewritten)
        self.assertTrue(result.valid, result.reasons)
        self.assertEqual(
            analyze_history(original).status,
            analyze_history(rewritten).status,
        )

    def test_inactive_may_links_do_not_change_the_active_partition(self) -> None:
        original = replace(fixture(), may_link=(("unused-one", "unused-two"),))
        rewritten = replace(original, may_link=tuple())
        result = certify_rewrite(original, rewritten)
        self.assertTrue(result.valid, result.reasons)
        self.assertEqual("CERTIFIED", analyze_history(original).status)
        self.assertEqual("CERTIFIED", analyze_history(rewritten).status)

    def test_default_alias_split_targets_score_mass_not_commit_frequency(self) -> None:
        history = History(
            "alias-target",
            (
                Commit("c1", "A", (Atom("a1", "f1", 5.0, "A"),)),
                Commit("c2", "A", (Atom("a2", "f2", 1.0, "A"),), ("c1",)),
                Commit("c3", "B", (Atom("b1", "f3", 1.0, "B"),), ("c2",)),
                Commit("c4", "B", (Atom("b2", "f4", 1.0, "B"),), ("c3",)),
                Commit("c5", "B", (Atom("b3", "f5", 1.0, "B"),), ("c4",)),
            ),
        )
        rewritten = split_alias_ambiguous(history)
        self.assertEqual("A", rewritten.metadata["alias_target"])
        self.assertEqual(["A-x", "A-y"], rewritten.metadata["alias_children"])
        result = analyze_history(rewritten)
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", result.status)
        self.assertGreater(result.score_units["A-x"], 0)
        self.assertGreater(result.score_units["A-y"], 0)


class ValidationTests(unittest.TestCase):
    def assert_malformed(self, history: History) -> None:
        validation = validate_history(history)
        self.assertTrue(validation.malformed, validation.reasons)
        self.assertFalse(validation.valid)
        self.assertEqual("MALFORMED_EVIDENCE", analyze_history(history).status)
        self.assertEqual({}, analyze_history(history).scores)
        self.assertTrue(certify_rewrite(history, history).malformed)

    def test_nonfinite_weights_are_malformed(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                atom = replace(fixture().commits[0].atoms[0], weight=value)
                history = replace(
                    fixture(),
                    commits=(replace(fixture().commits[0], atoms=(atom,)), fixture().commits[1]),
                )
                self.assert_malformed(history)

    def test_extreme_weight_is_reported_as_malformed(self) -> None:
        atom = replace(fixture().commits[0].atoms[0], weight=1e100)
        history = replace(
            fixture(),
            commits=(replace(fixture().commits[0], atoms=(atom,)), fixture().commits[1]),
        )
        self.assert_malformed(history)

    def test_negative_and_zero_structural_weights_are_malformed(self) -> None:
        for value in (-1.0, 0.0):
            with self.subTest(value=value):
                atom = replace(fixture().commits[0].atoms[0], weight=value)
                history = replace(
                    fixture(),
                    commits=(replace(fixture().commits[0], atoms=(atom,)), fixture().commits[1]),
                )
                self.assert_malformed(history)

    def test_nonzero_cosmetic_weight_is_malformed(self) -> None:
        cosmetic = Atom("z", "style", 1.0, "A", kind="cosmetic")
        history = replace(
            fixture(),
            commits=(replace(fixture().commits[0], atoms=(cosmetic,)), fixture().commits[1]),
        )
        self.assert_malformed(history)

    def test_duplicate_commit_identifier_is_malformed(self) -> None:
        history = replace(
            fixture(),
            commits=(fixture().commits[0], replace(fixture().commits[1], commit_id="c1")),
        )
        self.assert_malformed(history)

    def test_missing_predecessor_is_malformed(self) -> None:
        history = replace(
            fixture(),
            commits=(fixture().commits[0], replace(fixture().commits[1], predecessors=("absent",))),
        )
        self.assert_malformed(history)

    def test_cycle_is_malformed(self) -> None:
        history = replace(
            fixture(),
            commits=(
                replace(fixture().commits[0], predecessors=("c2",)),
                fixture().commits[1],
            ),
        )
        self.assert_malformed(history)

    def test_duplicate_event_identifier_is_malformed(self) -> None:
        duplicate = replace(fixture().commits[1].atoms[0], atom_id="e1")
        history = replace(
            fixture(),
            commits=(fixture().commits[0], replace(fixture().commits[1], atoms=(duplicate,))),
        )
        self.assert_malformed(history)

    def test_unknown_kind_and_blank_entity_are_malformed(self) -> None:
        bad = replace(fixture().commits[0].atoms[0], entity=" ", kind="unknown")
        history = replace(
            fixture(),
            commits=(replace(fixture().commits[0], atoms=(bad,)), fixture().commits[1]),
        )
        self.assert_malformed(history)

        # JSON decoding must not silently coerce invalid identifier types into
        # apparently valid strings before local validation sees them.
        decoded = History.from_dict(
            {
                "history_id": 7,
                "commits": [
                    {
                        "commit_id": 1,
                        "alias": 2,
                        "atoms": [
                            {
                                "atom_id": 3,
                                "entity": 4,
                                "weight": 1.0,
                                "origin": 2,
                            }
                        ],
                    }
                ],
            }
        )
        self.assert_malformed(decoded)

    def test_unhashable_kind_is_rejected_without_crashing(self) -> None:
        bad = replace(fixture().commits[0].atoms[0], kind=["structural"])  # type: ignore[arg-type]
        history = replace(
            fixture(),
            commits=(replace(fixture().commits[0], atoms=(bad,)), fixture().commits[1]),
        )
        self.assert_malformed(history)

    def test_cross_history_alias_merger_is_not_a_certificate(self) -> None:
        history = fixture()
        rewritten = replace(history, history_id="merged", must_link=(("A", "B"),))
        certificate = certify_rewrite(history, rewritten)
        self.assertFalse(certificate.valid)
        self.assertIn("merge distinct original classes", " ".join(certificate.reasons))

    def test_transitive_must_link_may_link_conflict_is_malformed(self) -> None:
        history = replace(
            fixture(),
            must_link=(("A", "X"), ("X", "B")),
            may_link=(("A", "B"),),
        )
        self.assert_malformed(history)

    def test_malformed_relation_shape_is_rejected_without_crashing(self) -> None:
        history = replace(fixture(), must_link=(("A", "B", "C"),))  # type: ignore[arg-type]
        self.assert_malformed(history)

    def test_nonstring_event_identifier_is_rejected_without_crashing(self) -> None:
        bad = replace(fixture().commits[0].atoms[0], atom_id=["not", "text"])  # type: ignore[arg-type]
        history = replace(
            fixture(),
            commits=(replace(fixture().commits[0], atoms=(bad,)), fixture().commits[1]),
        )
        self.assert_malformed(history)

    def test_invalid_container_shapes_are_malformed_without_crashing(self) -> None:
        base = fixture()
        commit = base.commits[0]
        cases = (
            replace(base, commits=None),  # type: ignore[arg-type]
            replace(base, commits=(None,)),  # type: ignore[arg-type]
            replace(base, must_link=None),  # type: ignore[arg-type]
            replace(base, may_link=1),  # type: ignore[arg-type]
            replace(base, entity_equivalence="bad"),  # type: ignore[arg-type]
            replace(base, metadata=None),  # type: ignore[arg-type]
            replace(base, commits=(replace(commit, atoms=None),)),  # type: ignore[arg-type]
            replace(base, commits=(replace(commit, atoms=(None,)),)),  # type: ignore[arg-type]
            replace(base, commits=(replace(commit, predecessors=None),)),  # type: ignore[arg-type]
        )
        for history in cases:
            with self.subTest(history=history):
                self.assert_malformed(history)

    def test_scaled_integer_accumulation_handles_large_aggregate(self) -> None:
        values = [1e47] * 100
        self.assertEqual(1e49, sum_weights(values))
        self.assertEqual(sum_weights(values), sum_weights(reversed(values)))

    def test_decimal_units_remain_exact_beyond_float_resolution(self) -> None:
        values = ("10000.000000000001", "0.000000000002")
        self.assertEqual(10000000000000003, sum_weight_units(values))
        self.assertEqual("10000.000000000003", format_units(sum_weight_units(values)))
        self.assertEqual(10000000000000001, weight_units(values[0]))

    def test_noninteger_bounds_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            score_influence(fixture(), "A", 1.5)  # type: ignore[arg-type]

    def test_decimal_accumulation_is_order_invariant(self) -> None:
        atoms = (
            Atom("a1", "f1", 1e16, "A"),
            Atom("a2", "f2", 1.0, "A"),
            Atom("a3", "f3", 1.0, "A"),
        )
        left = History("left", (Commit("c1", "A", atoms),))
        right = History("right", (Commit("c1", "A", tuple(reversed(atoms))),))
        left_result = analyze_history(left)
        right_result = analyze_history(right)
        self.assertEqual(left_result.score_units, right_result.score_units)
        self.assertEqual(10000000000000002000000000000, left_result.score_units["A"])

        # A one-quantum difference beyond binary-float resolution must still
        # determine the certified order on the exact internal surface.
        close = History(
            "close",
            (
                Commit(
                    "c1",
                    "A",
                    (Atom("b1", "f1", "10000000000000000.000000000000", "A"),),
                ),
                Commit(
                    "c2",
                    "B",
                    (Atom("b2", "f2", "10000000000000000.000000000001", "B"),),
                    ("c1",),
                ),
            ),
        )
        close_result = analyze_history(close)
        self.assertGreater(close_result.score_units["B"], close_result.score_units["A"])
        self.assertEqual("B", close_result.ranking[0][0])
        self.assertIn(("A", "B", "<"), close_result.aliases.certified_pairs)

    def test_rivet_score_comparison_is_exact(self) -> None:
        left = {"A": 1.0}
        right = {"A": 1.0 + 5e-10}
        self.assertFalse(score_equal(left, right))
        self.assertTrue(score_equal(left, right, tolerance=1e-9))

    def test_identical_vectors_have_exact_zero_normalized_distance(self) -> None:
        scores = {"A": 5822.406062864184, "B": 4814.147687162597}
        self.assertEqual(0.0, normalized_l1(scores, dict(reversed(tuple(scores.items())))))

    def test_resolved_score_tie_is_certified_not_alias_abstention(self) -> None:
        result = analyze_history(fixture())
        self.assertEqual("CERTIFIED", result.status)
        self.assertEqual((("A", 6.0), ("B", 6.0)), result.ranking)
        self.assertIn(("A", "B", "="), result.aliases.certified_pairs)
        self.assertEqual(tuple(), result.aliases.unresolved_components)

    def test_normalized_distance_is_stable_across_mapping_orders(self) -> None:
        pairs = [(f"A{i:03d}", (i + 1) * 0.1, (80 - i) * 0.07) for i in range(80)]
        orders = (
            pairs,
            list(reversed(pairs)),
            pairs[::2] + pairs[1::2],
            pairs[1::2] + pairs[::2],
            sorted(pairs, key=lambda item: (item[0][2:], item[0][0])),
            sorted(pairs, key=lambda item: item[1]),
            sorted(pairs, key=lambda item: item[2]),
            pairs[20:] + pairs[:20],
        )
        outputs = {
            normalized_l1(
                {actor: left for actor, left, _ in order},
                {actor: right for actor, _, right in reversed(order)},
            )
            for order in orders
        }
        self.assertEqual(1, len(outputs), outputs)


class BoundsTests(unittest.TestCase):
    def test_exact_alias_rank_interval_and_partition_count(self) -> None:
        scores = {"a": 4.0, "b": 3.0, "c": 2.0, "outside": 8.0}
        best, worst, resolutions = exact_rank_interval(scores, ("a", "b", "c"), "a")
        self.assertEqual(5, resolutions)  # Bell number B_3
        self.assertEqual(1, best)
        self.assertEqual(3, worst)

    def test_exact_alias_rank_interval_refuses_oversized_component(self) -> None:
        aliases = tuple(f"a{i}" for i in range(8))
        with self.assertRaises(ValueError):
            exact_rank_interval({alias: 1.0 for alias in aliases}, aliases, aliases[0])

    def test_exact_alias_rank_interval_requires_integer_cap(self) -> None:
        with self.assertRaises(ValueError):
            exact_rank_interval({"a": 1.0}, ("a",), "a", maximum_component_size=2.5)  # type: ignore[arg-type]

    def test_exact_alias_rank_interval_units_keeps_sub_float_ordering(self) -> None:
        scores = {
            "a": 10000000000000001,
            "b": 10000000000000000,
            "outside": 10000000000000000,
        }
        best, worst, resolutions = exact_rank_interval_units(scores, ("a", "b"), "a")
        self.assertEqual(2, resolutions)
        self.assertEqual(1, best)
        self.assertEqual(1, worst)

    def test_alias_sensitivity_partitions_conserve_exact_units(self) -> None:
        rows = alias_sensitivity([fixture()], trials_per_size=2)
        self.assertEqual(12, len(rows))
        for row in rows:
            self.assertEqual(row["component_score_units"], row["partition_total_units"])
            self.assertGreater(row["anchor_score_units"], 0)

    def test_certificate_mutation_campaign_rejects_every_obligation_fault(self) -> None:
        rows = certificate_mutation_evaluation([fixture()])
        self.assertEqual(7, len(rows))
        self.assertEqual(7, sum(row["detected"] for row in rows))
        self.assertEqual(
            {
                "missing-event",
                "extra-event",
                "one-quantum-weight",
                "origin-substitution",
                "undeclared-entity-substitution",
                "cross-history-alias-merge",
                "may-link-regime-change",
            },
            {row["fault"] for row in rows},
        )

    def test_strict_winner_flip_radius_is_exact(self) -> None:
        history = History(
            "winner-radius",
            (
                Commit(
                    "c1",
                    "A",
                    tuple(Atom(f"a{index}", f"fa{index}", 1.0, "A") for index in range(3)),
                ),
                Commit("c2", "B", (Atom("b1", "fb", 1.0, "B"),), ("c1",)),
                Commit("c3", "C", (Atom("c1", "fc", 1.0, "C"),), ("c2",)),
            ),
        )
        result = strict_winner_flip_radius(history)
        self.assertEqual("A", result.leader)
        self.assertEqual(2, result.minimum_relabels)
        self.assertEqual("B", result.challenger)
        self.assertEqual(2, result.initial_gap_units // 10**12)
        self.assertLessEqual(
            next(pair for pair in result.pairwise if pair.challenger == "B").gain_before_units,
            result.initial_gap_units,
        )
        self.assertGreater(
            next(pair for pair in result.pairwise if pair.challenger == "B").selected_gain_units,
            result.initial_gap_units,
        )

        atoms = history.atoms(include_cosmetic=False)
        actors = tuple(sorted(analyze_history(history).score_units))
        exact = None
        for destinations in product(actors, repeat=len(atoms)):
            changes = sum(
                destination != atom.origin
                for atom, destination in zip(atoms, destinations)
            )
            scores = {actor: 0 for actor in actors}
            for atom, destination in zip(atoms, destinations):
                scores[destination] += weight_units(atom.weight)
            if any(scores[actor] > scores["A"] for actor in actors if actor != "A"):
                exact = changes if exact is None else min(exact, changes)
        self.assertEqual(exact, result.minimum_relabels)

    def test_winner_flip_refuses_ties_and_unresolved_identity(self) -> None:
        with self.assertRaises(ValueError):
            strict_winner_flip_radius(fixture())
        with self.assertRaises(ValueError):
            strict_winner_flip_radius(replace(fixture(), may_link=(("A", "B"),)))

    def test_single_actor_has_no_observed_winner_challenger(self) -> None:
        history = History(
            "solo-radius",
            (Commit("c1", "A", (Atom("e", "f", 1.0, "A"),)),),
        )
        result = strict_winner_flip_radius(history)
        self.assertIsNone(result.minimum_relabels)
        self.assertIsNone(result.challenger)
        self.assertEqual(tuple(), result.pairwise)

    def test_exact_score_influence(self) -> None:
        history = fixture()
        bound = score_influence(history, "A", 1)
        self.assertEqual(6.0, bound.original)
        self.assertEqual(1.0, bound.minimum)
        self.assertEqual(10.0, bound.maximum)

    def test_score_influence_keeps_exact_internal_units(self) -> None:
        history = History(
            "unit-influence",
            (
                Commit(
                    "c1",
                    "A",
                    (Atom("e1", "f1", "10000.000000000001", "A"),),  # type: ignore[arg-type]
                ),
                Commit(
                    "c2",
                    "B",
                    (Atom("e2", "f2", "7.000000000003", "B"),),  # type: ignore[arg-type]
                    ("c1",),
                ),
            ),
        )
        bound = score_influence(history, "A", 1)
        self.assertEqual(10000000000000001, bound.original_units)
        self.assertEqual(0, bound.minimum_units)
        self.assertEqual(10007000000000004, bound.maximum_units)
        self.assertEqual(10000000000000001, bound.removable_units)
        self.assertEqual(7000000000003, bound.acquirable_units)

    def test_must_link_alias_is_canonicalized_for_influence(self) -> None:
        history = replace(fixture(), must_link=(("A", "A-alt"),))
        bound = score_influence(history, "A-alt", 1)
        self.assertEqual("A", bound.actor)
        self.assertEqual(6.0, bound.original)

    def test_single_actor_has_no_admissible_relabeling(self) -> None:
        history = History(
            "solo",
            (Commit("c1", "A", (Atom("a1", "f1", 4.0, "A"),)),),
        )
        bound = score_influence(history, "A", 3)
        self.assertEqual(bound.original, bound.minimum)
        self.assertEqual(bound.original, bound.maximum)

    def test_influence_refuses_unresolved_alias_identity(self) -> None:
        history = replace(fixture(), may_link=(("A", "B"),))
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", analyze_history(history).status)
        with self.assertRaises(ValueError):
            score_influence(history, "A", 1)
        with self.assertRaises(ValueError):
            rank_influence(history, "A", 1)

    def test_score_influence_matches_exhaustive_reassignments(self) -> None:
        history = fixture()
        atoms = history.atoms(include_cosmetic=False)
        actors = tuple(sorted(analyze_history(history).scores))
        for target in actors:
            for budget in range(3):
                bound = score_influence(history, target, budget)
                attainable = []
                for destinations in product(actors, repeat=len(atoms)):
                    changed = sum(
                        destination != atom.origin
                        for atom, destination in zip(atoms, destinations)
                    )
                    if changed > budget:
                        continue
                    attainable.append(
                        sum(
                            weight_units(atom.weight)
                            for atom, destination in zip(atoms, destinations)
                            if destination == target
                        )
                    )
                self.assertEqual(min(attainable), bound.minimum_units)
                self.assertEqual(max(attainable), bound.maximum_units)

    def test_rank_interval_contains_all_one_event_reassignments(self) -> None:
        history = fixture()
        interval = rank_influence(history, "A", 1)
        observed_ranks = set()
        actors = ("A", "B")
        atoms = history.atoms(include_cosmetic=False)
        candidates = [None] + [(index, actor) for index in range(len(atoms)) for actor in actors]
        for mutation in candidates:
            changed = list(atoms)
            if mutation is not None:
                index, actor = mutation
                changed[index] = replace(changed[index], origin=actor)
            mutated = History(
                "mutated",
                (
                    Commit("c1", "A", tuple(changed[:2])),
                    Commit("c2", "B", tuple(changed[2:]), ("c1",)),
                ),
            )
            scores = analyze_history(mutated).scores
            rank = 1 + sum(value > scores["A"] for name, value in scores.items() if name != "A")
            observed_ranks.add(rank)
        self.assertGreaterEqual(min(observed_ranks), interval.best_rank)
        self.assertLessEqual(max(observed_ranks), interval.worst_rank)


class DiagnosticsTests(unittest.TestCase):
    def test_minimal_witness(self) -> None:
        history = fixture()
        rewritten = squash_cross_origin(history, retain_origins=False)

        def predicate(left: History, right: History) -> bool:
            return bool(left.atoms(include_cosmetic=False)) and analyze_history(right).status == "ABSTAIN_ORIGIN"

        witness = exact_minimal_atom_witness(history, rewritten, predicate)
        self.assertEqual(1, len(witness))

    def test_witness_search_refuses_to_truncate_the_universe(self) -> None:
        atoms = tuple(Atom(f"e{i}", f"f{i}", 1.0, "A") for i in range(15))
        history = History("large", (Commit("c1", "A", atoms),))
        with self.assertRaises(ValueError):
            exact_minimal_atom_witness(history, history, lambda _left, _right: True)

    def test_witness_search_requires_integer_cap(self) -> None:
        history = fixture()
        with self.assertRaises(ValueError):
            exact_minimal_atom_witness(
                history, history, lambda _left, _right: True, maximum_atoms=2.5  # type: ignore[arg-type]
            )

    def test_baseline_counterexamples_and_tau(self) -> None:
        history = fixture()
        split = split_commits(history)
        self.assertNotEqual(
            baseline_scores(history, "commit_count"), baseline_scores(split, "commit_count")
        )
        self.assertEqual(1.0, kendall_tau_b({"a": 2.0, "b": 1.0}, {"a": 2.0, "b": 1.0}))


if __name__ == "__main__":
    unittest.main()
