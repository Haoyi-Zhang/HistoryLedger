from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from rivet.public_patch_experiments import (
    EXPECTED_LANGUAGES,
    _file_record,
    case_rows,
    load_cases,
    run,
)


FIXTURE = Path(__file__).resolve().parents[1] / "external_inputs" / "public_patch_cases.json"
NOTICES = FIXTURE.with_name("THIRD_PARTY_NOTICES.md")


class PublicPatchBoundaryTests(unittest.TestCase):
    def _payload(self) -> dict[str, object]:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, object], directory: Path) -> Path:
        path = directory / "cases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        (directory / "THIRD_PARTY_NOTICES.md").write_bytes(NOTICES.read_bytes())
        return path

    def _reject(self, mutate) -> None:
        payload = copy.deepcopy(self._payload())
        mutate(payload)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(ValueError):
                load_cases(self._write(payload, Path(raw)))

    def test_fixed_corpus_contract(self) -> None:
        payload = load_cases(FIXTURE)
        cases = payload["cases"]
        self.assertEqual(len(cases), 12)
        self.assertEqual({case["language"] for case in cases}, EXPECTED_LANGUAGES)
        self.assertEqual(sum(case.get("control") == "comment_only" for case in cases), 1)
        self.assertEqual(len({case["repository"] for case in cases}), 12)

    def test_row_level_endpoint_certificates(self) -> None:
        rows = case_rows(FIXTURE)
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["endpoint_certificate_valid"] == 1 for row in rows))
        self.assertTrue(all(row["upstream_execution"] == 0 for row in rows))

    def test_comment_control_and_positive_cycles(self) -> None:
        rows = {row["case"]: row for row in case_rows(FIXTURE)}
        control = rows["P07"]
        self.assertEqual(control["control"], "comment_only")
        self.assertEqual(control["endpoint_mass"], 0)
        self.assertEqual(control["cycle_path_mass"], 0)
        positive = [row for row in rows.values() if row["endpoint_mass"] > 0]
        self.assertEqual(len(positive), 11)
        self.assertTrue(all(row["cycle_path_mass"] > 0 for row in positive))

    def test_frozen_summary_and_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "external_inputs").mkdir()
            (root / "external_inputs" / "public_patch_cases.json").write_bytes(FIXTURE.read_bytes())
            (root / "external_inputs" / "THIRD_PARTY_NOTICES.md").write_bytes(NOTICES.read_bytes())
            summary = run(root)
            self.assertEqual(
                summary,
                {
                    "repositories": 12,
                    "cases": 12,
                    "files": 14,
                    "languages": ["C++", "JavaScript", "Python", "Rust", "TypeScript"],
                    "comment_only_controls": 1,
                    "positive_endpoint_cases": 11,
                    "hunk_path_mismatches": 3,
                    "block_path_mismatches": 3,
                    "delete_add_path_mismatches": 8,
                    "positive_cycle_cases": 11,
                    "endpoint_certificates_valid": 12,
                    "upstream_execution": False,
                    "scope": "bounded public production-code patch fragments; descriptive boundary evidence only",
                },
            )
            self.assertTrue((root / "results" / "public_patch_boundary.csv").is_file())
            self.assertTrue((root / "results" / "public_patch_summary.json").is_file())

    def test_endpoint_mass_differs_from_delete_add_path(self) -> None:
        record = _file_record("example.py", "@@ -1 +1 @@\n-value = x\n+value = y")
        self.assertEqual(record["endpoint_mass"], 1)
        self.assertEqual(record["hunk_path_mass"], 1)
        self.assertEqual(record["block_path_mass"], 1)
        self.assertGreater(record["delete_add_path_mass"], record["endpoint_mass"])
        self.assertEqual(record["cycle_path_mass"], 2)

    def test_duplicate_case_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][1].__setitem__("case", "P01"))

    def test_duplicate_repository_rejected(self) -> None:
        def mutate(payload):
            payload["cases"][1]["repository"] = payload["cases"][0]["repository"]
            payload["cases"][1]["repository_url"] = payload["cases"][0]["repository_url"]
        self._reject(mutate)

    def test_non_mit_case_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0].__setitem__("license", "Other"))

    def test_license_metadata_and_notices_are_complete(self) -> None:
        payload = load_cases(FIXTURE)
        notices = NOTICES.read_text(encoding="utf-8")
        self.assertEqual(sum(len(case["copyright_notices"]) for case in payload["cases"]), 13)
        for case in payload["cases"]:
            self.assertIn(case["license_file"], {"LICENSE", "LICENSE.md", "LICENSE.txt"})
            for notice in case["copyright_notices"]:
                self.assertIn(notice, notices)

    def test_invalid_license_path_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0].__setitem__("license_file", "../LICENSE"))

    def test_missing_copyright_notice_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0].__setitem__("copyright_notices", []))

    def test_missing_third_party_notice_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "cases.json"
            path.write_bytes(FIXTURE.read_bytes())
            with self.assertRaisesRegex(ValueError, "third-party notices are missing"):
                load_cases(path)

    def test_escaping_path_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0]["files"][0].__setitem__("path", "../escape.py"))

    def test_non_code_path_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0]["files"][0].__setitem__("path", "notes.txt"))

    def test_oversized_patch_rejected(self) -> None:
        self._reject(
            lambda payload: payload["cases"][0]["files"][0].__setitem__(
                "patch", "@@ -1 +1 @@\n-" + ("a" * 5000) + "\n+b"
            )
        )

    def test_missing_hunk_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][0]["files"][0].__setitem__("patch", "-a\n+b"))

    def test_language_coverage_change_rejected(self) -> None:
        self._reject(lambda payload: payload["cases"][8].__setitem__("language", "Python"))


if __name__ == "__main__":
    unittest.main()
