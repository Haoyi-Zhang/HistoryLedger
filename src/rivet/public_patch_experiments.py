"""Source-boundary experiment over retained public patch fragments.

The module never executes upstream code.  It parses unified-diff hunks, applies
exact token-multiset accounting, and contrasts two quantities:

* endpoint mass: one extraction from the retained initial hunk state to the
  retained final hunk state; and
* path-additive mass: the sum of extraction results along a chosen edit path.

Endpoint mass is invariant under path decomposition by construction.  The
path-additive baseline can grow under delete/add staging or a nonzero cycle.
The experiment does not claim that a patch fragment is a complete program or
that intermediate staged states compile.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .certificate import certify_rewrite
from .io import atomic_output_path, atomic_write_json
from .extract_public import CODE_EXTENSIONS, edit_size, parse_patch, tokens
from .model import Atom, Commit, History

MAX_CASES = 12
MAX_FILES_PER_CASE = 3
MAX_PATCH_BYTES = 4096
MAX_TOTAL_BYTES = 32768
EXPECTED_LANGUAGES = frozenset({"Python", "JavaScript", "TypeScript", "Rust", "C++"})
EXPECTED_LICENSE_FILES = frozenset({"LICENSE", "LICENSE.md", "LICENSE.txt"})
EXPECTED_COPYRIGHT_NOTICES = 13


@dataclass(frozen=True)
class ChangePart:
    old_lines: tuple[str, ...]
    new_lines: tuple[str, ...]


def _flush_part(old: list[str], new: list[str], parts: list[ChangePart]) -> None:
    if old or new:
        parts.append(ChangePart(tuple(old), tuple(new)))
        old.clear()
        new.clear()


def split_change_parts(patch: str, *, by_hunk: bool) -> list[ChangePart]:
    """Split a header-free unified patch into hunk or contiguous change parts."""
    parts: list[ChangePart] = []
    old: list[str] = []
    new: list[str] = []
    in_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            _flush_part(old, new, parts)
            in_hunk = True
            continue
        if not in_hunk:
            if line.strip():
                raise ValueError("patch text precedes first hunk")
            continue
        if line.startswith("+") and not line.startswith("+++"):
            new.append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            old.append(line[1:])
        elif line.startswith(" ") or line == "" or line.startswith("\\ No newline"):
            if not by_hunk:
                _flush_part(old, new, parts)
        else:
            raise ValueError(f"unsupported unified-patch line: {line[:40]!r}")
    _flush_part(old, new, parts)
    if not parts:
        raise ValueError("patch contains no changed lines")
    return parts


def _net_counts(old_tokens: list[str], new_tokens: list[str]) -> tuple[int, int]:
    old_counts, new_counts = Counter(old_tokens), Counter(new_tokens)
    removed = sum((old_counts - new_counts).values())
    added = sum((new_counts - old_counts).values())
    return removed, added


def _part_mass(parts: list[ChangePart]) -> int:
    return sum(edit_size(tokens(list(part.old_lines)), tokens(list(part.new_lines))) for part in parts)


def _file_record(path: str, patch: str) -> dict[str, int | str]:
    wrapped = f"diff --git a/{path} b/{path}\n{patch}\n"
    parsed = parse_patch(wrapped)
    if set(parsed) != {path}:
        raise ValueError("patch adapter did not recover exactly one declared file")
    record = parsed[path]
    old_tokens = list(record["old_tokens"])
    new_tokens = list(record["new_tokens"])
    removed, added = _net_counts(old_tokens, new_tokens)
    hunks = split_change_parts(patch, by_hunk=True)
    blocks = split_change_parts(patch, by_hunk=False)
    direct = int(record["structural_tokens"])
    return {
        "path": path,
        "hunks": len(hunks),
        "blocks": len(blocks),
        "raw_lines": int(record["raw_lines"]),
        "old_tokens": len(old_tokens),
        "new_tokens": len(new_tokens),
        "net_removed": removed,
        "net_added": added,
        "endpoint_mass": direct,
        "hunk_path_mass": _part_mass(hunks),
        "block_path_mass": _part_mass(blocks),
        # A deliberately adversarial two-edge path: delete the changed-region
        # token stream, then insert the final changed-region token stream.
        "delete_add_path_mass": len(old_tokens) + len(new_tokens),
        "cycle_path_mass": 2 * direct,
    }


def load_cases(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    notices_path = path.with_name("THIRD_PARTY_NOTICES.md")
    if not notices_path.is_file():
        raise ValueError("third-party notices are missing")
    notices_text = notices_path.read_text(encoding="utf-8")
    if ("## Common MIT grant and disclaimer" not in notices_text
            or "Permission is hereby granted, free of charge" not in notices_text
            or "THE SOFTWARE IS PROVIDED \"AS IS\"" not in notices_text):
        raise ValueError("common MIT grant or disclaimer is incomplete")
    if payload.get("schema") != "public-patch-boundary":
        raise ValueError("unknown public patch schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != MAX_CASES:
        raise ValueError(f"expected exactly {MAX_CASES} public patch cases")
    case_ids: set[str] = set()
    repositories: set[str] = set()
    languages: set[str] = set()
    controls = 0
    total_bytes = 0
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("public patch case is not a mapping")
        case_id = case.get("case")
        repository = case.get("repository")
        language = case.get("language")
        if not isinstance(case_id, str) or not case_id.startswith("P") or case_id in case_ids:
            raise ValueError("case identifiers must be unique neutral P-labels")
        if not isinstance(repository, str) or repository.count("/") != 1 or repository in repositories:
            raise ValueError("repositories must be unique owner/name labels")
        if case.get("repository_url") != f"https://github.com/{repository}":
            raise ValueError("repository URL does not match repository label")
        if case.get("license") != "MIT":
            raise ValueError("all retained public patches must declare MIT")
        license_file = case.get("license_file")
        license_path = PurePosixPath(license_file) if isinstance(license_file, str) else None
        if (license_path is None or license_path.is_absolute() or ".." in license_path.parts
                or license_path.name not in EXPECTED_LICENSE_FILES):
            raise ValueError("invalid upstream license-file path")
        copyright_notices = case.get("copyright_notices")
        if (not isinstance(copyright_notices, list) or not copyright_notices
                or len(copyright_notices) != len(set(copyright_notices))
                or any(not isinstance(notice, str) or not notice.startswith("Copyright ")
                       for notice in copyright_notices)):
            raise ValueError("invalid project-specific copyright notices")
        required_notice_fragments = [
            f"### {case_id}: {repository}",
            f"- Repository: {case.get('repository_url')}",
            f"- Upstream license file: `{license_file}`",
            *(f"- {notice}" for notice in copyright_notices),
        ]
        if any(fragment not in notices_text for fragment in required_notice_fragments):
            raise ValueError("third-party notices do not cover every retained case")
        if language not in EXPECTED_LANGUAGES:
            raise ValueError("unexpected language label")
        files = case.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES_PER_CASE:
            raise ValueError("invalid number of files in public patch case")
        seen_paths: set[str] = set()
        for file in files:
            if not isinstance(file, dict):
                raise ValueError("file entry is not a mapping")
            file_path, patch = file.get("path"), file.get("patch")
            if not isinstance(file_path, str) or file_path in seen_paths:
                raise ValueError("file paths must be unique strings")
            if PurePosixPath(file_path).is_absolute() or ".." in PurePosixPath(file_path).parts:
                raise ValueError("file path escapes the case root")
            if PurePosixPath(file_path).suffix.lower() not in CODE_EXTENSIONS:
                raise ValueError("public patch file is outside the code-extension lock")
            if not isinstance(patch, str) or not patch.startswith("@@"):
                raise ValueError("patch must be a header-free unified hunk fragment")
            size = len(patch.encode("utf-8"))
            if size > MAX_PATCH_BYTES:
                raise ValueError("public patch file exceeds byte cap")
            total_bytes += size
            split_change_parts(patch, by_hunk=True)
            split_change_parts(patch, by_hunk=False)
            seen_paths.add(file_path)
        if case.get("control") == "comment_only":
            controls += 1
        elif "control" in case:
            raise ValueError("unknown control label")
        case_ids.add(case_id)
        repositories.add(repository)
        languages.add(str(language))
    if languages != EXPECTED_LANGUAGES:
        raise ValueError("language-stratum coverage changed")
    if controls != 1:
        raise ValueError("expected one comment-only control")
    if sum(len(case["copyright_notices"]) for case in cases) != EXPECTED_COPYRIGHT_NOTICES:
        raise ValueError("project-specific copyright-notice coverage changed")
    if total_bytes > MAX_TOTAL_BYTES:
        raise ValueError("public patch corpus exceeds aggregate byte cap")
    return payload


def _endpoint_history(case_id: str, records: list[dict[str, int | str]], variant: str) -> History:
    atoms: list[Atom] = []
    for index, record in enumerate(records, 1):
        mass = int(record["endpoint_mass"])
        if mass:
            atoms.append(
                Atom(
                    atom_id=f"{case_id}-E{index:02d}",
                    entity=f"{case_id}-F{index:02d}",
                    weight=float(mass),
                    origin="A",
                    raw_lines=int(record["raw_lines"]),
                    raw_tokens=int(record["old_tokens"]) + int(record["new_tokens"]),
                    kind="structural",
                )
            )
    commit = Commit(commit_id=f"{variant}-C", alias="A", atoms=tuple(atoms))
    return History(history_id=f"{case_id}-{variant}", commits=(commit,))


def case_rows(path: Path) -> list[dict[str, object]]:
    payload = load_cases(path)
    rows: list[dict[str, object]] = []
    for case in payload["cases"]:  # type: ignore[index]
        file_records = [_file_record(file["path"], file["patch"]) for file in case["files"]]
        direct = sum(int(row["endpoint_mass"]) for row in file_records)
        hunk = sum(int(row["hunk_path_mass"]) for row in file_records)
        block = sum(int(row["block_path_mass"]) for row in file_records)
        staged = sum(int(row["delete_add_path_mass"]) for row in file_records)
        cycle = sum(int(row["cycle_path_mass"]) for row in file_records)
        original = _endpoint_history(case["case"], file_records, "direct")
        rewritten = _endpoint_history(case["case"], file_records, "staged")
        endpoint_certificate = certify_rewrite(original, rewritten)
        if not endpoint_certificate.valid:
            raise AssertionError((case["case"], endpoint_certificate.reasons))
        rows.append(
            {
                "case": case["case"],
                "repository": case["repository"],
                "language": case["language"],
                "control": case.get("control", "structural"),
                "files": len(file_records),
                "hunks": sum(int(row["hunks"]) for row in file_records),
                "blocks": sum(int(row["blocks"]) for row in file_records),
                "raw_changed_lines": sum(int(row["raw_lines"]) for row in file_records),
                "old_tokens": sum(int(row["old_tokens"]) for row in file_records),
                "new_tokens": sum(int(row["new_tokens"]) for row in file_records),
                "net_removed": sum(int(row["net_removed"]) for row in file_records),
                "net_added": sum(int(row["net_added"]) for row in file_records),
                "endpoint_mass": direct,
                "hunk_path_mass": hunk,
                "block_path_mass": block,
                "delete_add_path_mass": staged,
                "cycle_path_mass": cycle,
                "hunk_path_equal": int(hunk == direct),
                "block_path_equal": int(block == direct),
                "delete_add_path_equal": int(staged == direct),
                "cycle_path_zero": int(cycle == 0),
                "endpoint_certificate_valid": int(endpoint_certificate.valid),
                "upstream_execution": 0,
            }
        )
    return rows


def run(root: Path) -> dict[str, object]:
    rows = case_rows(root / "external_inputs" / "public_patch_cases.json")
    results = root / "results"
    results.mkdir(exist_ok=True)
    with atomic_output_path(results / "public_patch_boundary.csv") as temporary:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "repositories": len({row["repository"] for row in rows}),
        "cases": len(rows),
        "files": sum(int(row["files"]) for row in rows),
        "languages": sorted({str(row["language"]) for row in rows}),
        "comment_only_controls": sum(row["control"] == "comment_only" for row in rows),
        "positive_endpoint_cases": sum(int(row["endpoint_mass"]) > 0 for row in rows),
        "hunk_path_mismatches": sum(not int(row["hunk_path_equal"]) for row in rows),
        "block_path_mismatches": sum(not int(row["block_path_equal"]) for row in rows),
        "delete_add_path_mismatches": sum(not int(row["delete_add_path_equal"]) for row in rows),
        "positive_cycle_cases": sum(int(row["cycle_path_mass"]) > 0 for row in rows),
        "endpoint_certificates_valid": sum(int(row["endpoint_certificate_valid"]) for row in rows),
        "upstream_execution": False,
        "scope": "bounded public production-code patch fragments; descriptive boundary evidence only",
    }
    if summary["repositories"] != MAX_CASES or summary["endpoint_certificates_valid"] != MAX_CASES:
        raise AssertionError("public patch experiment lost a case or endpoint certificate")
    if summary["comment_only_controls"] != 1:
        raise AssertionError("comment-only control missing")
    atomic_write_json(results / "public_patch_summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.artifact_root), sort_keys=True))
