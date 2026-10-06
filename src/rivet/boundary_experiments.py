"""Deterministic source-boundary controls and global alias-rank checks.

No source fixture is executed. Source comparisons use bytes, syntax trees,
patch extraction, and normalized certificates. Behavioral witness arguments
are explicit small proofs stored with the fixtures, not test execution.
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import shutil
import tempfile
from dataclasses import asdict
from difflib import unified_diff
from itertools import product
from math import log2
from pathlib import Path

from .certificate import certify_rewrite
from .extract_public import parse_patch
from .global_aliases import exact_global_rank_interval_units, exact_global_rank_intervals_units
from .io import atomic_output_path, atomic_write_json
from .model import Atom, Commit, History
from .numeric import format_units, sum_weight_units
from .transforms import squash_pairs


def source_history(name: str, states: list[str]) -> tuple[History, list[int]]:
    if not 1 <= len(states) <= 3 or any(len(s.encode()) > 512 for s in states):
        raise ValueError('source case exceeds frozen dimensions')
    parsed = []
    for old, new in zip(states, states[1:]):
        ast.parse(old); ast.parse(new)
        patch = 'diff --git a/unit.py b/unit.py\n' + ''.join(unified_diff(
            old.splitlines(True), new.splitlines(True),
            fromfile='a/unit.py', tofile='b/unit.py', n=0))
        parsed.append(parse_patch(patch)['unit.py'])
    commits = []
    masses = []
    for index, record in enumerate(parsed, 1):
        mass = int(record['structural_tokens'])
        masses.append(mass)
        atom = Atom(f'E{index:03d}', 'unit.py',
                    mass * (1 + log2(1 + len(parsed))) if mass else 0,
                    'A', int(record['raw_lines']), int(record['raw_tokens']),
                    'structural' if mass else 'cosmetic')
        commits.append(Commit(f'C{index:03d}', 'A', (atom,),
                              (f'C{index-1:03d}',) if index > 1 else ()))
    return History(name, tuple(commits)), masses


def source_rows(path: Path) -> list[dict[str, object]]:
    cases = json.loads(path.read_text())['cases']
    if len(cases) != 8 or len({row['case'] for row in cases}) != 8:
        raise ValueError('expected eight unique source fixtures')
    result = []
    for case in cases:
        left, left_tokens = source_history(case['case']+'-path', case['states'])
        right, right_tokens = source_history(case['case']+'-comparison', case['comparison'])
        same_ast = ast.dump(ast.parse(case['states'][-1]), include_attributes=False) == ast.dump(
            ast.parse(case['comparison'][-1]), include_attributes=False)
        if (left_tokens != case['expected_tokens'] or right_tokens != case['expected_comparison_tokens']
                or same_ast != case['expected_ast_equal']):
            raise AssertionError('source negative control changed: '+case['case'])
        certificate = certify_rewrite(left, right)
        kept = certify_rewrite(left, squash_pairs(left))
        result.append({
            'case':case['case'], 'kind':case['kind'],
            'path_positive_events':len(left.atoms(include_cosmetic=False)),
            'comparison_positive_events':len(right.atoms(include_cosmetic=False)),
            'path_mass':format_units(sum_weight_units(a.weight for a in left.atoms())),
            'comparison_mass':format_units(sum_weight_units(a.weight for a in right.atoms())),
            'final_bytes_equal':case['states'][-1] == case['comparison'][-1],
            'final_ast_equal':same_ast,
            'reextracted_certificate_valid':certificate.valid,
            'frozen_event_squash_valid':kept.valid,
            'argument':case['argument'],
        })
    return result


def load_oracle(path: Path):
    spec = importlib.util.spec_from_file_location('independent_alias_oracle', path)
    if spec is None or spec.loader is None:
        raise ValueError('oracle module cannot be read')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def component_partitions(labels: tuple[str, ...]) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Enumerate set partitions by incremental insertion.

    This generator is deliberately distinct from the restricted-growth-string
    enumeration in the independent oracle. Labels are inserted in fixed order;
    each new label either starts the final block or joins one existing block.
    """
    if not 1 <= len(labels) <= 7 or len(set(labels)) != len(labels):
        raise ValueError('component-case generator admits one through seven unique labels')
    current: list[tuple[tuple[str, ...], ...]] = [()]
    for label in labels:
        following: list[tuple[tuple[str, ...], ...]] = []
        for partition in current:
            following.append(partition + ((label,),))
            for index in range(len(partition)):
                updated = list(partition)
                updated[index] = updated[index] + (label,)
                following.append(tuple(updated))
        current = following
    result = tuple(current)
    if len(result) != len(set(result)):
        raise AssertionError('component partition generator produced a duplicate')
    return result



def validate_oracle_transport(path: Path, expected_rows: int) -> int:
    """Read a compressed member to EOF and validate its declared row count."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            rows = sum(1 for _ in stream)
    except (EOFError, gzip.BadGzipFile, UnicodeDecodeError) as exc:
        raise ValueError(f"corrupt alias-oracle member: {path.name}") from exc
    if rows != expected_rows:
        raise ValueError(
            f"alias-oracle member row count changed for {path.name}: "
            f"{rows} != {expected_rows}"
        )
    return rows


def file_sha256(path: Path) -> str:
    """Bind replay evidence to exact bytes, not only a problem-row count."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_oracle_receipt(root: Path, receipt: dict, root_counts: tuple[int, ...]) -> dict[str, int]:
    oracle_path = root / "replayer" / "alias_rank_oracle.py"
    oracle = load_oracle(oracle_path)
    if (receipt.get("schema") != "rivet-alias-oracle-v1"
            or receipt.get("root_counts") != list(root_counts)
            or receipt.get("checker_sha256") != file_sha256(oracle_path)):
        raise ValueError("stale or unsupported alias-oracle receipt; rerun independent checks")
    keys = {str(n) for n in root_counts}
    if set(receipt.get("members", {})) != keys or set(receipt.get("member_sha256", {})) != keys:
        raise ValueError("alias-oracle receipt has incomplete member coverage")
    aggregate = dict(problems=0, cases=0, bound_mismatches=0, invalid_witnesses=0)
    for n in root_counts:
        member = root / "results" / "global_alias_oracle" / f"roots-{n}.jsonl.gz"
        validate_oracle_transport(member, oracle.EXPECTED_PROBLEMS_BY_ROOTS[n])
        if receipt["member_sha256"][str(n)] != file_sha256(member):
            raise ValueError(f"stale alias-oracle receipt for roots-{n}; member bytes changed")
        expected = dict(root_count=n, problems=oracle.EXPECTED_PROBLEMS_BY_ROOTS[n],
                        cases=oracle.EXPECTED_CASES_BY_ROOTS[n],
                        bound_mismatches=0, invalid_witnesses=0)
        if receipt["members"][str(n)] != expected:
            raise ValueError("invalid alias-oracle member result")
        for key in aggregate:
            aggregate[key] += expected[key]
    if receipt.get("aggregate") != aggregate:
        raise ValueError("alias-oracle receipt aggregate differs from its members")
    return aggregate

def run(root: Path) -> dict[str, object]:
    results = root/'results'
    results.mkdir(exist_ok=True)
    rows = source_rows(root/'external_inputs/source_cases.json')
    with atomic_output_path(results / 'source_boundary.csv') as temporary:
        with temporary.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    oracle = load_oracle(root/'replayer/alias_rank_oracle.py')
    member_dir = results/'global_alias_oracle'
    member_paths = [member_dir/f'roots-{n}.jsonl.gz' for n in range(1,8)]
    receipt_paths = [member_dir/'check-low.json', member_dir/'check-cap.json']
    missing = [path.name for path in member_paths + receipt_paths if not path.is_file()]
    if missing:
        raise ValueError('missing alias-oracle evidence: '+', '.join(missing))
    receipts = [json.loads(path.read_text(encoding='utf-8')) for path in receipt_paths]
    checked = {'problems':0, 'cases':0, 'bound_mismatches':0, 'invalid_witnesses':0}
    for receipt, roots in zip(receipts, (tuple(range(1, 7)), (7,))):
        if receipt.get('stage') != ('low' if roots[0] == 1 else 'cap'):
            raise ValueError('alias-oracle receipt stage changed')
        aggregate = validate_oracle_receipt(root, receipt, roots)
        for key in checked:
            checked[key] += aggregate[key]
    expected = {
        'problems': oracle.EXPECTED_PROBLEMS,
        'cases': oracle.EXPECTED_CASES,
        'bound_mismatches': 0,
        'invalid_witnesses': 0,
    }
    if checked != expected:
        raise AssertionError(checked)
    counts = {str(n):oracle.EXPECTED_CASES_BY_ROOTS[n] for n in range(1,8)}
    problem_counts = {str(n):oracle.EXPECTED_PROBLEMS_BY_ROOTS[n] for n in range(1,8)}
    mass_alphabets = {str(n):list(oracle.MASS_ALPHABETS[n]) for n in range(1,8)}
    directed = exact_global_rank_interval_units({'T':5,'B':3,'C':3}, [('T',),('B','C')], 'T')
    if (directed.best_rank,directed.worst_rank) != (1,2):
        raise AssertionError('other-component uncertainty was ignored')
    groups = [[f'G{g}A{i}' for i in range(7)] for g in range(8)]
    weights = {label:1+(i % 5) for group in groups for i,label in enumerate(group)}
    large = exact_global_rank_interval_units(weights, groups, groups[0][0])
    for which in ('best','worst'):
        actual = oracle.rank_of(weights, groups, groups[0][0], getattr(large,which+'_partition'))
        if actual != getattr(large,which+'_rank'):
            raise AssertionError('large-case witness rank mismatch')
    summary = {
        'source_cases':len(rows),
        'source_path_comparisons':sum(row['final_bytes_equal'] for row in rows),
        'equal_endpoint_path_mismatches':sum(row['final_bytes_equal'] and
            row['path_mass'] != row['comparison_mass'] for row in rows),
        'zero_mass_same_ast_controls':sum(row['path_positive_events'] == 0 and
            row['final_ast_equal'] for row in rows),
        'positive_mass_numeric_control':sum(row['kind'] == 'numeric_literal' and
            row['path_positive_events'] > 0 for row in rows),
        'zero_mass_distinct_behavior_cases':sum(row['path_positive_events'] == 0 and
            not row['final_ast_equal'] for row in rows),
        'fixture_execution':False,
        'global_alias_oracle':checked,
        'oracle_problems_by_roots':problem_counts,
        'oracle_cases_by_roots':counts,
        'oracle_mass_alphabet_by_roots':mass_alphabets,
        'other_component_example':asdict(directed),
        'eight_component_example':{'roots':56,'components':8,'maximum_component_size':7,**asdict(large)},
    }
    atomic_write_json(results / 'boundary_summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact_root', type=Path)
    args = parser.parse_args()
    summary = run(args.artifact_root)
    print(json.dumps({key:summary[key] for key in ('source_cases','global_alias_oracle')},sort_keys=True))
