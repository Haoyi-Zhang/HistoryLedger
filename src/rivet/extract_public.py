from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from .io import save_histories
from .model import Atom, Commit, History

CODE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".java", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".py", ".rb", ".go", ".rs", ".php", ".cs", ".swift",
    ".kt", ".kts", ".scala", ".sh", ".html", ".css", ".scss", ".xml", ".json",
}

TOKEN_RE = re.compile(
    r"[A-Za-z_$][A-Za-z0-9_$]*|0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?|"
    r"===|!==|=>|==|!=|<=|>=|&&|\|\||\+\+|--|\*\*|<<|>>|[-+*/%&|^~<>?:=.!;,(){}\[\]]"
)


def run_git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"//.*$", " ", line)
        line = re.sub(r"(?<!:)#.*$", " ", line)
        lines.append(line)
    return "\n".join(lines)


def tokens(lines: list[str]) -> list[str]:
    return TOKEN_RE.findall(strip_comments("\n".join(lines)))


def edit_size(old_tokens: list[str], new_tokens: list[str]) -> int:
    # Linear-time token-multiset edit mass.  It is intentionally insensitive
    # to formatting and pure movement, and the paper does not equate it with
    # semantic program equivalence.
    old_counts, new_counts = Counter(old_tokens), Counter(new_tokens)
    removed = sum((old_counts - new_counts).values())
    added = sum((new_counts - old_counts).values())
    return max(removed, added)


def parse_patch(patch: str) -> dict[str, dict[str, object]]:
    files: dict[str, dict[str, object]] = {}
    current: str | None = None
    old_lines: list[str] = []
    new_lines: list[str] = []

    def flush() -> None:
        nonlocal current, old_lines, new_lines
        if current is None:
            return
        old_tok, new_tok = tokens(old_lines), tokens(new_lines)
        files[current] = {
            "old_tokens": old_tok,
            "new_tokens": new_tok,
            "raw_lines": len(old_lines) + len(new_lines),
            "raw_tokens": len(old_tok) + len(new_tok),
            "structural_tokens": edit_size(old_tok, new_tok),
        }
        old_lines = []
        new_lines = []

    for line in patch.splitlines():
        if line.startswith("diff --git "):
            flush()
            match = re.match(r"diff --git a/(.*?) b/(.*)", line)
            current = match.group(2) if match else None
            continue
        if current is None:
            continue
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            new_lines.append(line[1:])
        elif line.startswith("-"):
            old_lines.append(line[1:])
    flush()
    return files


def commit_records(repository: Path) -> list[tuple[str, str, str, str]]:
    output = run_git(
        repository,
        "log",
        "--reverse",
        "--no-merges",
        "--format=%H%x1f%an%x1f%ae%x1f%aI%x1e",
        "HEAD",
    )
    records = []
    for record in output.split("\x1e"):
        record = record.strip()
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 4:
            continue
        records.append(tuple(fields))
    return records


def select_window_starts(total: int, window_size: int, desired: int) -> list[int]:
    if total < window_size:
        return []
    low = max(0, total // 20)
    high = max(low, total - window_size - total // 20)
    if desired == 1:
        return [(low + high) // 2]
    starts = []
    for index in range(desired * 3):
        fraction = index / max(1, desired * 3 - 1)
        starts.append(round(low + fraction * (high - low)))
    return sorted(dict.fromkeys(starts))


def build_histories(
    repository: Path,
    project_name: str,
    source_commit_count: int | None = None,
    window_size: int = 8,
    desired: int = 40,
) -> list[History]:
    records = commit_records(repository)
    if source_commit_count is not None:
        if source_commit_count <= 0:
            raise ValueError("source commit count must be positive")
        if len(records) < source_commit_count:
            raise ValueError(
                f"repository contains only {len(records)} non-merge commits; "
                f"requested prefix contains {source_commit_count}"
            )
        records = records[:source_commit_count]
    starts = select_window_starts(len(records), window_size, desired)
    alias_map: dict[tuple[str, str], str] = {}
    next_alias = 1
    histories: list[History] = []

    for start in starts:
        selected = records[start : start + window_size]
        parsed: list[tuple[str, str, dict[str, dict[str, object]]]] = []
        for revision_id, author_name, author_email, _date in selected:
            identity = (author_name.strip().casefold(), author_email.strip().casefold())
            if identity not in alias_map:
                alias_map[identity] = f"A{next_alias:03d}"
                next_alias += 1
            alias = alias_map[identity]
            patch = run_git(
                repository,
                "show",
                "--format=",
                "--find-renames",
                "--unified=0",
                "--no-ext-diff",
                revision_id,
            )
            files = parse_patch(patch)
            files = {
                path: info
                for path, info in files.items()
                if Path(path).suffix.lower() in CODE_EXTENSIONS
                and int(info["raw_lines"]) <= 4000
            }
            parsed.append((revision_id, alias, files))

        actors = {alias for _revision_id, alias, files in parsed if files}
        total_files = sum(len(files) for _revision_id, _alias, files in parsed)
        if len(actors) < 2 or total_files < window_size or total_files > 120:
            continue

        path_counts: Counter[str] = Counter()
        for _revision_id, _alias, files in parsed:
            path_counts.update(files.keys())
        entity_map = {path: f"F{index:03d}" for index, path in enumerate(sorted(path_counts), 1)}
        commits: list[Commit] = []
        atom_serial = 1
        previous: str | None = None
        for commit_index, (_revision_id, alias, files) in enumerate(parsed, 1):
            atoms: list[Atom] = []
            for path, info in sorted(files.items()):
                structural = int(info["structural_tokens"])
                raw_lines = int(info["raw_lines"])
                raw_tokens = int(info["raw_tokens"])
                if structural == 0 and raw_lines == 0:
                    continue
                salience = 1.0 + math.log2(1.0 + path_counts[path])
                weight = float(structural) * salience
                kind = "structural" if structural else "cosmetic"
                atoms.append(
                    Atom(
                        atom_id=f"E{atom_serial:04d}",
                        entity=entity_map[path],
                        weight=weight if kind == "structural" else 0.0,
                        origin=alias,
                        raw_lines=raw_lines,
                        raw_tokens=raw_tokens,
                        kind=kind,
                    )
                )
                atom_serial += 1
            commit_id = f"C{commit_index:03d}"
            predecessors = (previous,) if previous is not None else tuple()
            commits.append(Commit(commit_id, alias, tuple(atoms), predecessors))
            previous = commit_id

        structural_atoms = sum(
            1 for commit in commits for atom in commit.atoms if atom.kind == "structural"
        )
        structural_actors = {
            atom.origin
            for commit in commits
            for atom in commit.atoms
            if atom.kind == "structural"
        }
        if structural_atoms < window_size or len(structural_actors) < 2:
            continue
        histories.append(
            History(
                history_id=f"public-{len(histories) + 1:03d}",
                commits=tuple(commits),
                metadata={
                    "project": project_name,
                    "selection_rule": "first forty eligible fixed-size windows encountered on an evenly spaced candidate grid over the interior of an oldest-first non-merge prefix",
                    "window_ordinal": start + 1,
                    "source_commit_count": len(records),
                },
            )
        )
        if len(histories) >= desired:
            break
    return histories


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-commit-count", type=int)
    parser.add_argument("--project-name", default="noVNC")
    parser.add_argument("--window-size", type=int, default=8)
    parser.add_argument("--desired", type=int, default=40)
    args = parser.parse_args()
    histories = build_histories(
        args.repository,
        args.project_name,
        args.source_commit_count,
        args.window_size,
        args.desired,
    )
    if len(histories) < args.desired:
        raise SystemExit(f"only {len(histories)} eligible histories were found")
    save_histories(
        args.output,
        histories,
        metadata={
            "source_project": args.project_name,
            "history_count": len(histories),
            "identities": "pseudonymous first-appearance aliases",
            "source_code_included": False,
            "source_commit_count": args.source_commit_count,
            "selection_order": "oldest-first non-merge prefix with an interior evenly spaced candidate grid",
        },
    )
    print(json.dumps({"histories": len(histories), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
