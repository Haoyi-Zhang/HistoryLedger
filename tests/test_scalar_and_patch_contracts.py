"""Bounded scalar-history, unified-hunk and event-universe contracts."""
from dataclasses import replace
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from rivet.certificate import certify_rewrite
from rivet.experiments import export_ledger
from rivet.extract_public import parse_patch
from rivet.model import Atom, Commit, History
from rivet.public_patch_experiments import _file_record, split_change_parts

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("scalar_contract_consumer", ROOT / "replayer/replay.py")
CONSUMER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONSUMER)


def history():
    return History(" h ", (Commit("c", "container", (
        Atom(" e ", " f ", "10000.000000000001", " A "),
        Atom("zero", "style", 0, None, kind="cosmetic"),
    )), Commit("empty", "container", (), ("c",))))


def rows(h):
    return [dict(history_id=h.history_id, atom_id=a.atom_id, entity=a.entity,
                 weight=str(a.weight), origin=a.origin or "", kind=a.kind) for a in h.atoms()]


def invalid_histories():
    h = history()
    first, empty = h.commits
    return [
        replace(h, commits=(replace(first, predecessors=("c",)), empty)),
        replace(h, commits=(replace(first, predecessors=("empty",)), empty)),
        replace(h, commits=(first, replace(empty, predecessors=("absent",)))),
        replace(h, commits=(first, replace(empty, commit_id="c", predecessors=()))),
        replace(h, commits=(replace(first, atoms=(replace(first.atoms[0], raw_lines=-1),)), empty)),
        replace(h, commits=(replace(first, atoms=(replace(first.atoms[0], origin=None),)), empty)),
    ]


class ScalarHistoryContracts(unittest.TestCase):
    def test_export_preflight_creates_no_files_for_invalid_history(self):
        for h in invalid_histories():
            with self.subTest(history=h), tempfile.TemporaryDirectory() as raw:
                ledger, expected = Path(raw)/"ledger.csv", Path(raw)/"expected.json"
                with self.assertRaises(ValueError):
                    export_ledger([h], ledger, expected)
                self.assertFalse(ledger.exists())
                self.assertFalse(expected.exists())

    def test_export_preflight_preserves_both_existing_outputs(self):
        for supplied in ([history(), invalid_histories()[0]], [history(), history()]):
            with self.subTest(histories=supplied), tempfile.TemporaryDirectory() as raw:
                ledger, expected = Path(raw)/"ledger.csv", Path(raw)/"expected.json"
                ledger.write_bytes(b"retained-ledger")
                expected.write_bytes(b"retained-expectation")
                with self.assertRaises(ValueError):
                    export_ledger(supplied, ledger, expected)
                self.assertEqual(b"retained-ledger", ledger.read_bytes())
                self.assertEqual(b"retained-expectation", expected.read_bytes())

    def test_replay_refuses_invalid_graph_even_with_matching_rows_and_totals(self):
        for h in invalid_histories()[:4]:
            with self.subTest(history=h):
                actual = CONSUMER.replay(rows(h), histories={"histories": [h.to_dict()]})
                self.assertTrue(actual["errors"])
                self.assertEqual({}, actual["scores"])

    def test_replay_preflights_row_fields_containers_and_singleton_scope(self):
        good = history().to_dict()
        cases = []
        for key, value in [("raw_lines", -1), ("raw_tokens", True), ("origin", None),
                           ("atom_id", ""), ("kind", "other"), ("weight", "NaN")]:
            changed = json.loads(json.dumps(good))
            changed["commits"][0]["atoms"][0][key] = value
            cases.append(changed)
        cases.extend([{**good, "commits": None}, {**good, "metadata": None},
                      {**good, "must_link": [[" A ", "other"]]},
                      {**good, "entity_equivalence": [["f", "f"]]}])
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(CONSUMER.replay(rows(history()), histories=[case])["errors"])
        self.assertTrue(CONSUMER.replay(rows(history()), histories=[good, good])["errors"])

    def test_replay_binds_validated_history_events_to_ledger(self):
        good = history()
        original_rows = rows(good)
        for changed in (original_rows[:-1],
                        [{**original_rows[0], "weight": "1"}, original_rows[1]],
                        [{**original_rows[0], "origin": "different"}, original_rows[1]]):
            with self.subTest(rows=changed):
                self.assertTrue(CONSUMER.replay(changed, histories=[good.to_dict()])["errors"])

    def test_cli_rejects_cycle_and_marks_csv_only_scope(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ledger, expected = root/"ledger.csv", root/"expected.json"
            export_ledger([history()], ledger, expected)
            source = root/"histories.json"
            source.write_text(json.dumps({"histories": [invalid_histories()[0].to_dict()]}), encoding="utf-8")
            command = [sys.executable, "-B", str(ROOT/"replayer/replay.py"), str(ledger), "--expected", str(expected)]
            legacy = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual("NOT_SUPPLIED", json.loads(legacy.stdout)["history_validation"])
            bad = subprocess.run(command + ["--histories", str(source)], capture_output=True, text=True)
            self.assertNotEqual(0, bad.returncode)
            self.assertEqual("FAIL", json.loads(bad.stdout)["status"])
            source.write_text(json.dumps({"histories": [history().to_dict()]}), encoding="utf-8")
            valid = subprocess.run(command + ["--histories", str(source)], capture_output=True, text=True, check=True)
            self.assertEqual("PASS", json.loads(valid.stdout)["history_validation"])
            # A mutually consistent forged CSV and expected document must
            # still disagree with the supplied valid normalized history.
            forged = rows(history())
            forged[0]["weight"] = "1"
            with ledger.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=forged[0])
                writer.writeheader()
                writer.writerows(forged)
            expected.write_text(json.dumps(CONSUMER.replay(forged)), encoding="utf-8")
            unbound = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual("PASS", json.loads(unbound.stdout)["status"])
            bound = subprocess.run(command + ["--histories", str(source)], capture_output=True, text=True)
            self.assertNotEqual(0, bound.returncode)
            self.assertEqual("FAIL", json.loads(bound.stdout)["status"])

    def test_valid_context_preserves_literal_decimal_cosmetic_and_empty_commits(self):
        h = history()
        legacy = CONSUMER.replay(rows(h))
        bound = CONSUMER.replay(rows(h), histories={"histories": [h.to_dict()]})
        self.assertEqual(legacy, bound)
        self.assertFalse(bound["errors"])
        self.assertEqual("10000.000000000001", bound["scores"][" h "][" A "])


class UnifiedPatchContracts(unittest.TestCase):
    def test_full_diff_preserves_spaced_compact_and_pathlike_unary_payload(self):
        for old, new in [("--x;", "++x;"), ("-- x;", "++ x;"), ("-- b/x;", "++ b/x;")]:
            patch = f"diff --git a/unit.cpp b/unit.cpp\n--- a/unit.cpp\n+++ b/unit.cpp\n@@ -1 +1 @@\n-{old}\n+{new}\n"
            parsed = parse_patch(patch)
            self.assertEqual({"unit.cpp"}, set(parsed))
            self.assertEqual((2, 1), (parsed["unit.cpp"]["raw_lines"], parsed["unit.cpp"]["structural_tokens"]))

    def test_real_headers_zero_ranges_multiple_files_and_no_newline_marker(self):
        patch = ("diff --git a/added.cpp b/added.cpp\nnew file mode 100644\n--- /dev/null\n+++ b/added.cpp\n"
                 "@@ -0,0 +1 @@\n+++x;\n\\ No newline at end of file\n"
                 "diff --git a/deleted.cpp b/deleted.cpp\n--- a/deleted.cpp\n+++ /dev/null\n"
                 "@@ -1 +0,0 @@\n---x;\n\\ No newline at end of file\n")
        parsed = parse_patch(patch)
        self.assertEqual({"added.cpp", "deleted.cpp"}, set(parsed))
        self.assertTrue(all(row["raw_lines"] == 1 and row["structural_tokens"] == 3 for row in parsed.values()))

    def test_header_free_hunks_preserve_unary_operators(self):
        for old, new in [("--x;", "++x;"), ("-- x;", "++ x;")]:
            result = _file_record("unit.cpp", f"@@ -1 +1 @@\n-{old}\n+{new}\n")
            self.assertEqual((1, 1, 1), (result["endpoint_mass"], result["hunk_path_mass"], result["block_path_mass"]))

    def test_header_free_syntax_still_rejects_file_headers_outside_hunks(self):
        good = "@@ -1 +1 @@\n-x\n+y\n"
        for patch in ("--- a/unit.cpp\n+++ b/unit.cpp\n"+good,
                      good+"--- a/other.cpp\n+++ b/other.cpp\n",
                      good+"diff --git a/other.cpp b/other.cpp\n"):
            for by_hunk in (False, True):
                with self.subTest(patch=patch, by_hunk=by_hunk), self.assertRaises(ValueError):
                    split_change_parts(patch, by_hunk=by_hunk)

    def test_malformed_headers_truncated_excess_or_unsupported_hunks_refuse(self):
        cases = ["@@ broken\n-x\n+y\n", "@@ -1,2 +1,2 @@\n-x\n+y\n",
                 "@@ -1 +1 @@\n-x\n+y\n+extra\n", "@@ -1 +1 @@\n-x\n+y\n \n",
                 "@@ -1 +1 @@\n?unknown\n",
                 "@@ -1 +1 @@\n-x\n+y\n\\ No newline nonsense\n"]
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                parse_patch("diff --git a/unit.cpp b/unit.cpp\n"+patch)
            if patch == "@@ -1,2 +1,2 @@\n-x\n+y\n":
                # The explicitly header-free fragment interface permits
                # clipped equal trailing context, unlike a complete diff.
                self.assertEqual(1, len(split_change_parts(patch, by_hunk=True)))
                continue
            for by_hunk in (False, True):
                with self.subTest(patch=patch, by_hunk=by_hunk), self.assertRaises(ValueError):
                    split_change_parts(patch, by_hunk=by_hunk)
        for by_hunk in (False, True):
            with self.assertRaises(ValueError):
                split_change_parts("@@ -1,2 +1 @@\n-x\n+y\n", by_hunk=by_hunk)

    def test_context_and_hunk_boundaries_keep_original_part_semantics(self):
        patch = "@@ -1,3 +1,3 @@\n-x\n+y\n context\n-a\n+b\n@@ -8 +8 @@\n-c\n+d\n"
        self.assertEqual(2, len(split_change_parts(patch, by_hunk=True)))
        self.assertEqual(3, len(split_change_parts(patch, by_hunk=False)))
        self.assertEqual(3, _file_record("unit.cpp", patch)["endpoint_mass"])
        marked = "@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n"
        self.assertEqual(1, len(split_change_parts(marked, by_hunk=True)))
        self.assertEqual(2, len(split_change_parts(marked, by_hunk=False)))


class EventUniverseContracts(unittest.TestCase):
    def test_total_injection_with_uncovered_positive_target_is_rejected(self):
        left = History("left", (Commit("c", "A", (Atom("p", "f", 1, "A"),)),))
        right = replace(left, history_id="right", commits=(Commit("c", "A", (
            Atom("renamed", "f", 1, "A"), Atom("extra", "f", 1, "A"))),))
        result = certify_rewrite(left, right, event_map=(("p", "renamed"),))
        self.assertFalse(result.valid)
        self.assertIn("unmapped rewritten structural events: extra", result.reasons)

    def test_bijection_covers_only_positive_surface_and_allows_empty_surface(self):
        left = History("left", (Commit("c", "A", (Atom("p", "f", 1, "A"),
            Atom("cosmetic", "style", 0, None, kind="cosmetic"))),))
        right = History("right", (Commit("d", "A", (Atom("q", "f", 1, "A"),)),))
        self.assertTrue(certify_rewrite(left, right, event_map=(("p", "q"),)).valid)
        self.assertTrue(certify_rewrite(left.restrict_atoms(("cosmetic",)),
                                       right.restrict_atoms(()), event_map=()).valid)


if __name__ == "__main__":
    unittest.main()
