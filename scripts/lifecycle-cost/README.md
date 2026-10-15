# Equal-information lifecycle cost experiment

This directory runs a fixed comparison of the existing Rivet and ordinary provenance-ledger implementations. It uses CPython 3.10+ and the artifact's `src/rivet` modules and `data/public_windows.json`. No additional Python packages or network access are required. Whole-process measurements use Windows APIs; no native Linux measurement is implied.

## Inputs and output contract

The input is the retained normalized event dataset: 40 eight-commit windows, 610 positive events, from one noVNC history. It contains numeric events and pseudonymous labels, not source snapshots or independently annotated origin/identity truth. Input preparation here means reading/parsing that JSON, constructing histories, applying the existing transformations and constructing total structural event maps. It does not include unavailable source reconstruction or origin acquisition.

For every pair, both original and transformed endpoints are recomputed. The ten transformations, retained input order, sample size and order are fixed in `protocol.json`: split, certified squash, independent reorder, formatting, empty padding, file move, event renaming, certified alias split, ambiguous alias split and origin-erasing squash. Each pass contains 400 pairs, with 320 accepted rewrite comparisons, 40 alias abstentions and 40 origin abstentions. Refusals remain part of the workload.

Both arms receive the same events, origins, decimal weights, identity/entity declarations and event maps. They emit integer-unit scores, decision status, active may-components over must-link roots, actor/entity buckets and exact all-target competition-rank intervals. One weight unit is 1e-12 of the frozen event-weight scale, not a time unit. The exact rank component cap remains seven; empty/origin-abstaining scores and oversize components have explicit unavailable/refused results.

The ledger natively returns scores, buckets, components and status. Rivet runs `analyze_history(include_pairwise=False)` and pays for the bucket/component projection in `harness.py`; its native ordering and alias-interval work is not free merely because the common format omits those fields. This is a common projected-service contract, not identical native API output. Both arms use the same rank backend and rewrite validator.

Each pair is serialized into the same v1 JSON bundle: full endpoint inputs and relations, total structural event map, both common outputs and certificate result. The stream is written, flushed/fsynced once per pass, reopened and parsed. The receiver reconstructs both endpoints, reruns `certify_rewrite`, recomputes the common output via the existing ledger and shared rank routine, and compares exact values. This shared-code receiver is not independent source authentication. The scalar replayer does not check identity relations and is not used as a whole-certificate checker.

## Fixed schedule and cost boundaries

Four paired rounds use ledger/Rivet, Rivet/ledger, Rivet/ledger, ledger/Rivet order. Each round runs cold then warm: 16 fresh sequential child processes, 24 total passes, 9,600 pairs and 19,200 producer endpoint computations, plus both receiver endpoints per pair. Each child has a 120-second timeout. A failure stops the campaign, retains partial evidence and is not retried. There is no pilot-based tuning, selective rerun or sample replacement.

Every child clears the exact-rank memoization cache once before pass 1. A cold child runs one complete batch, with natural intra-batch reuse. A warm child pays for a complete first batch and then repeats the entire pipeline in a second batch while retaining the cache. Whole-child warm totals include both passes; pass 2 is separately labelled reuse and is not a full-lifecycle denominator. Cache hits/misses/entries are retained at producer/receiver boundaries. Filesystem and hardware caches are uncontrolled, so cold does not mean cold disk.

Both arms import the same implementation closure and verify pinned source/input files. Named phases cover input preparation, transformation/map construction, both endpoint analyses/projections, both rank calls, certificate production, serialization/write/fsync and receiver read/parse/reconstruction/check. The whole-child CPU/wall boundary additionally includes interpreter startup/imports, all paid warmup, result writes and process exit. Parent coordinator setup is outside the child denominator.

`GetProcessTimes` provides raw creation/exit/user/kernel 100-ns counts, with derived nanoseconds, and the parent also records a monotonic launch-to-wait envelope. CPU includes all child threads; no descendant process is launched by the workload. Phase times are supplementary and do not replace the whole-child metric.

The coordinator launches CPython's base executable directly. Each payload returns its process and parent identifiers, which must match the launched process and coordinator before resource observations are accepted. Whole-process CPU must cover the disjoint recorded phase CPU. Child-side peak-memory snapshots are joined only after this identity check, and an after-exit counter that falls below an observed lifetime peak is treated as an unavailable final peak.

`GetProcessMemoryInfo` provides actual OS process peak working-set bytes and private-commit bytes, not Python-only allocation counts. Working set includes shared and private resident pages; private commit is not resident RAM or physical pagefile traffic. The coordinator queries lifetime-so-far peaks while the child lives and attempts an after-exit query. If the latter fails or decreases inconsistently, the report explicitly limits the boundary to the last live sample and does not claim a verified final-teardown peak. Missing counters are null with errors, not zero. No interpreter baseline is subtracted.

Environment metadata records `ProcessorNameString` from the CPU registry (null with reason on failure), real timezone-aware UTC, and raw `GetSystemTimes`/`GlobalMemoryStatusEx` host snapshots. Kernel time includes idle, so host CPU busy percentage is derived only from valid before/after deltas as `(kernel + user - idle) / (kernel + user) * 100`. This bracketing activity includes other applications and observation overhead; on systems above 64 processors, the CPU API covers the calling primary processor group. The resource lock coordinates this project's participating cost jobs, not unrelated applications or operating-system activity.

All four raw paired observations per condition are retained. Signed differences are ledger minus Rivet; positive means ledger cost is higher. Medians are descriptive, require four complete pairs, and do not pool cold with warm. Shared checking, adverse costs, cache growth, absolute totals and serialization bytes are not removed to infer a gain. These measurements concern the retained normalized inputs on the measured host, not natural deployment performance or a broad-corpus scalability result.

## Running and relocating

Keep all seven files in this directory together, without modifying their bytes after measurement. `protocol.json` pins the consumed artifact sources/data and these scripts. Artifact location and fresh output directory are mandatory command-line arguments; outputs must be outside this script directory. The same files can later be installed in an artifact and rerun against the pinned inputs without path edits. Result metadata uses portable command templates and source bindings rather than baking machine-specific absolute paths into the protocol.

For example, if this directory is installed as `artifact/scripts/lifecycle-cost`, run from this directory in PowerShell. Choose fresh directories for every distinct invocation:

```powershell
$python = (Get-Command python).Source
& $python -I -B .\test_harness.py --artifact-root ..\.. --integration-output-dir ..\..\..\cost-runs\correctness-001
& $python -I -B -O .\test_harness.py --artifact-root ..\..
.\run-measurement.ps1 -ArtifactRoot ..\.. -OutputDir ..\..\..\cost-runs\measurement-001 -PythonExecutable $python -Run
```

Correctness execution disables phase clocks, patches duration clocks to fail on use, and tests resource arithmetic with fake APIs; it does not collect timing or host-load observations. Both arms' two-pass correctness outputs must match. Measurement is a separate opt-in entry.

`run-measurement.ps1` calls the bundled `run-with-resources.ps1` in measurement mode. The wrapper must acquire all four project tokens from `Local\HistoryLedgerCostResourcePool`, using `Local\HistoryLedgerCostResourceGate`, before starting the coordinator; busy returns exit 75 and produces no sample. An optional `-ResourceWrapper` can select another copy only if its text is identical after line-ending normalization. The package is self-contained. The cooperative environment marker is not an independent lock attestation.

The measurement output directory contains the exact predeclared protocol copy, per-child stream/result/measurement files and the complete `campaign.json` with raw observations, availability/errors, paired differences, UTC and host context. Install these results together with the measured source bytes; do not replace the implementation or select new repetitions after observing cost.

Windows API definitions: [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes), [process memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex), [GetSystemTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getsystemtimes), and [GlobalMemoryStatusEx](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-globalmemorystatusex).
