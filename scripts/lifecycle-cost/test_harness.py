"""Clock-free correctness checks; no TextTestRunner timing or resource queries."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as h


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol = h.load_protocol(cls.artifact_root)
        h.verify_sources(cls.protocol)
        cls.api = h.load_api(cls.protocol)
        data = json.loads((Path(cls.protocol["artifact_root"]) / "data/public_windows.json").read_text(encoding="utf-8"))
        cls.history = cls.api["History"].from_dict(data["histories"][0])

    def test_projections_match_all_ten_variants(self):
        for name in h.TRANSFORMS:
            right, _ = h.prepare_variant(self.api, self.history, name)
            for history in (self.history, right):
                self.assertEqual(h.endpoint(self.api, history, "ledger"), h.endpoint(self.api, history, "rivet"))

    def bundle(self):
        right, mapping = h.prepare_variant(self.api, self.history, "event-map")
        return h.normalized({
            "schema": "p022-cost-bundle-v1", "history_id": self.history.history_id,
            "transformation": "event-map", "left": self.history.to_dict(), "right": right.to_dict(),
            "event_map": mapping,
            "certificate": h.asdict(self.api["certify_rewrite"](self.history, right, event_map=mapping)),
            "left_output": h.add_ranks(self.api, h.endpoint(self.api, self.history, "rivet")),
            "right_output": h.add_ranks(self.api, h.endpoint(self.api, right, "rivet")),
        })

    def test_roundtrip_rejects_score_and_map_tampering(self):
        bundle = self.bundle()
        self.assertTrue(h.check_bundle(self.api, bundle))
        changed = copy.deepcopy(bundle)
        actor = next(iter(changed["right_output"]["score_units"]))
        changed["right_output"]["score_units"][actor] += 1
        with self.assertRaisesRegex(ValueError, "receiver mismatch"):
            h.check_bundle(self.api, changed)
        changed = copy.deepcopy(bundle)
        changed["event_map"].pop()
        with self.assertRaisesRegex(ValueError, "certificate report mismatch"):
            h.check_bundle(self.api, changed)

    def test_abstention_not_mistaken_for_point_ranking(self):
        right, _ = h.prepare_variant(self.api, self.history, "squash-without-origin")
        output = h.add_ranks(self.api, h.endpoint(self.api, right, "ledger"))
        self.assertEqual(output["status"], "ABSTAIN_ORIGIN")
        self.assertEqual(output["rank"]["status"], "UNAVAILABLE")
        self.assertEqual(output["rank"]["intervals"], {})

    def test_rank_cap_refuses_without_exponential_work(self):
        output = {"score_units": {"a%d" % i: i for i in range(8)},
                  "components": [["a%d" % i for i in range(8)]], "status": "PARTIAL_ALIAS_ABSTENTION"}
        with patch.dict(self.api, {"global_rank_diagnostics_units": lambda *a: self.fail("must not search")}):
            self.assertEqual(h.add_ranks(self.api, output)["rank"]["status"], "REFUSED_COMPONENT_CAP")

    def test_disabled_phases_do_not_call_any_clock(self):
        with patch("time.perf_counter_ns", side_effect=AssertionError("clock forbidden")), \
             patch("time.process_time_ns", side_effect=AssertionError("clock forbidden")):
            phases = h.Phases(False)
            with phases.at("a"):
                self.assertEqual(h.encoded({"a": 1}), b'{"a":1}')
            self.assertFalse(phases.values)

    def test_source_drift_fails_closed(self):
        changed = copy.deepcopy(self.protocol)
        key = next(iter(changed["artifact_sha256"]))
        changed["artifact_sha256"][key] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source/input drift"):
            h.verify_sources(changed)

    def test_measurement_gate_and_fixed_schedule_without_measurement(self):
        import measure
        self.assertEqual(len(list(measure.scheduled())), 16)
        for cache in ("cold", "warm"):
            self.assertEqual(sum(c == cache for _, c, _ in measure.scheduled()), 8)
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(sys, "argv", ["measure.py", "--campaign", "--artifact-root", str(self.artifact_root),
                                        "--output-dir", str(h.HERE.parent / "must-not-run")]):
            with self.assertRaisesRegex(ValueError, "measurement gate absent"):
                measure.main()

    def test_windows_time_units_using_fake_api_not_clocks(self):
        import measure
        def fake_api(handle, created, exited, kernel, user):
            for reference, value in zip((created, exited, kernel, user),
                                        ((1 << 32) + 100, (1 << 32) + 150, 3, 7)):
                reference._obj.dwHighDateTime = value >> 32
                reference._obj.dwLowDateTime = value & 0xffffffff
            return 1
        stats = measure.WinStats.__new__(measure.WinStats)
        stats.kernel = type("FakeKernel", (), {"GetProcessTimes": staticmethod(fake_api)})()
        actual = stats.exited_times(123)
        self.assertEqual(actual["wall_ns"], 5000)
        self.assertEqual(actual["cpu_ns"], 1000)
        self.assertEqual(actual["user_100ns"], 7)

    def test_adverse_differences_and_missing_counters_are_retained(self):
        import measure
        rows = []
        for round_index, cache, arm in measure.scheduled():
            amount = 100 if round_index < 3 else 200
            amount = amount if arm == "ledger" else 150
            rows.append({"round": round_index, "cache": cache, "arm": arm, "status": "PASS",
                         "whole_child_times": {"wall_ns": amount, "cpu_ns": amount},
                         "memory": {"peak_working_set_bytes": amount, "peak_private_commit_bytes": amount},
                         "child_result": {"passes": [{"bundle_sha256": "same"}] * (1 if cache == "cold" else 2)}})
        actual = measure.summarize(rows)
        cold = [p["ledger_minus_rivet"]["wall_ns"] for p in actual["paired_raw_differences"] if p["cache"] == "cold"]
        self.assertEqual(cold, [-50, -50, 50, 50])
        self.assertEqual(len(actual["paired_raw_differences"]), 8)
        rows[0]["whole_child_times"]["cpu_ns"] = None
        self.assertIsNone(measure.summarize(rows)["median_signed_differences_if_four_pairs"]["cold"]["cpu_ns"])

    def test_cpu_registry_model_success_and_failure_are_explicit(self):
        import measure
        registry = MagicMock()
        registry.QueryValueEx.return_value = (" Fixture CPU ", 1)
        self.assertEqual(measure.cpu_model(registry)["value"], "Fixture CPU")
        registry.OpenKey.side_effect = PermissionError("fixture access denied")
        missing = measure.cpu_model(registry)
        self.assertIsNone(missing["value"])
        self.assertIn("fixture access denied", missing["reason"])

    def test_host_snapshot_shape_with_fake_counters_only(self):
        import measure
        def fake_system(idle, kernel, user):
            for reference, value in zip((idle, kernel, user), (100, 200, 300)):
                reference._obj.dwLowDateTime = value
            return 1
        def fake_memory(reference):
            self.assertEqual(reference._obj.dwLength, measure.ctypes.sizeof(measure.HostMemoryStatus))
            reference._obj.dwMemoryLoad = 55
            reference._obj.ullTotalPhys = 1000
            reference._obj.ullAvailPhys = 450
            return 1
        stats = measure.WinStats.__new__(measure.WinStats)
        stats.kernel = type("FakeKernel", (), {"GetSystemTimes": staticmethod(fake_system),
                                               "GlobalMemoryStatusEx": staticmethod(fake_memory)})()
        with patch.object(measure, "utc_now", return_value="fixture-not-a-real-host-observation"):
            snapshot = stats.host_snapshot()
        self.assertEqual(snapshot["physical_memory"]["approximate_used_percent"], 55)
        self.assertEqual(snapshot["cpu_times_100ns"]["kernel_including_idle"], 200)
        self.assertEqual(snapshot["utc"], "fixture-not-a-real-host-observation")

    def test_host_load_subtracts_idle_and_keeps_missing_values_null(self):
        import measure
        before = {"cpu_times_100ns": {"status": "AVAILABLE", "idle": 100, "kernel_including_idle": 200, "user": 300}}
        after = {"cpu_times_100ns": {"status": "AVAILABLE", "idle": 140, "kernel_including_idle": 260, "user": 340}}
        self.assertEqual(measure.host_load_between(before, after)["cpu_busy_percent"], 60)
        after["cpu_times_100ns"]["status"] = "UNAVAILABLE"
        unavailable = measure.host_load_between(before, after)
        self.assertIsNone(unavailable["cpu_busy_percent"])
        self.assertTrue(unavailable["reason"])

    def test_runtime_paths_are_not_serialized_into_protocol(self):
        public = h.public_protocol(self.protocol)
        self.assertNotIn("artifact_root", public)
        self.assertNotIn(str(Path(self.artifact_root).resolve()), h.encoded(public).decode("utf-8"))
        import measure
        bundled = measure.resource_wrapper_info(h.HERE / "run-with-resources.ps1", self.protocol)
        self.assertTrue(bundled["equivalent_to_bundled"])
        self.assertNotIn(str(h.HERE), h.encoded(bundled).decode("utf-8"))

    def test_outputs_cannot_modify_frozen_script_directory(self):
        with self.assertRaisesRegex(ValueError, "outside the cost-script directory"):
            h.output_path(h.HERE / "must-not-create")

    def accounting_row(self):
        return {"launched_pid": 11, "launched_parent_pid": 7,
                "whole_child_times": {"status": "AVAILABLE", "cpu_ns": 100},
                "child_result": {"process_identity": {"pid": 11, "ppid": 7},
                    "setup_phases": {"setup": {"cpu_ns": 10}},
                    "passes": [{"phases": {"work": {"cpu_ns": 50}},
                                "memory_snapshot": {"status": "AVAILABLE",
                                    "peak_working_set_bytes": 100,
                                    "peak_private_commit_bytes": 80}}]},
                "memory": {"status": "AVAILABLE", "peak_working_set_bytes": 120,
                           "peak_private_commit_bytes": 90,
                           "after_exit_query": {"status": "AVAILABLE",
                               "peak_working_set_bytes": 120,
                               "peak_private_commit_bytes": 90}}}

    def test_resource_accounting_rejects_launcher_payload_pid_mismatch(self):
        import measure
        row = self.accounting_row()
        row["child_result"]["process_identity"]["pid"] = 12
        with self.assertRaisesRegex(ValueError, "Python payload process"):
            measure.validate_process_accounting(row)

    def test_whole_process_cpu_covers_disjoint_payload_phases(self):
        import measure
        row = self.accounting_row()
        self.assertEqual(measure.validate_process_accounting(row)["disjoint_phase_cpu_ns"], 60)
        row["whole_child_times"]["cpu_ns"] = 59
        with self.assertRaisesRegex(ValueError, "smaller than its disjoint payload phases"):
            measure.validate_process_accounting(row)

    def test_reset_after_exit_memory_keeps_actual_same_process_lower_bound(self):
        import measure
        row = self.accounting_row()
        for key in ("peak_working_set_bytes", "peak_private_commit_bytes"):
            row["memory"][key] = 20
            row["memory"]["after_exit_query"][key] = 20
        measure.validate_process_accounting(row)
        self.assertEqual(row["memory"]["peak_working_set_bytes"], 100)
        self.assertEqual(row["memory"]["peak_private_commit_bytes"], 80)
        self.assertFalse(row["memory"]["after_exit_peak_consistent"])
        self.assertIn("final teardown peak not verified", row["memory"]["boundary"])

    def test_missing_base_interpreter_is_not_silently_replaced_by_redirector(self):
        import measure
        with patch.object(sys, "_base_executable", None):
            with self.assertRaisesRegex(ValueError, "base executable is required"):
                measure.native_interpreter()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--integration-output-dir", type=Path)
    args = parser.parse_args()
    ContractTests.artifact_root = args.artifact_root
    # TestSuite + TestResult avoids TextTestRunner's elapsed-time measurement.
    result = unittest.TestResult()
    with patch("time.perf_counter_ns", side_effect=AssertionError("clock forbidden")), \
         patch("time.process_time_ns", side_effect=AssertionError("clock forbidden")):
        unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests).run(result)
        if result.wasSuccessful() and args.integration_output_dir:
            with patch.object(sys, "argv", ["harness.py", "--correctness",
                                          "--artifact-root", str(args.artifact_root),
                                          "--output-dir", str(args.integration_output_dir)]):
                h.main()
    report = {"tests": result.testsRun, "failures": result.failures, "errors": result.errors,
              "timing_run": False, "integration_requested": args.integration_output_dir is not None,
              "status": "PASS" if result.wasSuccessful() else "FAIL"}
    print(json.dumps(report, default=str))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
