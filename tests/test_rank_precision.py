import unittest

from rivet.influence import rank_influence
from rivet.model import Atom, Commit, History


class RankPrecisionTests(unittest.TestCase):
    def history(self, left, right):
        return History("rank-precision", (Commit("c", "container", (
            Atom("eA", "entity", left, "A"),
            Atom("eB", "entity", right, "B"),
        )),))

    def test_one_quantum_difference_survives_float_projection(self):
        history = self.history("10000000000000000.000000000001",
                               "10000000000000000.000000000000")
        result = rank_influence(history, "B", 0)
        self.assertEqual((result.best_rank, result.worst_rank), (2, 2))

    def test_exact_tie_has_competition_rank_one(self):
        history = self.history("10000000000000000.000000000000",
                               "10000000000000000.000000000000")
        result = rank_influence(history, "B", 0)
        self.assertEqual((result.best_rank, result.worst_rank), (1, 1))

    def test_ordinary_zero_budget_ranks(self):
        history = self.history("2", "1")
        for actor, rank in (("A", 1), ("B", 2)):
            result = rank_influence(history, actor, 0)
            self.assertEqual((result.best_rank, result.worst_rank), (rank, rank))


if __name__ == "__main__":
    unittest.main()
