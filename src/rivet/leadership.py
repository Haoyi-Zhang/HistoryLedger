"""Replayable exact loss-of-uniqueness and strict-overtake diagnostics.

This extends the stated resolved-identity/event-relabeling model, not extraction
or identity inference. It adds no new score and leaves the strict-radius API
unchanged. The standalone consumer imports no Rivet code.
"""
from __future__ import annotations

import json

from .influence import _resolved_origins
from .model import History
from .numeric import weight_units


def leadership_diagnostic(history: History) -> dict:
    scores, roots = _resolved_origins(history)
    if not scores:
        raise ValueError("leadership diagnostic needs a scored actor")
    maximum = max(scores.values())
    leaders = [actor for actor, value in scores.items() if value == maximum]
    if len(leaders) != 1:
        raise ValueError("leadership diagnostic needs a unique initial leader")
    leader = leaders[0]
    events = sorted(({
        "atom_id": event.atom_id, "entity": event.entity,
        "owner": roots.get(event.origin, event.origin), "units": weight_units(event.weight),
    } for event in history.atoms(include_cosmetic=False)), key=lambda e: e["atom_id"])
    if not 1 <= len(events) <= 4096:
        raise ValueError("leadership record permits one through 4096 positive events")
    outputs = {}
    for mode in ("loss_of_unique", "strict_overtake"):
        pairwise = []
        for challenger in sorted(actor for actor in scores if actor != leader):
            gap = scores[leader] - scores[challenger]
            gains = sorted(((2 * event["units"] if event["owner"] == leader else event["units"],
                             event["atom_id"]) for event in events if event["owner"] != challenger),
                           key=lambda entry: (-entry[0], entry[1]))
            cumulative, before, witness = 0, 0, []
            for gain, atom_id in gains:
                before = cumulative
                cumulative += gain
                witness.append(atom_id)
                if cumulative > gap or (mode == "loss_of_unique" and cumulative == gap):
                    break
            if cumulative < gap or (mode == "strict_overtake" and cumulative == gap):
                raise AssertionError("positive leader mass should permit a challenger")
            pairwise.append({"challenger": challenger, "minimum_relabels": len(witness),
                             "initial_gap_units": gap, "max_smaller_budget_gain_units": before,
                             "witness_gain_units": cumulative, "margin_units": cumulative - gap,
                             "witness_atoms": witness})
        best = min(pairwise, key=lambda row: (row["minimum_relabels"], row["challenger"])) if pairwise else None
        outputs[mode] = {"minimum_relabels": best["minimum_relabels"] if best else None,
                         "challenger": best["challenger"] if best else None,
                         "witness_atoms": best["witness_atoms"] if best else [],
                         "pairwise": pairwise}
    record = {"schema": "rivet-leadership-v1", "history_id": history.history_id,
              "quantum": "1e-12", "leader": leader, "score_units": dict(sorted(scores.items())),
              "events": events, "queries": outputs}
    if len(json.dumps(record, sort_keys=True).encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("leadership record exceeds its eight-MiB byte bound")
    return record
