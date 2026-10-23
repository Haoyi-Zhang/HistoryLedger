"""Cache eviction changes retained work, never exact rank answers."""
import unittest

from rivet.global_aliases import (
    PATTERN_CACHE_ENTRIES, _max_above_pattern,
    exact_global_rank_intervals_units, global_rank_diagnostics_units,
)


class PatternCacheTests(unittest.TestCase):
    def setUp(self):
        _max_above_pattern.cache_clear()

    def tearDown(self):
        _max_above_pattern.cache_clear()

    def churn(self):
        for index in range(PATTERN_CACHE_ENTRIES + 1):
            _max_above_pattern((index, index + 1), index)

    def test_persistent_entry_budget_is_enforced(self):
        self.churn()
        info = _max_above_pattern.cache_info()
        self.assertEqual(info.maxsize, PATTERN_CACHE_ENTRIES)
        self.assertEqual(info.currsize, PATTERN_CACHE_ENTRIES)

    def test_evicted_pattern_is_recomputed_exactly(self):
        pattern, threshold = (0, 2, 3, 1, 4, 2, 0), 3
        expected = _max_above_pattern.__wrapped__(pattern, threshold)
        self.assertEqual(_max_above_pattern(pattern, threshold), expected)
        self.churn()
        misses = _max_above_pattern.cache_info().misses
        self.assertEqual(_max_above_pattern(pattern, threshold), expected)
        self.assertEqual(_max_above_pattern.cache_info().misses, misses + 1)

    def test_both_public_apis_ignore_eviction_history(self):
        weights = {'T': 5, 'B': 3, 'C': 3, 'Z': 0}
        groups = [('T',), ('B', 'C', 'Z')]
        expected = exact_global_rank_intervals_units(weights, groups)
        diagnostic = global_rank_diagnostics_units(weights, groups)
        self.churn()
        self.assertEqual(exact_global_rank_intervals_units(weights, groups), expected)
        self.assertEqual(global_rank_diagnostics_units(weights, groups), diagnostic)
        self.assertEqual(diagnostic.intervals['T'], (1, 2))
