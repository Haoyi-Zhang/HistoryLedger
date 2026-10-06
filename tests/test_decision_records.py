"""Regressions for the bounded, independently readable event-map examples."""
import ast
import copy
from pathlib import Path
from typing import Any, Mapping
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts' / 'reviewer_f1_f11.py'
NAMES = {'ReviewError', 'require', 'decision_records', '_aggregate_endpoint',
         'replay_decision_record'}
TREE = ast.parse(SOURCE.read_text(encoding='utf-8'))
NAMESPACE = {'Any': Any, 'Mapping': Mapping}
exec(compile(ast.Module(body=[node for node in TREE.body
                             if getattr(node, 'name', None) in NAMES],
                        type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)


class DecisionRecordContracts(unittest.TestCase):
    def setUp(self):
        self.rows = NAMESPACE['decision_records']()

    def replay(self, row):
        return NAMESPACE['replay_decision_record'](row)

    def test_current_examples_have_their_declared_decisions(self):
        self.assertEqual(['ACCEPT', 'ACCEPT', 'UNCERTAIN'],
                         [self.replay(row)['decision'] for row in self.rows])

    def test_one_to_many_mapping_is_rejected(self):
        row = copy.deepcopy(self.rows[1])
        row['left_endpoint']['events'] = [{'id': 'e', 'root': 'A', 'units': 4}]
        for pair in row['event_mapping']:
            pair['left'] = 'e'
        with self.assertRaisesRegex(NAMESPACE['ReviewError'], 'one-to-one'):
            self.replay(row)

    def test_equal_actor_totals_do_not_mask_per_event_change(self):
        row = copy.deepcopy(self.rows[1])
        for event in row['right_endpoint']['events']:
            event['units'] = 2
        with self.assertRaisesRegex(NAMESPACE['ReviewError'], 'units differ'):
            self.replay(row)

    def test_common_map_cannot_merge_distinct_classes(self):
        row = copy.deepcopy(self.rows[1])
        row['right_endpoint']['classes'] = [['A1'], ['A2']]
        with self.assertRaisesRegex(NAMESPACE['ReviewError'], 'merges distinct'):
            self.replay(row)

    def test_boolean_units_are_not_integer_weights(self):
        row = copy.deepcopy(self.rows[0])
        row['left_endpoint']['events'][0]['units'] = True
        with self.assertRaisesRegex(NAMESPACE['ReviewError'], 'exact integers'):
            self.replay(row)
