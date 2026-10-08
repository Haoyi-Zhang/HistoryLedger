from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReplayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]
        self.replayer = self.root / "replayer" / "replay.py"

    def replay_module(self):
        spec = importlib.util.spec_from_file_location("literal_replay", self.replayer)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_literal_nonblank_labels_survive_export_and_replay(self):
        from rivet.certificate import validate_history
        from rivet.experiments import export_ledger
        from rivet.model import Atom, Commit, History
        history = History(" h ", (Commit("c", " A ", (
            Atom(" e ", " f ", 1, " A "),
        )),))
        self.assertTrue(validate_history(history).valid)
        with tempfile.TemporaryDirectory() as directory:
            ledger, expected = Path(directory) / "ledger.csv", Path(directory) / "expected.json"
            export_ledger([history], ledger, expected)
            code, payload, stderr = self.run_replayer(ledger, expected)
            self.assertEqual(0, code, stderr)
            self.assertEqual("PASS", payload["status"])

    def test_whitespace_label_changes_are_not_normalized_away(self):
        module = self.replay_module()
        row = dict(history_id="h", atom_id="e", entity="f", weight="1",
                   origin="A", kind="structural")
        expected = module.replay([row])
        for field in ("history_id", "atom_id", "entity", "origin"):
            with self.subTest(field=field):
                changed = module.replay([{**row, field: " " + row[field] + " "}])
                self.assertTrue(module.compare(changed, expected))

    def test_export_rejects_must_link_before_writing(self):
        from rivet.experiments import export_ledger
        from rivet.model import Atom, Commit, History
        from rivet.score import analyze_history
        history = History("h", (Commit("c", "A", (
            Atom("e1", "f1", 1, "A"),
            Atom("e2", "f2", 1, "A-alt"),
            Atom("e3", "f3", 1.5, "B"),
        )),), must_link=(("A", "A-alt"),))
        self.assertEqual({"A": 2000000000000, "B": 1500000000000},
                         analyze_history(history).score_units)
        with tempfile.TemporaryDirectory() as directory:
            ledger, expected = Path(directory)/"ledger.csv", Path(directory)/"expected.json"
            with self.assertRaisesRegex(ValueError, "singleton actor classes"):
                export_ledger([history], ledger, expected)
            self.assertFalse(ledger.exists())
            self.assertFalse(expected.exists())

    def test_export_rejects_may_link_before_writing(self):
        from rivet.experiments import export_ledger
        from rivet.model import Atom, Commit, History
        from rivet.score import analyze_history
        history = History("h", (Commit("c", "A", (
            Atom("e1", "f1", 1, "A"), Atom("e2", "f2", 1.5, "B"),
        )),), may_link=(("A", "B"),))
        self.assertEqual("PARTIAL_ALIAS_ABSTENTION", analyze_history(history).status)
        with tempfile.TemporaryDirectory() as directory:
            ledger, expected = Path(directory)/"ledger.csv", Path(directory)/"expected.json"
            with self.assertRaisesRegex(ValueError, "singleton actor classes"):
                export_ledger([history], ledger, expected)
            self.assertFalse(ledger.exists())
            self.assertFalse(expected.exists())

    def test_padded_kind_is_rejected(self):
        module = self.replay_module()
        actual = module.replay([dict(history_id="h", atom_id="e", entity="f",
                                    weight="1", origin="A", kind=" structural ")])
        self.assertTrue(actual["errors"])

    def test_whitespace_only_cosmetic_origin_is_rejected(self):
        module = self.replay_module()
        actual = module.replay([dict(history_id="h", atom_id="e", entity="f",
                                    weight="0", origin=" ", kind="cosmetic")])
        self.assertTrue(actual["errors"])

    def run_replayer(self, ledger: Path, expected: Path | None = None) -> tuple[int, dict, str]:
        command = [sys.executable, str(self.replayer), str(ledger)]
        if expected is not None:
            command.extend(("--expected", str(expected)))
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.returncode, json.loads(completed.stdout), completed.stderr

    def write_rows(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=("history_id", "atom_id", "entity", "weight", "origin", "kind"),
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_public_ledger_passes(self) -> None:
        code, payload, stderr = self.run_replayer(
            self.root / "data" / "canonical_ledgers.csv",
            self.root / "data" / "canonical_expected.json",
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual("PASS", payload["status"])
        self.assertEqual(40, payload["history_count"])

    def test_expected_ledger_uses_exact_decimal_strings(self) -> None:
        expected = json.loads(
            (self.root / "data" / "canonical_expected.json").read_text(encoding="utf-8")
        )
        self.assertTrue(all(isinstance(row[3], str) for row in expected["rows"]))
        self.assertTrue(
            all(
                isinstance(value, str)
                for history_scores in expected["scores"].values()
                for value in history_scores.values()
            )
        )

    def test_nonfinite_weight_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.csv"
            self.write_rows(
                ledger,
                [{"history_id": "h", "atom_id": "e", "entity": "f", "weight": "NaN", "origin": "A", "kind": "structural"}],
            )
            code, payload, _stderr = self.run_replayer(ledger)
            self.assertNotEqual(0, code)
            self.assertEqual("FAIL", payload["status"])
            self.assertIn("nonfinite", " ".join(payload["errors"]))

    def test_extreme_weight_is_rejected_with_a_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.csv"
            self.write_rows(
                ledger,
                [{"history_id": "h", "atom_id": "e", "entity": "f", "weight": "1e100", "origin": "A", "kind": "structural"}],
            )
            code, payload, _stderr = self.run_replayer(ledger)
            self.assertNotEqual(0, code)
            self.assertEqual("FAIL", payload["status"])
            self.assertTrue(payload["errors"])

    def test_nonzero_cosmetic_and_unknown_kind_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            cases = (
                {"history_id": "h", "atom_id": "e", "entity": "f", "weight": "1", "origin": "A", "kind": "cosmetic"},
                {"history_id": "h", "atom_id": "e", "entity": "f", "weight": "1", "origin": "A", "kind": "other"},
            )
            for index, row in enumerate(cases):
                with self.subTest(case=index):
                    ledger = temporary_path / f"ledger-{index}.csv"
                    self.write_rows(ledger, [row])
                    code, payload, _stderr = self.run_replayer(ledger)
                    self.assertNotEqual(0, code)
                    self.assertEqual("FAIL", payload["status"])

    def test_large_aggregate_uses_exact_scaled_accumulation(self) -> None:
        rows = [
            {
                "history_id": "h",
                "atom_id": f"e{index}",
                "entity": f"f{index}",
                "weight": "1e47",
                "origin": "A",
                "kind": "structural",
            }
            for index in range(100)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.csv"
            self.write_rows(ledger, rows)
            code, payload, stderr = self.run_replayer(ledger)
            self.assertEqual(0, code, stderr)
            self.assertEqual("PASS", payload["status"])
            self.assertEqual(100, payload["event_count"])

    def test_decimal_totals_do_not_depend_on_row_order(self) -> None:
        rows = [
            {"history_id": "h", "atom_id": "e1", "entity": "f1", "weight": "10000000000000000", "origin": "A", "kind": "structural"},
            {"history_id": "h", "atom_id": "e2", "entity": "f2", "weight": "1", "origin": "A", "kind": "structural"},
            {"history_id": "h", "atom_id": "e3", "entity": "f3", "weight": "1", "origin": "A", "kind": "structural"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            left = Path(temporary) / "left.csv"
            right = Path(temporary) / "right.csv"
            self.write_rows(left, rows)
            self.write_rows(right, list(reversed(rows)))
            left_code, left_payload, _ = self.run_replayer(left)
            right_code, right_payload, _ = self.run_replayer(right)
            self.assertEqual(0, left_code)
            self.assertEqual(0, right_code)
            self.assertEqual(left_payload, right_payload)

    def test_missing_columns_fail_with_a_structured_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            ledger = Path(temporary) / "ledger.csv"
            ledger.write_text("history_id,atom_id\nh,e\n", encoding="utf-8")
            code, payload, stderr = self.run_replayer(ledger)
            self.assertNotEqual(0, code, stderr)
            self.assertEqual("FAIL", payload["status"])
            self.assertIn("missing columns", " ".join(payload["errors"]))


if __name__ == "__main__":
    unittest.main()
