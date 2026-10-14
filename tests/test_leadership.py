"""Small authored exact controls; no generated matrix or upstream execution."""
import ast
import copy
from decimal import Decimal
import importlib.util
from itertools import product
from pathlib import Path
import unittest

from rivet.influence import strict_winner_flip_radius
from rivet.leadership import leadership_diagnostic
from rivet.model import Atom, Commit, History

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("independent_leadership", ROOT / "replayer/leadership.py")
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


def history(name, pairs, must=(), may=()):
    events = tuple(Atom(f"e{i}", "owned", Decimal(f"{units}e-12"), owner)
                   for i, (owner, units) in enumerate(pairs))
    return History(name, (Commit("owned-container", "integrator", events),), must_link=must, may_link=may)


def fixtures():
    return [
        history("tie-before-strict", [("A", 1), ("A", 1), ("A", 1), ("B", 1)]),
        history("all-challengers", [("A", 1), ("A", 1), ("A", 1), ("B", 1), ("C", 2)]),
        history("third-party-gain", [("A", 2), ("A", 2), ("A", 2), ("B", 1), ("C", 5)]),
        history("single-actor", [("A", 3)]),
        history("one-quantum-gap", [("A", 10**20 + 1), ("B", 10**20)]),
        history("literal-labels", [(" A ", 3), ("A", 1)]),
        history("resolved-must", [("A", 1), ("X", 2), ("B", 1)], must=(("A", "X"),)),
    ]


def brute_radii(events):
    """Enumerate final assignments and Hamming cost, never the gain formula."""
    if len(events) > 6:
        raise ValueError("owned oracle cap is six events")
    actors = sorted({e["owner"] for e in events})
    if len(actors) > 3:
        raise ValueError("owned oracle cap is three actor classes")
    initial = {a: sum(e["units"] for e in events if e["owner"] == a) for a in actors}
    leader = max(actors, key=initial.get)
    minima = {"loss_of_unique": None, "strict_overtake": None}
    examined = 0
    for destinations in product(actors, repeat=len(events)):
        examined += 1
        totals = {a: 0 for a in actors}
        changes = 0
        for event, destination in zip(events, destinations):
            totals[destination] += event["units"]
            changes += destination != event["owner"]
        rivals = [totals[a] for a in actors if a != leader]
        for mode, met in [("loss_of_unique", bool(rivals) and max(rivals) >= totals[leader]),
                          ("strict_overtake", bool(rivals) and max(rivals) > totals[leader])]:
            if met:
                minima[mode] = changes if minima[mode] is None else min(minima[mode], changes)
    return minima, examined


class LeadershipTests(unittest.TestCase):
    def test_both_thresholds_match_independent_assignment_oracle(self):
        for case in fixtures():
            record = leadership_diagnostic(case)
            expected, _ = brute_radii(record["events"])
            self.assertEqual(expected, consumer.verify(record)["radii"])
            self.assertEqual(expected, consumer.direct_radii(record["events"]))

    def test_existing_strict_radius_and_witness_are_unchanged(self):
        for case in fixtures():
            record, old = leadership_diagnostic(case), strict_winner_flip_radius(case)
            query = record["queries"]["strict_overtake"]
            self.assertEqual(old.minimum_relabels, query["minimum_relabels"])
            self.assertEqual(old.challenger, query["challenger"])
            self.assertEqual(list(old.witness_atoms), query["witness_atoms"])

    def test_tie_is_not_a_strict_overtake(self):
        record = leadership_diagnostic(fixtures()[0])
        self.assertEqual({"loss_of_unique": 1, "strict_overtake": 2}, consumer.verify(record)["radii"])
        changed = copy.deepcopy(record)
        changed["queries"]["strict_overtake"] = copy.deepcopy(changed["queries"]["loss_of_unique"])
        with self.assertRaises(ValueError):
            consumer.verify(changed)

    def test_global_minimality_requires_every_challenger(self):
        record = leadership_diagnostic(fixtures()[1])
        query = record["queries"]["strict_overtake"]
        self.assertEqual(1, query["minimum_relabels"])
        b = next(row for row in query["pairwise"] if row["challenger"] == "B")
        self.assertEqual(2, b["minimum_relabels"])
        query.update(minimum_relabels=2, challenger="B", witness_atoms=b["witness_atoms"], pairwise=[b])
        with self.assertRaises(ValueError):
            consumer.verify(record)

    def test_mutated_arithmetic_events_witness_and_lower_bound_reject(self):
        record = leadership_diagnostic(fixtures()[0])
        for fault in ("lower", "gain", "boolean", "witness", "duplicate", "score"):
            changed = copy.deepcopy(record)
            row = changed["queries"]["strict_overtake"]["pairwise"][0]
            if fault == "lower": row["max_smaller_budget_gain_units"] += 1
            elif fault == "gain": row["witness_gain_units"] += 1
            elif fault == "boolean": row["minimum_relabels"] = True
            elif fault == "witness": row["witness_atoms"][0] = "absent"
            elif fault == "duplicate": changed["events"].append(copy.deepcopy(changed["events"][0]))
            else: changed["score_units"]["A"] += 1
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                consumer.verify(changed)

    def test_refused_identity_origin_initial_tie_and_record_bounds(self):
        for case in [history("tie", [("A", 1), ("B", 1)]),
                     history("unknown", [(None, 2), ("B", 1)]),
                     history("may", [("A", 2), ("B", 1)], may=(("A", "B"),))]:
            with self.assertRaises(ValueError): leadership_diagnostic(case)
        with self.assertRaises(ValueError): consumer.surface([])
        event = {"atom_id": "e", "entity": "owned", "owner": "A", "units": 1}
        with self.assertRaises(ValueError): consumer.surface([event] * 4097)
        with self.assertRaises(ValueError): consumer.surface([dict(event, units=10**60)])
        with self.assertRaises(ValueError): consumer.unique_object([("x", 1), ("x", 2)])

    def test_consumer_imports_no_project_implementation(self):
        tree = ast.parse((ROOT / "replayer/leadership.py").read_text(encoding="utf-8"))
        imports = [name for node in ast.walk(tree) for name in
                   ([node.module] if isinstance(node, ast.ImportFrom) else
                    [a.name for a in node.names] if isinstance(node, ast.Import) else [])]
        self.assertTrue(all(name in {"__future__", "argparse", "heapq", "json", "pathlib"} for name in imports))

    def test_one_actor_has_no_observed_challenger(self):
        record = leadership_diagnostic(fixtures()[3])
        self.assertEqual({"loss_of_unique": None, "strict_overtake": None}, consumer.verify(record)["radii"])


if __name__ == "__main__":
    unittest.main()
