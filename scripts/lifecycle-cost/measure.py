"""Windows-only lifecycle measurement; enter through run-measurement.ps1."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
import harness as h

GATE_NAME = "P022_COST_RESOURCE_ENTRY"
GATE_VALUE = "four-slot-wrapper-v1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def cpu_model(registry=None):
    source = r"HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0:ProcessorNameString"
    try:
        if registry is None:
            import winreg as registry
        with registry.OpenKey(registry.HKEY_LOCAL_MACHINE,
                              r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            value, _ = registry.QueryValueEx(key, "ProcessorNameString")
        h.require(isinstance(value, str) and bool(value.strip()), "blank/non-string ProcessorNameString")
        return {"value": value.strip(), "source": source, "reason": None}
    except (OSError, ImportError, ValueError) as error:
        return {"value": None, "source": source, "reason": repr(error)}


class HostMemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD)] + [
        (name, ctypes.c_uint64) for name in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]


def host_load_between(before, after):
    """All-application CPU activity over a bracketing interval, not child CPU."""
    result = {"cpu_busy_percent": None,
              "scope": "GetSystemTimes: all processors at <=64 CPUs, calling primary processor group above 64",
              "boundary": "coordinator snapshots bracket work and observation overhead; includes other applications"}
    a, b = before["cpu_times_100ns"], after["cpu_times_100ns"]
    if a["status"] != "AVAILABLE" or b["status"] != "AVAILABLE":
        result["reason"] = "host CPU counters unavailable; see raw snapshots"
        return result
    delta = {key: b[key] - a[key] for key in ("idle", "kernel_including_idle", "user")}
    total = delta["kernel_including_idle"] + delta["user"]
    result["delta_100ns"] = delta
    if total <= 0 or any(value < 0 for value in delta.values()) or delta["idle"] > total:
        result["reason"] = "nonpositive or inconsistent counter interval; no inferred load"
    else:
        result.update(cpu_busy_percent=100 * (total - delta["idle"]) / total, reason=None)
    return result


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("PageFaultCount", w.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def ticks(filetime):
    return (int(filetime.dwHighDateTime) << 32) | int(filetime.dwLowDateTime)


class WinStats:
    def __init__(self):
        h.require(os.name == "nt", "Windows measurement only; no guessed fallback memory")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.kernel.GetCurrentProcess.argtypes = []
        self.kernel.GetCurrentProcess.restype = w.HANDLE
        self.kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = w.BOOL
        self.kernel.GetSystemTimes.argtypes = [ctypes.POINTER(w.FILETIME)] * 3
        self.kernel.GetSystemTimes.restype = w.BOOL
        self.kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(HostMemoryStatus)]
        self.kernel.GlobalMemoryStatusEx.restype = w.BOOL
        self.psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(MemoryCounters), w.DWORD]
        self.psapi.GetProcessMemoryInfo.restype = w.BOOL

    def host_snapshot(self):
        snapshot = {"utc": utc_now()}
        idle, kernel, user = (w.FILETIME() for _ in range(3))
        if self.kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            snapshot["cpu_times_100ns"] = {"status": "AVAILABLE", "idle": ticks(idle),
                                           "kernel_including_idle": ticks(kernel), "user": ticks(user)}
        else:
            snapshot["cpu_times_100ns"] = {"status": "UNAVAILABLE", "winerror": ctypes.get_last_error(),
                                           "reason": "GetSystemTimes failed",
                                           "idle": None, "kernel_including_idle": None, "user": None}
        memory = HostMemoryStatus()
        memory.dwLength = ctypes.sizeof(memory)
        if self.kernel.GlobalMemoryStatusEx(ctypes.byref(memory)):
            snapshot["physical_memory"] = {"status": "AVAILABLE", "approximate_used_percent": int(memory.dwMemoryLoad),
                                            "total_bytes": int(memory.ullTotalPhys),
                                            "available_bytes": int(memory.ullAvailPhys)}
        else:
            snapshot["physical_memory"] = {"status": "UNAVAILABLE", "winerror": ctypes.get_last_error(),
                                            "reason": "GlobalMemoryStatusEx failed",
                                            "approximate_used_percent": None, "total_bytes": None, "available_bytes": None}
        snapshot["utc_after_queries"] = utc_now()
        return snapshot

    def memory(self, handle=None):
        handle = self.kernel.GetCurrentProcess() if handle is None else handle
        value = MemoryCounters()
        value.cb = ctypes.sizeof(value)
        if not self.psapi.GetProcessMemoryInfo(handle, ctypes.byref(value), value.cb):
            return {"status": "UNAVAILABLE", "winerror": ctypes.get_last_error()}
        return {"status": "AVAILABLE", "peak_working_set_bytes": int(value.PeakWorkingSetSize),
                "working_set_bytes": int(value.WorkingSetSize),
                "peak_private_commit_bytes": int(value.PeakPagefileUsage),
                "private_commit_bytes": int(value.PrivateUsage)}

    def exited_times(self, handle):
        created, exited, kernel, user = (w.FILETIME() for _ in range(4))
        if not self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                           ctypes.byref(kernel), ctypes.byref(user)):
            return {"status": "UNAVAILABLE", "winerror": ctypes.get_last_error(),
                    "wall_ns": None, "cpu_ns": None}
        creation, exit_, system, application = map(ticks, (created, exited, kernel, user))
        return {"status": "AVAILABLE", "creation_filetime_100ns": creation,
                "exit_filetime_100ns": exit_, "kernel_100ns": system, "user_100ns": application,
                "wall_ns": (exit_ - creation) * 100, "cpu_ns": (system + application) * 100}


def scheduled():
    for round_index, arms in enumerate((("ledger", "rivet"), ("rivet", "ledger"),
                                        ("rivet", "ledger"), ("ledger", "rivet")), 1):
        for cache in ("cold", "warm"):
            for arm in arms:
                yield round_index, cache, arm


def child(api_stats, protocol, args):
    # This flag is a cooperative entry restriction, not an independent lease attestation.
    h.require(os.environ.get(GATE_NAME) == GATE_VALUE, "use four-slot wrapper entry")
    return h.execute(protocol, args.arm, args.cache, args.output_dir, measured=True, memory=api_stats.memory)


def native_interpreter():
    # A Windows venv python.exe may be only a redirector. Its process HANDLE
    # would account for the launcher rather than the interpreter doing work.
    value = getattr(sys, "_base_executable", None)
    h.require(bool(value), "CPython base executable is required for process accounting")
    path = Path(value).resolve()
    h.require(path.is_file(), "CPython base executable is unavailable")
    return path


def validate_process_accounting(row):
    result = row["child_result"]
    identity = result.get("process_identity", {})
    h.require(identity.get("pid") == row["launched_pid"] and
              identity.get("ppid") == row["launched_parent_pid"],
              "measured HANDLE does not identify the Python payload process")
    phases = list(result.get("setup_phases", {}).values())
    phases += [v for p in result["passes"] for v in p.get("phases", {}).values()]
    phase_cpu = sum(x["cpu_ns"] for x in phases)
    times = row["whole_child_times"]
    if times["status"] == "AVAILABLE":
        h.require(times["cpu_ns"] >= phase_cpu,
                  "whole-process CPU is smaller than its disjoint payload phases")
    snapshots = [p["memory_snapshot"] for p in result["passes"]
                 if p.get("memory_snapshot", {}).get("status") == "AVAILABLE"]
    memory = row["memory"]
    if snapshots:
        child_peaks = {key: max(x[key] for x in snapshots)
                       for key in ("peak_working_set_bytes", "peak_private_commit_bytes")}
        memory["child_pass_peak_counters"] = child_peaks
        for key, value in child_peaks.items():
            memory[key] = max(memory.get(key) or 0, value)
        memory["status"] = "AVAILABLE"
        end = memory["after_exit_query"]
        consistent = end["status"] == "AVAILABLE" and all(
            end[key] >= memory[key] for key in child_peaks)
        memory["after_exit_peak_consistent"] = consistent
        memory["boundary"] = ("OS process peak queried after exit" if consistent else
            "same-process lifetime-so-far through last live or payload snapshot; final teardown peak not verified")
    return {"status": "PASS", "payload_pid_matches_handle": True,
            "disjoint_phase_cpu_ns": phase_cpu,
            "whole_cpu_covers_phases": times["status"] == "AVAILABLE"}


def one_child(api_stats, root, round_index, cache, arm, timeout_seconds, artifact_root):
    name = "round-%d-%s-%s" % (round_index, cache, arm)
    out = root / name
    command = [str(native_interpreter()), "-I", "-B", str(Path(__file__).resolve()), "--child",
               "--arm", arm, "--cache", cache, "--artifact-root", str(artifact_root),
               "--output-dir", str(out)]
    command_template = ["python", "-I", "-B", "measure.py", "--child", "--arm", arm,
                        "--cache", cache, "--artifact-root", "<artifact-root>",
                        "--output-dir", "<output-dir>/" + name]
    row = {"round": round_index, "cache": cache, "arm": arm, "command": command_template,
           "timeout_seconds": timeout_seconds, "status": "FAIL"}
    row["host_before"] = api_stats.host_snapshot()
    peaks, live_successes, live_failures = {}, 0, 0
    last_live, after_exit = None, None
    with (root / (name + ".log")).open("xb") as log:
        started = time.perf_counter_ns()
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, cwd=str(HERE), shell=False)
        row["launched_pid"] = process.pid
        row["launched_parent_pid"] = os.getpid()
        row["child_interpreter_selection"] = "CPython base executable, not a virtual-environment redirector"
        # CPython's retained Windows process HANDLE includes query/VM-read rights.
        handle = int(process._handle)
        try:
            while process.poll() is None:
                sample = api_stats.memory(handle)
                if sample["status"] == "AVAILABLE":
                    live_successes += 1
                    last_live = sample
                    for metric in ("peak_working_set_bytes", "peak_private_commit_bytes"):
                        peaks[metric] = max(peaks.get(metric, 0), sample[metric])
                else:
                    live_failures += 1
                if time.perf_counter_ns() - started > timeout_seconds * 1_000_000_000:
                    row["timeout"] = True
                    process.kill()
                    break
                time.sleep(0.005)
            process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise
        finally:
            # Take the wall envelope before querying resources / parsing results.
            row["parent_launch_to_wait_envelope_ns"] = time.perf_counter_ns() - started
            row["exit_code"] = process.returncode
            row["whole_child_times"] = api_stats.exited_times(handle)
            after_exit = api_stats.memory(handle)
            # Some systems no longer expose useful counters after termination.
            # An OS lifetime peak cannot legitimately decrease from a live query.
            after_valid = after_exit["status"] == "AVAILABLE" and all(
                after_exit[metric] >= peaks.get(metric, 0)
                for metric in ("peak_working_set_bytes", "peak_private_commit_bytes"))
            if after_valid:
                for metric in ("peak_working_set_bytes", "peak_private_commit_bytes"):
                    peaks[metric] = max(peaks.get(metric, 0), after_exit[metric])
            row["memory"] = {
                "status": "AVAILABLE" if peaks else "UNAVAILABLE",
                "boundary": ("OS process peak queried after exit" if after_valid
                             else "whole-process lifetime-so-far through last live sample; final teardown peak not verified"),
                "peak_working_set_bytes": peaks.get("peak_working_set_bytes"),
                "peak_private_commit_bytes": peaks.get("peak_private_commit_bytes"),
                "live_successful_queries": live_successes, "live_failed_queries": live_failures,
                "last_live": last_live, "after_exit_query": after_exit,
                "after_exit_peak_consistent": after_valid,
            }
            row["host_after"] = api_stats.host_snapshot()
            row["host_load_during_bracketing_interval"] = host_load_between(row["host_before"], row["host_after"])
    if (out / "result.json").is_file():
        row["child_result"] = json.loads((out / "result.json").read_text(encoding="utf-8"))
    if row["exit_code"] == 0 and row.get("child_result", {}).get("status") == "PASS":
        try:
            row["process_accounting"] = validate_process_accounting(row)
            row["status"] = "PASS"
        except ValueError as error:
            row["error"] = str(error)
            row["process_accounting"] = {"status": "FAIL", "error": str(error)}
    else:
        row["error"] = "child failed; retain its log and partial bundle files; do not retry"
    h.write_json(root / (name + ".measurement.json"), row)
    return row


def summarize(rows):
    pairs = []
    for round_index in range(1, 5):
        for cache in ("cold", "warm"):
            selected = {r["arm"]: r for r in rows if r["round"] == round_index and r["cache"] == cache}
            if len(selected) != 2 or any(r["status"] != "PASS" for r in selected.values()):
                continue
            left, right = selected["ledger"], selected["rivet"]
            lp, rp = left["child_result"]["passes"], right["child_result"]["passes"]
            h.require([p["bundle_sha256"] for p in lp] == [p["bundle_sha256"] for p in rp],
                      "paired arms differ on serialized contract")
            differences = {}
            for metric in ("wall_ns", "cpu_ns"):
                a, b = left["whole_child_times"].get(metric), right["whole_child_times"].get(metric)
                differences[metric] = None if a is None or b is None else a - b
            for metric in ("peak_working_set_bytes", "peak_private_commit_bytes"):
                a, b = left["memory"].get(metric), right["memory"].get(metric)
                differences[metric] = None if a is None or b is None else a - b
            pairs.append({"round": round_index, "cache": cache,
                          "ledger_minus_rivet": differences,
                          "work": "400 pairs" if cache == "cold" else "800 pairs including paid warmup"})
    medians = {}
    for cache in ("cold", "warm"):
        complete = [p for p in pairs if p["cache"] == cache]
        medians[cache] = {}
        for metric in ("wall_ns", "cpu_ns", "peak_working_set_bytes", "peak_private_commit_bytes"):
            values = [p["ledger_minus_rivet"][metric] for p in complete]
            medians[cache][metric] = statistics.median(values) if len(values) == 4 and None not in values else None
    return {"paired_raw_differences": pairs, "median_signed_differences_if_four_pairs": medians,
            "direction": "positive = ledger higher cost; no observation excluded for being adverse",
            "inference": "descriptive on retained normalized inputs on this host only; no deployment or gain claim"}


def resource_wrapper_info(path, protocol):
    path = Path(path).resolve()
    raw = path.read_bytes()
    canonical = raw.decode("utf-8-sig").replace("\r\n", "\n").rstrip("\n") + "\n"
    digest = h.hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    h.require(digest == protocol["resource_wrapper"]["sha256_lf"],
              "resource wrapper differs from bundled four-slot implementation")
    return {"file": "run-with-resources.ps1", "source_sha256": h.hashlib.sha256(raw).hexdigest(),
            "sha256_lf": digest, "equivalent_to_bundled": True}


def campaign(api_stats, protocol, output_dir, wrapper_info):
    h.require(os.environ.get(GATE_NAME) == GATE_VALUE, "use run-measurement.ps1 under four-slot wrapper")
    h.verify_sources(protocol)
    root = h.output_path(output_dir)
    root.mkdir(parents=True, exist_ok=False)
    h.write_json(root / "predeclared-protocol.json", h.public_protocol(protocol))
    report = {"status": "INCOMPLETE", "timing_run": True,
              "started_utc": utc_now(),
              "protocol_sha256": h.hashlib.sha256(h.PROTOCOL.read_bytes()).hexdigest(),
              "resource_entry": {"mode": "measurement", "slots_required": 4,
                                 "wrapper": wrapper_info,
                                 "attestation": "entry/wrapper call chain; not independently sensed by child"},
              "environment": {"python": sys.version, "executable": Path(sys.executable).name,
                              "platform": platform.platform(), "machine": platform.machine(),
                              "logical_cpus": os.cpu_count(), "concurrent_children": 1,
                              "cpu_model": cpu_model(),
                              "resource_lock_scope": "four slots coordinate participating HistoryLedger cost jobs only; other applications and OS work are not excluded",
                              "host_before": api_stats.host_snapshot(),
                              "os_file_cache": "uncontrolled; no cold-disk claim"}, "samples": []}
    try:
        for round_index, cache, arm in scheduled():
            row = one_child(api_stats, root, round_index, cache, arm, protocol["child_timeout_seconds"], protocol["artifact_root"])
            report["samples"].append(row)
            if row["status"] != "PASS":
                raise RuntimeError("failed child; fixed campaign stopped without retry")
        h.verify_sources(protocol)
        report["analysis"] = summarize(report["samples"])
        h.require(len(report["analysis"]["paired_raw_differences"]) == 8, "incomplete paired schedule")
        report["status"] = "PASS"
    except BaseException as error:
        report["status"] = "FAIL_OR_INTERRUPTED"
        report["error"] = repr(error)
        raise
    finally:
        report["finished_utc"] = utc_now()
        report["environment"]["host_after"] = api_stats.host_snapshot()
        report["environment"]["host_load_over_campaign"] = host_load_between(
            report["environment"]["host_before"], report["environment"]["host_after"])
        h.write_json(root / "campaign.json", report)
    print(json.dumps({"status": report["status"], "children": len(report["samples"]),
                      "claim": "raw descriptive cost observations"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--child", action="store_true")
    group.add_argument("--campaign", action="store_true")
    parser.add_argument("--arm", choices=h.ARMS)
    parser.add_argument("--cache", choices=("cold", "warm"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resource-wrapper", type=Path, default=HERE / "run-with-resources.ps1")
    args = parser.parse_args()
    h.require(os.environ.get(GATE_NAME) == GATE_VALUE, "measurement gate absent; use four-slot wrapper")
    protocol = h.load_protocol(args.artifact_root)
    wrapper_info = resource_wrapper_info(args.resource_wrapper, protocol) if args.campaign else None
    stats = WinStats()
    if args.child:
        child(stats, protocol, args)
    else:
        campaign(stats, protocol, args.output_dir, wrapper_info)


if __name__ == "__main__":
    main()
