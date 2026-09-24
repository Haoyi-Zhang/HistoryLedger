from __future__ import annotations

import unittest
import gzip
import json
import tempfile
from unittest import mock
from dataclasses import replace
from itertools import product
from pathlib import Path

from rivet.aliases import UnionFind, exact_rank_interval_units
from rivet.alias_case_generation import generate_member
from rivet.boundary_experiments import (
    component_partitions, load_oracle, source_rows, validate_oracle_transport,
)
from rivet.certificate import certify_rewrite, validate_history
from rivet.global_aliases import exact_global_rank_interval_units, exact_global_rank_intervals_units
from rivet.model import Atom, Commit, History
from rivet.transforms import add_cosmetic_padding, move_entities, rename_event_identifiers


class BoundaryTests(unittest.TestCase):
    def test_source_controls(self):
        rows = source_rows(Path(__file__).resolve().parents[1]/'external_inputs/source_cases.json')
        self.assertEqual(len(rows), 8)
        for row in rows[:2]:
            self.assertTrue(row['final_bytes_equal'])
            self.assertNotEqual(row['path_mass'], row['comparison_mass'])
            self.assertFalse(row['reextracted_certificate_valid'])
            self.assertTrue(row['frozen_event_squash_valid'])
        self.assertEqual(sum(not row['final_ast_equal'] and row['path_mass']=='0.000000000000' for row in rows), 3)

    def test_alias_chain_does_not_recurse(self):
        labels = [f'A{i:04d}' for i in range(2501)]
        relation = tuple((labels[i],labels[i-1]) for i in range(2500,0,-1))
        u = UnionFind(labels)
        for left,right in relation:
            u.union(left,right)
        self.assertEqual(u.find(labels[-1]),labels[0])
        h = History('chain',(Commit('C',labels[-1],(Atom('E','F',1,labels[-1]),)),),must_link=relation)
        self.assertFalse(validate_history(h).malformed)
        self.assertTrue(certify_rewrite(h,h).valid)

    def test_padding_allocates_unused_event_names(self):
        h = History('padding',(Commit('C','A',(Atom('Z0001','F',1,'A'),)),))
        rewritten = add_cosmetic_padding(h)
        self.assertTrue(certify_rewrite(h,rewritten).valid)
        self.assertEqual(len({a.atom_id for a in rewritten.atoms()}),2)

    def test_renaming_avoids_cosmetic_names(self):
        h = History('rename',(Commit('C','A',(Atom('E','F',1,'A'),Atom('N0001','X',0,'A',kind='cosmetic'))),))
        rewritten,mapping = rename_event_identifiers(h)
        self.assertTrue(certify_rewrite(h,rewritten,event_map=mapping).valid)
        self.assertNotEqual(mapping[0][1],'N0001')

    def test_move_avoids_existing_entity_names(self):
        h = History('move',(Commit('C','A',(Atom('E1','F',1,'A'),Atom('E2','moved-0001',2,'A'))),))
        self.assertTrue(certify_rewrite(h,move_entities(h)).valid)

    def test_move_preserves_existing_equivalence(self):
        h = History('equivalence',(Commit('C','A',(Atom('E1','F',1,'A'),Atom('E2','G',2,'A'))),),entity_equivalence=(('F','G'),('G','moved-0001')))
        moved = move_entities(h)
        self.assertTrue(certify_rewrite(h,moved).valid)
        self.assertTrue(set(h.entity_equivalence).issubset(moved.entity_equivalence))
        self.assertNotIn('moved-0001',{a.entity for a in moved.atoms()})

    def test_component_case_generator_counts(self):
        expected = {1: 1, 2: 2, 3: 5, 4: 15, 5: 52, 6: 203, 7: 877}
        for roots, count in expected.items():
            labels = tuple(f'A{i}' for i in range(roots))
            self.assertEqual(len(component_partitions(labels)), count)


    def test_three_partition_yes_instance_reaches_three_competition_rank(self):
        weights = {"T": 11, **{f"A{i}": 4 for i in range(6)}}
        answer = exact_global_rank_interval_units(
            weights, [("T",), tuple(f"A{i}" for i in range(6))], "T"
        )
        self.assertEqual((answer.best_rank, answer.worst_rank), (1, 3))

    def test_three_partition_no_instance_cannot_cover_two_blocks(self):
        weights = {"T": 12, "A0": 4, "A1": 4, "A2": 4,
                   "A3": 4, "A4": 4, "A5": 6}
        answer = exact_global_rank_interval_units(
            weights, [("T",), tuple(f"A{i}" for i in range(6))], "T"
        )
        self.assertEqual((answer.best_rank, answer.worst_rank), (1, 2))

    def test_global_other_component_changes_worst_rank(self):
        answer = exact_global_rank_interval_units({'T':5,'B':3,'C':3},[('T',),('B','C')],'T')
        self.assertEqual((answer.best_rank,answer.worst_rank),(1,2))

    def test_global_target_merging_improves_best_rank(self):
        answer = exact_global_rank_interval_units({'T':2,'A':2,'B':3},[('T','A'),('B',)],'T')
        self.assertEqual((answer.best_rank,answer.worst_rank),(1,2))

    def test_global_ties_are_not_ahead(self):
        answer = exact_global_rank_interval_units({'T':6,'B':3,'C':3},[('T',),('B','C')],'T')
        self.assertEqual((answer.best_rank,answer.worst_rank),(1,1))

    def test_global_zero_masses(self):
        answer = exact_global_rank_interval_units({'T':0,'A':0,'B':1},[('T','A'),('B',)],'T')
        self.assertEqual((answer.best_rank,answer.worst_rank),(2,2))

    def test_global_large_exact_integer_units(self):
        big = 10**30
        answer = exact_global_rank_interval_units({'T':big,'B':big+1},[('T',),('B',)],'T')
        self.assertEqual((answer.best_rank,answer.worst_rank),(2,2))

    def test_global_component_cap(self):
        weights={f'A{i}':1 for i in range(8)}
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units(weights,[tuple(weights)],'A0')

    def test_global_cap_cannot_be_raised(self):
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units({'T':1},[('T',)],'T',maximum_component_size=8)

    def test_global_duplicate_root_refused(self):
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units({'T':1,'A':2},[('T','A'),('T',)],'T')

    def test_global_incomplete_partition_refused(self):
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units({'T':1,'A':2},[('T',)],'T')

    def test_global_negative_mass_refused(self):
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units({'T':-1},[('T',)],'T')

    def test_global_boolean_mass_refused(self):
        with self.assertRaises(ValueError):
            exact_global_rank_interval_units({'T':True},[('T',)],'T')

    def test_global_input_order_invariance(self):
        a=exact_global_rank_interval_units({'T':5,'A':4,'B':3},[('T',),('A','B')],'T')
        b=exact_global_rank_interval_units({'B':3,'A':4,'T':5},[('B','A'),('T',)],'T')
        self.assertEqual(a,b)

    @staticmethod
    def _one_root_oracle_row():
        answer = {'best_rank':1, 'worst_rank':1,
                  'best_partition':[['A0']], 'worst_partition':[['A0']],
                  'subset_transitions':0}
        return {'weights':{'A0':1}, 'components':[['A0']],
                'answers':{'A0':answer}}

    def _oracle_file(self, duplicate):
        oracle = load_oracle(Path(__file__).resolve().parents[1]/'replayer/alias_rank_oracle.py')
        row = self._one_root_oracle_row()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cases.jsonl'
            path.write_text((json.dumps(row)+'\n')*(2 if duplicate else 1))
            oracle.check(path)



    def test_oracle_member_generation_is_atomic_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member_dir = root / "results" / "global_alias_oracle"
            member_dir.mkdir(parents=True)
            destination = member_dir / "roots-1.jsonl.gz"
            destination.write_bytes(b"previous-complete-member")
            with mock.patch(
                "rivet.alias_case_generation.exact_global_rank_intervals_units",
                side_effect=RuntimeError("injected generation failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected generation failure"):
                    generate_member(root, 1)
            self.assertEqual(destination.read_bytes(), b"previous-complete-member")
            self.assertEqual(list(member_dir.glob("*.tmp")), [])
            self.assertEqual(list(member_dir.glob(".*.tmp")), [])

    def test_oracle_member_generation_cleans_stale_interrupted_temp_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            member_dir = root / "results" / "global_alias_oracle"
            member_dir.mkdir(parents=True)
            stale = member_dir / ".roots-1.jsonl.gz.interrupted.tmp"
            stale.write_bytes(b"partial-gzip")
            path, problems, cases = generate_member(root, 1)
            self.assertEqual((problems, cases), (3, 3))
            self.assertFalse(stale.exists())
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                self.assertEqual(sum(1 for _ in stream), 3)
            self.assertEqual(list(member_dir.glob(".*.tmp")), [])

    def test_oracle_member_generation_publishes_complete_gzip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, problems, cases = generate_member(root, 1)
            self.assertEqual((problems, cases), (3, 3))
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertEqual(len(rows), 3)
            self.assertEqual(
                [row["weights"]["A0"] for row in rows], [1, 2, 3]
            )
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_oracle_refuses_truncated_gzip_with_clear_diagnostic(self):
        oracle = load_oracle(
            Path(__file__).resolve().parents[1] / "replayer/alias_rank_oracle.py"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _, _ = generate_member(root, 1)
            truncated = Path(directory) / "truncated.jsonl.gz"
            truncated.write_bytes(path.read_bytes()[:-8])
            with self.assertRaisesRegex(ValueError, "corrupt oracle member"):
                oracle.check_member(truncated, 1)


    def test_transport_validation_checks_gzip_footer_and_row_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, _, _ = generate_member(root, 1)
            self.assertEqual(validate_oracle_transport(path, 3), 3)
            with self.assertRaisesRegex(ValueError, "row count changed"):
                validate_oracle_transport(path, 2)
            path.write_bytes(path.read_bytes()[:-8])
            with self.assertRaisesRegex(ValueError, "corrupt alias-oracle member"):
                validate_oracle_transport(path, 3)

    def test_oracle_reads_gzip_transport(self):
        oracle = load_oracle(Path(__file__).resolve().parents[1]/'replayer/alias_rank_oracle.py')
        row = self._one_root_oracle_row()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cases.jsonl.gz'
            with gzip.open(path, 'wt', encoding='utf-8') as stream:
                stream.write(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError, 'incomplete oracle case coverage'):
                oracle.check(path)

    def test_oracle_seven_root_alphabet_is_binary(self):
        oracle = load_oracle(Path(__file__).resolve().parents[1]/'replayer/alias_rank_oracle.py')
        roots = [f'A{i}' for i in range(7)]
        row = {'weights':{root:3 for root in roots}, 'components':[roots], 'target':'A0',
               'best_rank':1, 'worst_rank':1,
               'best_partition':[roots], 'worst_partition':[roots]}
        with self.assertRaisesRegex(ValueError, 'mass alphabet'):
            oracle._case_key(row)


    def test_batch_matches_individual_targets(self):
        weights = {'A0':3, 'A1':2, 'A2':1, 'A3':3, 'A4':1, 'A5':2, 'A6':1}
        components = [('A0', 'A1', 'A2'), ('A3', 'A4'), ('A5', 'A6')]
        batched = exact_global_rank_intervals_units(weights, components)
        self.assertEqual(
            batched,
            {target: exact_global_rank_interval_units(weights, components, target)
             for target in sorted(weights)},
        )

    def test_oracle_and_optimizer_agree_on_directed_seven_root_case(self):
        oracle = load_oracle(Path(__file__).resolve().parents[1]/'replayer/alias_rank_oracle.py')
        roots = [f'A{i}' for i in range(7)]
        weights = {root:1+(i%2) for i,root in enumerate(roots)}
        components = [roots]
        expected = oracle.exact_bounds_all(weights, components)
        for target in roots:
            answer = exact_global_rank_interval_units(weights, components, target)
            self.assertEqual((answer.best_rank, answer.worst_rank), expected[target])

    def test_oracle_mask_representation_matches_direct_partition_walk(self):
        oracle = load_oracle(Path(__file__).resolve().parents[1]/'replayer/alias_rank_oracle.py')
        roots = tuple(f'A{i}' for i in range(5))
        for groups in component_partitions(roots):
            components = [list(group) for group in groups]
            signature = oracle._component_signature(components)
            candidates = oracle.admissible_partitions(5, signature)
            for values in product((1, 2), repeat=5):
                weights = dict(zip(roots, values))
                minima = {root:6 for root in roots}
                maxima = {root:0 for root in roots}
                for blocks in candidates:
                    masses = [sum(values[index] for index in block) for block in blocks]
                    ranks = [1 + sum(other > mass for other in masses) for mass in masses]
                    for block, rank in zip(blocks, ranks):
                        for index in block:
                            root = roots[index]
                            minima[root] = min(minima[root], rank)
                            maxima[root] = max(maxima[root], rank)
                direct = {root:(minima[root], maxima[root]) for root in roots}
                self.assertEqual(oracle.exact_bounds_all(weights, components), direct)

    def test_global_mass_pattern_cache_is_label_agnostic(self):
        left_weights = {'A0':3, 'A1':1, 'A2':2, 'A3':1}
        right_weights = {'W':3, 'X':1, 'Y':2, 'Z':1}
        left = exact_global_rank_intervals_units(
            left_weights, [('A0', 'A1', 'A2'), ('A3',)]
        )
        right = exact_global_rank_intervals_units(
            right_weights, [('W', 'X', 'Y'), ('Z',)]
        )
        mapping = {'A0':'W', 'A1':'X', 'A2':'Y', 'A3':'Z'}
        for source, target in mapping.items():
            self.assertEqual(left[source].best_rank, right[target].best_rank)
            self.assertEqual(left[source].worst_rank, right[target].worst_rank)
            self.assertEqual(left[source].subset_transitions, right[target].subset_transitions)

    def test_oracle_duplicate_cases_refused(self):
        with self.assertRaisesRegex(ValueError, 'duplicate oracle problem'):
            self._oracle_file(True)

    def test_oracle_incomplete_coverage_refused(self):
        with self.assertRaisesRegex(ValueError, 'incomplete oracle case coverage'):
            self._oracle_file(False)


if __name__ == '__main__':
    unittest.main()
