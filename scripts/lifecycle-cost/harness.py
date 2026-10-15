"""P022 fixed-workload core. Correctness mode has no clocks/counters."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "protocol.json"
ARMS = ("ledger", "rivet")
TRANSFORMS = (
    "split", "squash-certified", "reorder-independent", "formatting",
    "empty-commit-padding", "file-move", "event-map", "alias-certified",
    "alias-ambiguous", "squash-without-origin",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def normalized(value):
    return json.loads(encoded(value))


def write_json(path, value):
    with Path(path).open("xb") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def load_protocol(artifact_root):
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    root = Path(artifact_root).resolve()
    require(root.is_dir(), "artifact root must be an existing directory")
    protocol["artifact_root"] = str(root)
    return protocol


def public_protocol(protocol):
    # Runtime locations are CLI parameters, not machine-specific source bindings.
    return {key: value for key, value in protocol.items()
            if key != "artifact_root" and not key.startswith("_")}


def output_path(value):
    out = Path(value).resolve()
    require(not out.is_relative_to(HERE), "output must be outside the cost-script directory")
    return out


def verify_sources(protocol):
    root = Path(protocol["artifact_root"])
    for relative, expected in protocol["artifact_sha256"].items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        require(actual == expected, "source/input drift: " + relative)
    for relative, expected in protocol["harness_sha256"].items():
        actual = hashlib.sha256((HERE / relative).read_bytes()).hexdigest()
        require(actual == expected, "cost harness drift: " + relative)


def load_api(protocol):
    root = Path(protocol["artifact_root"])
    sys.path.insert(0, str(root / "src"))
    # Import both arms in every child, before cache clearing and input loading.
    from rivet.model import History
    from rivet.score import analyze_history
    from rivet.provenance_baseline import provenance_ledger
    from rivet.certificate import certify_rewrite, _relation_roots
    from rivet.numeric import weight_units
    from rivet.global_aliases import global_rank_diagnostics_units, _max_above_pattern
    from rivet import transforms
    return locals()


class Phases:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.values = defaultdict(lambda: {"wall_ns": 0, "cpu_ns": 0, "calls": 0})
        if enabled:
            from time import perf_counter_ns, process_time_ns
            self.wall, self.cpu = perf_counter_ns, process_time_ns

    @contextmanager
    def at(self, name):
        if not self.enabled:
            yield
            return
        wall, cpu = self.wall(), self.cpu()
        try:
            yield
        finally:
            value = self.values[name]
            value["wall_ns"] += self.wall() - wall
            value["cpu_ns"] += self.cpu() - cpu
            value["calls"] += 1


def prepare_variant(api, history, name):
    t = api["transforms"]
    functions = {
        "split": t.split_commits, "squash-certified": t.squash_pairs,
        "reorder-independent": t.reorder_independent,
        "formatting": t.add_cosmetic_padding, "empty-commit-padding": t.add_empty_commits,
        "file-move": t.move_entities, "alias-certified": t.split_alias_certified,
        "alias-ambiguous": t.split_alias_ambiguous, "squash-without-origin": t.squash_cross_origin,
    }
    if name == "event-map":
        return t.rename_event_identifiers(history)
    changed = functions[name](history)
    mapping = tuple((atom.atom_id, atom.atom_id)
                    for atom in history.atoms(include_cosmetic=False))
    return changed, mapping


def endpoint(api, history, arm):
    require(arm in ARMS, "unknown arm")
    if arm == "ledger":
        native = api["provenance_ledger"](history)
        status, scores = native.status, native.score_units
        groups, buckets = native.components, native.attribution_buckets
    else:
        native = api["analyze_history"](history, include_pairwise=False)
        status, scores = native.status, native.score_units
        unresolved = native.aliases.unresolved_components if native.aliases else ()
        grouped = {label for group in unresolved for label in group}
        groups = tuple(sorted((*unresolved, *((label,) for label in scores if label not in grouped))))
        buckets = {}
        if status not in ("MALFORMED_EVIDENCE", "ABSTAIN_ORIGIN"):
            roots = api["_relation_roots"]((history,), lambda h: h.must_link, lambda h: h.aliases())
            entities = api["_relation_roots"]((history,), lambda h: h.entity_equivalence,
                                             lambda h: (a.entity for a in h.atoms()))
            for atom in history.atoms(include_cosmetic=False):
                key = (roots[atom.origin], entities[atom.entity])
                buckets[key] = buckets.get(key, 0) + api["weight_units"](atom.weight)
    return {"status": status, "score_units": scores, "components": normalized(groups),
            "attribution_buckets": [[actor, entity, units]
                                    for (actor, entity), units in sorted(buckets.items())]}


def add_ranks(api, output):
    if not output["score_units"]:
        output["rank"] = {"status": "UNAVAILABLE", "reason": output["status"], "intervals": {}}
    elif any(len(group) > 7 for group in output["components"]):
        output["rank"] = {"status": "REFUSED_COMPONENT_CAP", "cap": 7, "intervals": {}}
    else:
        result = api["global_rank_diagnostics_units"](output["score_units"], output["components"])
        output["rank"] = {"status": "EXACT", "cap": 7, "intervals": normalized(result.intervals)}
    return output


def check_bundle(api, bundle):
    """Shared-code finite bundle receiver; NOT an independent source checker."""
    require(bundle["schema"] == "p022-cost-bundle-v1", "bundle schema")
    left, right = (api["History"].from_dict(bundle[side]) for side in ("left", "right"))
    mapping = tuple(tuple(pair) for pair in bundle["event_map"])
    certificate = api["certify_rewrite"](left, right, event_map=mapping)
    require(normalized(asdict(certificate)) == bundle["certificate"], "certificate report mismatch")
    for side, history in (("left_output", left), ("right_output", right)):
        actual = add_ranks(api, endpoint(api, history, "ledger"))
        require(normalized(actual) == bundle[side], side + " receiver mismatch")
    return certificate.valid


def cache_info(api):
    return api["_max_above_pattern"].cache_info()._asdict()


def run_pass(api, protocol, arm, out, index, phases):
    root = Path(protocol["artifact_root"])
    with phases.at("input_read_parse_construct"):
        raw = json.loads((root / "data/public_windows.json").read_text(encoding="utf-8"))
        histories = [api["History"].from_dict(row) for row in raw["histories"]]
        require(len(histories) == 40, "expected 40 retained normalized histories")
        require(sum(len(h.atoms(include_cosmetic=False)) for h in histories) == 610,
                "expected 610 retained positive events")
    before = cache_info(api)
    path = out / ("bundles-%d.jsonl" % index)
    digest = hashlib.sha256()
    count, accepted, right_statuses, total_bytes = 0, 0, Counter(), 0
    with path.open("xb") as stream:
        for left in histories:
            for name in TRANSFORMS:
                with phases.at("transform_and_event_map"):
                    right, mapping = prepare_variant(api, left, name)
                with phases.at("left_endpoint_native_plus_projection"):
                    left_output = endpoint(api, left, arm)
                with phases.at("left_rank_shared"):
                    add_ranks(api, left_output)
                with phases.at("right_endpoint_native_plus_projection"):
                    right_output = endpoint(api, right, arm)
                with phases.at("right_rank_shared"):
                    add_ranks(api, right_output)
                with phases.at("certificate_producer_shared"):
                    certificate = api["certify_rewrite"](left, right, event_map=mapping)
                with phases.at("bundle_construct_serialize_write"):
                    bundle = {"schema": "p022-cost-bundle-v1", "history_id": left.history_id,
                              "transformation": name, "left": left.to_dict(), "right": right.to_dict(),
                              "event_map": mapping, "certificate": asdict(certificate),
                              "left_output": left_output, "right_output": right_output}
                    blob = encoded(bundle) + b"\n"
                    stream.write(blob)
                    digest.update(blob)
                    total_bytes += len(blob)
                count += 1
                accepted += int(certificate.valid)
                right_statuses[right_output["status"]] += 1
        with phases.at("producer_stream_flush_fsync"):
            stream.flush()
            os.fsync(stream.fileno())
    after_producer = cache_info(api)
    checked = 0
    # The whole read/parse/reconstruct/check boundary includes receiver I/O.
    with phases.at("receiver_stream_read_parse_reconstruct_check"):
        with path.open("rb") as stream:
            for line in stream:
                checked += int(check_bundle(api, json.loads(line)))
    require(count == 400 and accepted == checked == 320, "pair/certificate coverage changed")
    require(right_statuses == {"CERTIFIED": 320, "PARTIAL_ALIAS_ABSTENTION": 40, "ABSTAIN_ORIGIN": 40},
            "endpoint decision distribution changed")
    return {"pass": index, "pairs": count, "accepted": accepted, "receiver_accepted": checked,
            "right_statuses": dict(right_statuses), "bundle_bytes": total_bytes,
            "bundle_sha256": digest.hexdigest(),
            "cache_before": before, "cache_after_producer": after_producer,
            "cache_after_receiver": cache_info(api)}


def execute(protocol, arm, cache, out, measured=False, memory=None):
    require(arm in ARMS and cache in ("cold", "warm"), "unknown arm/cache")
    if measured:
        require(os.environ.get("P022_COST_RESOURCE_ENTRY") == "four-slot-wrapper-v1",
                "timing requires four-slot wrapper entry")
    out = output_path(out)
    out.mkdir(parents=True, exist_ok=False)
    setup = Phases(measured)
    with setup.at("source_input_and_harness_verify"):
        verify_sources(protocol)
    with setup.at("imports_both_arms_shared_closure"):
        api = load_api(protocol)
    with setup.at("rank_cache_clear_once"):
        api["_max_above_pattern"].cache_clear()
    passes = []
    for index in range(1, 2 if cache == "cold" else 3):
        phases = Phases(measured)
        row = run_pass(api, protocol, arm, out, index, phases)
        row["role"] = "cold_batch" if cache == "cold" else ("paid_warmup" if index == 1 else "warm_reuse")
        if measured:
            row["phases"] = dict(phases.values)
            row["memory_snapshot"] = memory() if memory else {"status": "UNAVAILABLE"}
        passes.append(row)
    require(len({r["bundle_sha256"] for r in passes}) == 1, "warm pass changed common output")
    with setup.at("final_source_input_and_harness_verify"):
        verify_sources(protocol)
    result = {"status": "PASS", "arm": arm, "cache": cache, "passes": passes,
              "timing_enabled": measured, "upstream_execution": False, "descendants_spawned": False}
    if measured:
        result["setup_phases"] = dict(setup.values)
        result["process_identity"] = {"pid": os.getpid(), "ppid": os.getppid(),
                                      "executable": Path(sys.executable).name}
    write_json(out / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correctness", action="store_true", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = output_path(args.output_dir)
    out.mkdir(parents=True, exist_ok=False)
    results = [execute(load_protocol(args.artifact_root), arm, "warm", out / arm) for arm in ARMS]
    require(results[0]["passes"][0]["bundle_sha256"] == results[1]["passes"][0]["bundle_sha256"],
            "arms differ on serialized common contract")
    report = {"status": "PASS", "timing_run": False, "arms": results}
    write_json(out / "correctness.json", report)
    print(json.dumps({"status": "PASS", "timing_run": False, "passes": 4, "pairs": 1600}))


if __name__ == "__main__":
    main()
