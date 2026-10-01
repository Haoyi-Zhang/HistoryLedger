#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export PYTHONPATH="$ROOT/src"
export PYTHONDONTWRITEBYTECODE=1

python -m unittest discover -s "$ROOT/tests" -v
python - "$ROOT" <<'PYCHECKLEDGER'
import csv
import sys
from pathlib import Path

root = Path(sys.argv[1])
ledger_path = root / "claim_evidence_ledger.csv"
with ledger_path.open(newline="", encoding="utf-8") as stream:
    reader = csv.DictReader(stream)
    rows = list(reader)

expected_header = [
    "claim_id",
    "claim",
    "formal_basis",
    "implementation_or_test",
    "result_surface",
    "maturity",
    "fresh_check",
]
if reader.fieldnames != expected_header:
    raise SystemExit(f"claim-evidence ledger header changed: {reader.fieldnames!r}")
expected_ids = [f"C{index}" for index in range(1, 42)]
actual_ids = [row["claim_id"] for row in rows]
if actual_ids != expected_ids:
    raise SystemExit("claim-evidence ledger must contain exactly C1 through C41 in order")
for row in rows:
    if any(not row[field].strip() for field in expected_header):
        raise SystemExit(f"claim-evidence ledger has a blank required field in {row['claim_id']}")
    expected_status = (
        "PASS_WITH_DECLARED_PROVENANCE_LIMIT"
        if row["claim_id"] == "C10"
        else "PASS_WITHIN_STATED_SCOPE"
    )
    if row["fresh_check"] != expected_status:
        raise SystemExit(
            f"claim-evidence ledger status changed for {row['claim_id']}: "
            f"{row['fresh_check']!r}"
        )
combined = "\n".join(value for row in rows for value in row.values()).casefold()
for stale in ("99-test", "104-test", "110-test", "112-test", "116-test", "fast check"):
    if stale in combined:
        raise SystemExit(f"claim-evidence ledger contains stale evidence wording: {stale}")
if sum("117-test suite" in row["result_surface"] for row in rows) != 11:
    raise SystemExit("claim-evidence ledger no longer has the expected 117-test surfaces")
print("claim-evidence ledger consistency: PASS")
PYCHECKLEDGER
python "$ROOT/replayer/replay.py" \
  "$ROOT/data/canonical_ledgers.csv" \
  --expected "$ROOT/data/canonical_expected.json"
python - "$ROOT/results/experiment_summary.json" "$ROOT/results/runtime.csv" "$ROOT" <<'PY'
import csv
import json
import math
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
runtime_path = Path(sys.argv[2])
root = Path(sys.argv[3])
summary = json.loads(summary_path.read_text(encoding="utf-8"))

required_exact = {
    "public_histories": 40,
    "public_commits": 320,
    "public_structural_events": 610,
    "public_actors_median": 2.0,
    "certified_transform_obligations": 320,
    "certified_transform_failures": 0,
    "unobserved_squash_abstentions": 40,
    "ambiguous_alias_partial_abstentions": 40,
    "alias_trials": 480,
    "alias_target_histories": 40,
    "alias_target_top_histories": 32,
    "alias_rank_width_median": 2.0,
    "alias_rank_width_p95": 6.0,
    "budget_three_worst_rank_bound_median": 2.0,
    "replay_faults_injected": 7,
    "replay_faults_detected": 7,
    "certificate_faults_injected": 280,
    "certificate_faults_detected": 280,
    "winner_flip_histories": 40,
    "winner_flip_one_label": 28,
    "winner_flip_radius_median": 1.0,
    "winner_flip_radius_p95": 4.0,
    "winner_flip_radius_maximum": 8,
}
for key, expected in required_exact.items():
    actual = summary.get(key)
    if actual != expected:
        raise SystemExit(f"summary mismatch for {key}: {actual!r} != {expected!r}")

span = summary.get("budget_three_score_span_fraction_median")
expected_span = 0.8181168518566861
if not isinstance(span, (int, float)) or not math.isclose(
    float(span), expected_span, rel_tol=0.0, abs_tol=1e-15
):
    raise SystemExit(
        "summary mismatch for budget_three_score_span_fraction_median: "
        f"{span!r} != {expected_span!r}"
    )

tiny = summary.get("tiny", {})
required_tiny = {
    "histories": 3510,
    "max_atoms": 4,
    "obligations": 27570,
    "certified_failures": 0,
    "origin_abstention_failures": 0,
    "winner_flip_oracle_cases": 2514,
    "winner_flip_oracle_failures": 0,
}
for key, expected in required_tiny.items():
    actual = tiny.get(key)
    if actual != expected:
        raise SystemExit(f"tiny-study mismatch for {key}: {actual!r} != {expected!r}")

expected_counterexamples = {
    "empty-commit-padding:commit_count": 3510,
    "formatting:line_count": 3510,
    "split:commit_count": 1956,
    "squash-certified:commit_count": 3420,
    "squash-certified:entity_degree": 2568,
    "squash-certified:line_count": 2568,
    "squash-certified:structural_no_origin": 2568,
    "squash-certified:token_count": 2568,
}
if tiny.get("baseline_counterexamples") != expected_counterexamples:
    raise SystemExit("exhaustive-study baseline counterexample counts changed")

if runtime_path.exists():
    raise SystemExit(
        "default scientific result set unexpectedly contains environment-sensitive runtime.csv"
    )

with (root / "results" / "alias_sensitivity.csv").open(
    newline="", encoding="utf-8"
) as handle:
    alias_rows = list(csv.DictReader(handle))
if len(alias_rows) != 480 or any(
    int(row["component_score_units"]) != int(row["partition_total_units"])
    for row in alias_rows
):
    raise SystemExit("alias sensitivity output does not conserve exact unit mass")

with (root / "results" / "certificate_mutations.csv").open(
    newline="", encoding="utf-8"
) as handle:
    mutation_rows = list(csv.DictReader(handle))
if len(mutation_rows) != 280 or any(row["detected"] != "1" for row in mutation_rows):
    raise SystemExit("certificate mutation campaign did not reject every injected fault")

with (root / "results" / "winner_flip_radius.csv").open(
    newline="", encoding="utf-8"
) as handle:
    winner_rows = list(csv.DictReader(handle))
radii = sorted(int(row["minimum_relabels"]) for row in winner_rows)
if len(winner_rows) != 40 or radii.count(1) != 28 or max(radii) != 8:
    raise SystemExit("winner-flip radius output changed")

print("frozen summary and row-level checks: PASS")
PY

python - "$ROOT" <<'PYCODE'
import csv
import json
import sys
from pathlib import Path
from rivet.boundary_experiments import source_rows, validate_oracle_transport
root = Path(sys.argv[1])
summary = json.loads((root / 'results/boundary_summary.json').read_text())
expected_summary_fields = {
    'global_alias_oracle': {
        'problems': 274250,
        'cases': 1742198,
        'bound_mismatches': 0,
        'invalid_witnesses': 0,
    },
    'source_cases': 8,
    'equal_endpoint_path_mismatches': 2,
    'zero_mass_same_ast_controls': 2,
    'positive_mass_numeric_control': 1,
    'zero_mass_distinct_behavior_cases': 3,
    'fixture_execution': False,
    'oracle_problems_by_roots': {
        '1':3,'2':18,'3':135,'4':1215,'5':12636,'6':147987,'7':112256,
    },
    'oracle_cases_by_roots': {
        '1':3,'2':36,'3':405,'4':4860,'5':63180,'6':887922,'7':785792,
    },
    'oracle_mass_alphabet_by_roots': {
        '1':[1,2,3],'2':[1,2,3],'3':[1,2,3],'4':[1,2,3],
        '5':[1,2,3],'6':[1,2,3],'7':[1,2],
    },
}
for key, expected_value in expected_summary_fields.items():
    if summary.get(key) != expected_value:
        raise SystemExit(
            f"boundary summary mismatch for {key}: {summary.get(key)!r} != {expected_value!r}"
        )
member_dir = root / 'results' / 'global_alias_oracle'
expected_members = {
    1:(3,3), 2:(18,36), 3:(135,405), 4:(1215,4860),
    5:(12636,63180), 6:(147987,887922), 7:(112256,785792),
}
for n, (problems, _cases) in expected_members.items():
    member_path = member_dir / f'roots-{n}.jsonl.gz'
    if not member_path.is_file():
        raise SystemExit(f'missing alias-oracle member for {n} roots')
    validate_oracle_transport(member_path, problems)
receipts = {
    'low': json.loads((member_dir/'check-low.json').read_text()),
    'cap': json.loads((member_dir/'check-cap.json').read_text()),
}
seen = set()
for receipt in receipts.values():
    for n_text, result in receipt['members'].items():
        n = int(n_text)
        problems, cases = expected_members[n]
        expected = {
            'root_count': n, 'problems': problems, 'cases': cases,
            'bound_mismatches': 0, 'invalid_witnesses': 0,
        }
        if result != expected or n in seen:
            raise SystemExit('alias-oracle receipt mismatch')
        seen.add(n)
if seen != set(expected_members):
    raise SystemExit('alias-oracle receipts do not cover one through seven roots')

for key, expected in [('other_component_example',(1,2)), ('eight_component_example',(1,48))]:
    row = summary.get(key, {})
    actual_interval = (row.get('best_rank'), row.get('worst_rank'))
    if actual_interval != expected:
        raise SystemExit(
            f"boundary witness interval mismatch for {key}: {actual_interval!r} != {expected!r}"
        )
with (root/'results/source_boundary.csv').open(newline='') as stream:
    actual = list(csv.DictReader(stream))
expected = [{key:str(value) for key,value in row.items()}
            for row in source_rows(root/'external_inputs/source_cases.json')]
if actual != expected:
    raise SystemExit('source-boundary rows differ from fresh in-process recomputation')
print('source controls and global alias bounds: PASS')
PYCODE

python - "$ROOT" <<'PYCODE'
import csv
import json
import sys
from pathlib import Path
from rivet.public_patch_experiments import case_rows, load_cases

root = Path(sys.argv[1])
cases_path = root / "external_inputs" / "public_patch_cases.json"
payload = load_cases(cases_path)
summary = json.loads((root / "results" / "public_patch_summary.json").read_text(encoding="utf-8"))
expected_summary = {
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
}
if summary != expected_summary:
    raise SystemExit(f"public-patch summary changed: {summary!r}")
with (root / "results" / "public_patch_boundary.csv").open(newline="", encoding="utf-8") as stream:
    actual = list(csv.DictReader(stream))
expected = [
    {key: str(value) for key, value in row.items()}
    for row in case_rows(cases_path)
]
if actual != expected:
    raise SystemExit("public-patch boundary rows differ from independent in-process recomputation")
if len(actual) != 12 or sum(row["endpoint_certificate_valid"] == "1" for row in actual) != 12:
    raise SystemExit("public-patch endpoint certificate coverage changed")
control = next(row for row in actual if row["case"] == "P07")
if control["endpoint_mass"] != "0" or control["cycle_path_mass"] != "0":
    raise SystemExit("comment-only control is no longer zero-mass")
with (root / "external_inputs" / "public_patch_manifest.csv").open(newline="", encoding="utf-8") as stream:
    manifest = list(csv.DictReader(stream))
expected_manifest = []
for case in payload["cases"]:
    expected_manifest.append({
        "case": case["case"],
        "repository": case["repository"],
        "repository_url": case["repository_url"],
        "license": case["license"],
        "license_file": case["license_file"],
        "copyright_notice": " | ".join(case["copyright_notices"]),
        "language": case["language"],
        "control": case.get("control", "structural"),
        "file_count": str(len(case["files"])),
        "included_input": "public_patch_cases.json",
    })
if manifest != expected_manifest:
    raise SystemExit("public-patch manifest does not match retained license metadata")
print("public patch boundary and license-notice checks: PASS")
PYCODE

if find "$ROOT" -type f -name '*.tmp' -print -quit | grep -q .; then
  echo "temporary output residue remains in artifact" >&2
  exit 1
fi
