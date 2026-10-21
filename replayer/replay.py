#!/usr/bin/env python3
"""Independent canonical-ledger replayer.

This file intentionally imports no project package. It validates event rows,
recomputes literal-origin totals as exact units on the frozen decimal surface, and compares
those totals and rows with a separately serialized expectation. It uses only
the Python standard library. This scalar format represents singleton actor
classes only. Optional normalized histories are independently preflighted and
bound to the ledger rows; CSV-only replay cannot check a discarded commit graph.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import Counter, defaultdict, deque
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {
    "history_id",
    "atom_id",
    "entity",
    "weight",
    "origin",
    "kind",
}
ALLOWED_KINDS = frozenset({"structural", "cosmetic"})
WEIGHT_QUANTUM = Decimal("0.000000000001")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError("missing columns: " + ", ".join(missing))
        return list(reader)


def decimal_weight(value: str) -> Decimal:
    try:
        candidate = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid numeric weight {value!r}") from exc
    if not candidate.is_finite():
        raise ValueError(f"nonfinite numeric weight {value!r}")
    try:
        with localcontext() as context:
            context.prec = 60
            return candidate.quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise ValueError(f"numeric weight outside canonical range {value!r}") from exc


def canonical_row(row: dict[str, str]) -> tuple[str, str, str, Decimal, str, str]:
    # Labels are opaque local keys in the history model. Whitespace is used
    # only to reject blank labels, never to silently rename a valid key.
    history_id = row["history_id"]
    atom_id = row["atom_id"]
    entity = row["entity"]
    origin = row["origin"]
    kind = row["kind"]
    location = f"{history_id or '<blank>'}:{atom_id or '<blank>'}"
    if not history_id.strip():
        raise ValueError(f"blank history identifier at {location}")
    if not atom_id.strip():
        raise ValueError(f"blank event identifier at {location}")
    if not entity.strip():
        raise ValueError(f"blank entity at {location}")
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unknown event kind at {location}: {kind!r}")
    weight = decimal_weight(row["weight"])
    if weight < 0:
        raise ValueError(f"negative weight at {location}")
    if kind == "structural" and weight <= 0:
        raise ValueError(f"nonpositive structural weight at {location}")
    if kind == "cosmetic" and weight != 0:
        raise ValueError(f"nonzero cosmetic weight at {location}")
    if kind == "structural" and not origin.strip():
        raise ValueError(f"missing origin at {location}")
    if kind == "cosmetic" and origin and not origin.strip():
        raise ValueError(f"blank cosmetic origin at {location}")
    return (history_id, atom_id, entity, weight, origin, kind)


def preflight_histories(payload: Any) -> list[dict[str, str]]:
    """Validate the supplied singleton-class histories without project imports.

    Return their event rows so a valid but unrelated graph cannot stand in for
    the history whose ledger is being checked. This is not source authentication.
    """
    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError("invalid normalized history: " + message)

    def label(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    histories = payload.get("histories") if isinstance(payload, dict) else payload
    require(isinstance(histories, list), "histories must be a list")
    seen_histories: set[str] = set()
    rows: list[dict[str, str]] = []
    for history in histories:
        require(isinstance(history, dict), "history must be an object")
        name = history.get("history_id")
        require(label(name) and name not in seen_histories, "blank or duplicate history identifier")
        seen_histories.add(name)
        require(isinstance(history.get("metadata", {}), dict), "metadata must be an object")
        for relation in ("must_link", "may_link"):
            require(history.get(relation, []) == [], "scalar replay requires empty alias declarations")
        pairs = history.get("entity_equivalence", [])
        require(isinstance(pairs, list), "entity-equivalence must be a list")
        seen_pairs = set()
        for pair in pairs:
            require(isinstance(pair, list) and len(pair) == 2 and all(label(x) for x in pair),
                    "invalid entity-equivalence pair")
            key = tuple(sorted(pair))
            require(pair[0] != pair[1] and key not in seen_pairs, "reflexive or duplicate entity-equivalence")
            seen_pairs.add(key)
        commits = history.get("commits")
        require(isinstance(commits, list), "commits must be a list")
        by_id: dict[str, dict] = {}
        events: set[str] = set()
        for commit in commits:
            require(isinstance(commit, dict), "commit must be an object")
            cid = commit.get("commit_id")
            require(label(cid) and cid not in by_id, "blank or duplicate commit identifier")
            require(label(commit.get("alias")), "blank commit alias")
            by_id[cid] = commit
            atoms = commit.get("atoms", [])
            require(isinstance(atoms, list), "atoms must be a list")
            for atom in atoms:
                require(isinstance(atom, dict), "event must be an object")
                require(set(atom) <= {"atom_id", "entity", "weight", "origin", "kind", "raw_lines", "raw_tokens"}
                        and {"atom_id", "entity", "weight", "origin"} <= set(atom), "invalid event fields")
                eid = atom.get("atom_id")
                require(label(eid) and eid not in events, "blank or duplicate event identifier")
                events.add(eid)
                for counter in ("raw_lines", "raw_tokens"):
                    value = atom.get(counter, 0)
                    require(type(value) is int and value >= 0, "invalid " + counter)
                origin = atom["origin"]
                require(origin is None or isinstance(origin, str), "invalid origin type")
                require(label(atom["entity"]), "blank entity")
                row = dict(history_id=name, atom_id=eid, entity=atom["entity"],
                           weight=str(atom["weight"]), origin="" if origin is None else origin,
                           kind=atom.get("kind", "structural"))
                canonical_row(row)
                rows.append(row)
        indegree = {cid: 0 for cid in by_id}
        children: dict[str, list[str]] = defaultdict(list)
        for cid, commit in by_id.items():
            predecessors = commit.get("predecessors", [])
            require(isinstance(predecessors, list), "predecessors must be a list")
            require(all(label(p) for p in predecessors), "invalid predecessor label")
            require(len(predecessors) == len(set(predecessors)), "duplicate predecessor")
            for predecessor in predecessors:
                require(predecessor in by_id and predecessor != cid, "missing or self predecessor")
                children[predecessor].append(cid)
                indegree[cid] += 1
        pending = deque(cid for cid, degree in indegree.items() if degree == 0)
        visited = 0
        while pending:
            visited += 1
            for child in children[pending.popleft()]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    pending.append(child)
        require(visited == len(by_id), "commit predecessor graph contains a cycle")
    return rows


def replay(rows: list[dict[str, str]], *, histories: Any = None) -> dict[str, Any]:
    if histories is not None:
        try:
            history_rows = preflight_histories(histories)
        except Exception as exc:
            return {"errors": [str(exc)], "rows": [], "scores": {}}
    identifiers: Counter[tuple[str, str]] = Counter()
    scores: dict[str, dict[str, list[Decimal]]] = defaultdict(lambda: defaultdict(list))
    canonical: list[tuple[str, str, str, Decimal, str, str]] = []
    errors: list[str] = []
    for row in rows:
        try:
            item = canonical_row(row)
        except Exception as exc:  # deterministic diagnostic surface
            errors.append(str(exc))
            continue
        history_id, atom_id, _entity, weight, origin, kind = item
        identifiers[(history_id, atom_id)] += 1
        if kind == "structural":
            scores[history_id][origin].append(weight)
        canonical.append(item)
    for (history_id, atom_id), count in sorted(identifiers.items()):
        if count != 1:
            errors.append(f"event multiplicity {count} at {history_id}:{atom_id}")

    def units(value: Decimal) -> int:
        sign, digits, exponent = value.as_tuple()
        if exponent != -12:
            raise ValueError(f"weight is not on the canonical surface: {value!r}")
        magnitude = int("".join(str(digit) for digit in digits) or "0")
        return -magnitude if sign else magnitude

    def format_units(value: int) -> str:
        return format(Decimal(f"{value}e-12"), ".12f")

    replayed_scores = {
        history_id: {
            alias: format_units(sum(units(value) for value in values))
            for alias, values in sorted(history_scores.items())
        }
        for history_id, history_scores in sorted(scores.items())
    }
    canonical_rows = [
        [history_id, atom_id, entity, format(weight, ".12f"), origin, kind]
        for history_id, atom_id, entity, weight, origin, kind in sorted(canonical)
    ]
    result = {
        "errors": sorted(set(errors)),
        "rows": canonical_rows,
        "scores": replayed_scores,
    }
    if histories is not None:
        # Use the same mismatch categories as the separately supplied expected
        # rows/totals. Fault counts do not depend on two agreeing expectations.
        reference = replay(history_rows)
        result["errors"] = compare(result, reference)
    return result



def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise

def compare(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors = list(actual.get("errors", []))
    if actual.get("rows") != expected.get("rows", []):
        errors.append("canonical event rows differ from expected ledger")
    if actual.get("scores") != expected.get("scores", {}):
        errors.append("replayed actor totals differ from expected totals")
    return sorted(set(errors))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--histories", type=Path,
                        help="preflight normalized histories and bind their events to the CSV")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        histories = json.loads(args.histories.read_text(encoding="utf-8")) if args.histories else None
        if args.histories and histories is None:
            raise ValueError("histories document must not be null")
        actual = replay(read_rows(args.ledger), histories=histories)
        errors = actual["errors"]
        if args.expected:
            expected = json.loads(args.expected.read_text(encoding="utf-8"))
            errors = compare(actual, expected)
        result = {
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "history_count": len(actual["scores"]),
            "event_count": len(actual["rows"]),
        }
    except Exception as exc:
        result = {
            "status": "FAIL",
            "errors": [str(exc)],
            "history_count": 0,
            "event_count": 0,
        }
    result["history_validation"] = ("PASS" if result["status"] == "PASS" else "FAIL") if args.histories else "NOT_SUPPLIED"
    result["scope"] = "normalized histories, ledger rows and totals" if args.histories else "CSV rows and totals only; commit graph unavailable"
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_text_atomic(args.output, text)
    print(text, end="")
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
