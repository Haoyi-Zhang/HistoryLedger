"""Independent exact diagnostic consumer and same-information direct baseline.

Only standard-library code is imported. The evidence surface is a supplied
positive-event ledger with resolved actor-class labels and exact integer units.
It does not authenticate this ledger, resolve aliases or certify a rewrite.
"""
from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path

MODES = ("loss_of_unique", "strict_overtake")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def label(value):
    return isinstance(value, str) and bool(value.strip())


def surface(events):
    require(isinstance(events, list) and 1 <= len(events) <= 4096, "event-list bound or shape")
    seen, totals, by_id = set(), {}, {}
    for event in events:
        require(isinstance(event, dict) and set(event) == {"atom_id", "owner", "entity", "units"}, "event fields")
        require(all(label(event[k]) for k in ("atom_id", "owner", "entity")), "nonblank literal labels required")
        require(integer(event["units"], 1) and len(str(event["units"])) <= 60, "canonical positive event units required")
        require(event["atom_id"] not in seen, "duplicate event identifier")
        seen.add(event["atom_id"])
        by_id[event["atom_id"]] = event
        totals[event["owner"]] = totals.get(event["owner"], 0) + event["units"]
    maximum = max(totals.values())
    leaders = [actor for actor, value in totals.items() if value == maximum]
    require(len(leaders) == 1, "unique initial leader required")
    return totals, leaders[0], by_id


def closes(gain, deficit, mode):
    return gain >= deficit if mode == "loss_of_unique" else gain > deficit


def gains_for(events, leader, challenger):
    return [event["units"] * (2 if event["owner"] == leader else 1)
            for event in events if event["owner"] != challenger]


def direct_radii(events):
    """Compute both exact radii without receiving a producer diagnostic.

    Same events/classes/units and thresholds, separate heap-based calculation.
    It is an algorithmic baseline, not an independently specified threat model.
    """
    totals, leader, _ = surface(events)
    answers = {}
    for mode in MODES:
        values = []
        for challenger in totals:
            if challenger == leader:
                continue
            heap = [-gain for gain in gains_for(events, leader, challenger)]
            heapq.heapify(heap)
            deficit, gain, count = totals[leader] - totals[challenger], 0, 0
            while not closes(gain, deficit, mode):
                require(bool(heap), "no attainable challenger")
                gain -= heapq.heappop(heap)
                count += 1
            values.append(count)
        answers[mode] = min(values) if values else None
    return answers


def verify(record):
    require(isinstance(record, dict) and set(record) == {
        "schema", "history_id", "quantum", "leader", "score_units", "events", "queries"}, "record fields")
    require(record["schema"] == "rivet-leadership-v1" and record["quantum"] == "1e-12", "record version")
    require(label(record["history_id"]), "history identifier")
    totals, leader, by_id = surface(record["events"])
    require(record["leader"] == leader, "leader differs from independent totals")
    require(isinstance(record["score_units"], dict) and set(record["score_units"]) == set(totals), "score coverage")
    require(all(integer(value, 1) for value in record["score_units"].values()) and record["score_units"] == totals,
            "score units differ from independent totals")
    queries = record["queries"]
    require(isinstance(queries, dict) and set(queries) == set(MODES), "both threshold queries required")
    challengers = set(totals) - {leader}
    checked = {}
    for mode in MODES:
        query = queries[mode]
        require(isinstance(query, dict) and set(query) == {
            "minimum_relabels", "challenger", "witness_atoms", "pairwise"}, "query fields")
        require(isinstance(query["pairwise"], list) and len(query["pairwise"]) == len(challengers), "complete challenger rows required")
        rows = {}
        for row in query["pairwise"]:
            require(isinstance(row, dict) and set(row) == {
                "challenger", "minimum_relabels", "initial_gap_units", "max_smaller_budget_gain_units",
                "witness_gain_units", "margin_units", "witness_atoms"}, "pairwise fields")
            challenger = row["challenger"]
            require(isinstance(challenger, str) and challenger in challengers and challenger not in rows, "challenger coverage or duplicate")
            k = row["minimum_relabels"]
            require(integer(k, 1) and k <= len(by_id), "radius integer or bound")
            ids = row["witness_atoms"]
            require(isinstance(ids, list) and len(ids) == k and all(isinstance(i, str) for i in ids)
                    and len(set(ids)) == k and all(i in by_id for i in ids), "witness identifiers")
            require(all(by_id[i]["owner"] != challenger for i in ids), "witness contains a no-op relabeling")
            deficit = totals[leader] - totals[challenger]
            gain = sum(by_id[i]["units"] * (2 if by_id[i]["owner"] == leader else 1) for i in ids)
            after = dict(totals)
            for atom_id in ids:
                event = by_id[atom_id]
                after[event["owner"]] -= event["units"]
                after[challenger] += event["units"]
            require(after[challenger] - after[leader] == gain - deficit
                    and sum(after.values()) == sum(totals.values()), "witness transfer replay")
            smaller = sum(heapq.nlargest(k - 1, gains_for(record["events"], leader, challenger)))
            expected = {"initial_gap_units": deficit, "max_smaller_budget_gain_units": smaller,
                        "witness_gain_units": gain, "margin_units": gain - deficit}
            require(all(integer(row[key]) and row[key] == value for key, value in expected.items()), "gain or deficit arithmetic")
            require(closes(gain, deficit, mode), "witness does not meet the requested threshold")
            require(not closes(smaller, deficit, mode), "smaller budget already meets threshold")
            rows[challenger] = row
        require(set(rows) == challengers, "missing global-optimality challenger")
        if not rows:
            require(query["minimum_relabels"] is None and query["challenger"] is None and query["witness_atoms"] == [],
                    "one-actor result must report no observed challenger")
            checked[mode] = None
            continue
        radius = min(row["minimum_relabels"] for row in rows.values())
        require(integer(query["minimum_relabels"], 1) and query["minimum_relabels"] == radius, "global radius")
        chosen = query["challenger"]
        require(isinstance(chosen, str) and chosen in rows and rows[chosen]["minimum_relabels"] == radius,
                "selected challenger is not globally minimal")
        require(query["witness_atoms"] == rows[chosen]["witness_atoms"], "selected witness differs")
        checked[mode] = radius
    return {"history_id": record["history_id"], "leader": leader, "radii": checked,
            "events": len(by_id), "challengers": len(challengers)}


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "duplicate JSON key")
        out[key] = value
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    require(args.record.stat().st_size <= 8 * 1024 * 1024, "record exceeds byte bound")
    record = json.loads(args.record.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    print(json.dumps(verify(record), sort_keys=True))
