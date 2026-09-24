# Rivet artifact

Rivet checks technical contribution scores over **frozen normalized events**, not program behavior, effort, or identity truth. A valid event certificate supplies a total one-to-one map over positive events and preserves each event's canonical twelve-place weight, declared origin class, entity class, and active identity-uncertainty partition. Commit containers, order, and local event identifiers may change. Unknown positive origins or unresolved may-links produce abstention or interval answers rather than fabricated point rankings.

The artifact contains three complementary evidence layers:

1. **Normalized histories.** Forty windows of eight commits from one noVNC history contain 320 commits and 610 positive token-change events. They support event-level certificate, baseline, alias, influence, witness, and replay experiments. They are not forty repositories, and the original source snapshots are absent.
2. **Exact source controls.** Eight bounded synthetic source histories demonstrate identical-endpoint path dependence, a positive reversible cycle, and three behavior-changing edits missed by the token proxy. They delimit, rather than validate, source semantics.
3. **Public patch boundary corpus.** Twelve exact MIT-licensed patch cases from twelve public repositories span fourteen source files in Python, JavaScript, TypeScript, Rust, and C++; one case is a comment-only negative control. Endpoint extraction certifies all 12 retained endpoint pairs. Path-additive alternatives disagree with the endpoint mass for 3 hunk decompositions, 3 contiguous-block decompositions, and 8 delete-then-add decompositions; all 11 positive endpoint edits induce a positive edit/reverse cycle. These are descriptive boundary cases, not a representative prevalence study. No upstream program is executed.

## Reproduction

A standard Python 3 installation and a POSIX shell suffice. No third-party package, private input, or network connection is required. The alias campaign is intentionally split into bounded resumable generation and independent-check chunks; run the stages in this order and then the joint checker:

```sh
sh scripts/reproduce.sh events
sh scripts/reproduce.sh boundary-low
sh scripts/reproduce.sh boundary-cap
sh scripts/reproduce.sh boundary-check-low
sh scripts/reproduce.sh boundary-check-cap
sh scripts/reproduce.sh boundaries
sh scripts/reproduce.sh sources
sh scripts/check.sh
```

The low chunk covers ternary masses through six roots; the cap chunk covers binary masses at seven roots. Their independent consumers write explicit receipts before the boundary summary is finalized. The checker runs 117 unit/integration tests, validates all 41 claim-ledger rows and their current evidence surfaces, independently replays canonical ledgers, checks frozen rows and summaries, and validates every source-control and public-patch contract. Scientific stage outputs are written to same-directory temporary files and published by atomic replacement only after successful close; a restarted stage removes stale siblings left by a hard interruption. The boundary finalizer and joint checker read every gzip member to end of stream, verify the frozen problem-row count, and reject residual temporary files. The stages regenerate every reported numerical result from retained inputs. Unknown stage names and extra arguments fail with exit code 2 before scientific execution. `sh scripts/reproduce.sh all` remains a convenience wrapper around the same ordered stages, while the explicit commands expose resumable checkpoints.

The bounded campaigns include 3,510 tiny histories with 27,570 obligations, 2,514 exact winner-radius oracle cases, 320 frozen-event public comparisons, 40 origin erasures, 480 one-component alias trials, 200 influence rows, 280 certificate mutations, seven replay faults, eight synthetic source controls, twelve public patch cases, and 1,742,198 whole-set target cases across 274,250 mass/component problems. Adverse outcomes and abstentions are retained.

## All-component alias ranks

The global routine consumes exact nonnegative integer-unit masses and a complete partition into may-link components. Every partition within a component is admissible; blocks cannot cross components. Each component is capped at seven roots, but the total root count may be larger. The best-rank formula merges the target component; the worst-rank recurrence counts the maximum number of actor blocks strictly above the singleton target mass. Both complete attaining partitions are returned.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python - <<'PYCODE'
from rivet.global_aliases import exact_global_rank_interval_units
answer = exact_global_rank_interval_units(
    {'T': 5, 'B': 3, 'C': 3}, [('T',), ('B', 'C')], 'T')
assert (answer.best_rank, answer.worst_rank) == (1, 2)
print(answer)
PYCODE
```

The older single-component routine remains available for the 480 historical sensitivity trials; it holds every outside root fixed. It must not be described as global uncertainty propagation. The exact best-rank formula is linear after component sums and maxima are known, whereas the unbounded worst-rank decision problem is strongly NP-complete by reduction from 3-PARTITION. The seven-root cap is therefore an explicit exact-tractability boundary, not an arbitrary search cutoff.

`replayer/alias_rank_oracle.py` imports none of the optimizer. It independently enumerates whole-set restricted-growth partitions, rejects duplicate or incomplete members, and checks both bounds and every attaining witness. The complete frozen domains are ternary masses through six roots and binary masses at the seven-root cap. The retained evidence is split into seven deterministic gzip members under `results/global_alias_oracle/`; for example:

```sh
PYTHONDONTWRITEBYTECODE=1 python replayer/alias_rank_oracle.py results/global_alias_oracle/roots-7.jsonl.gz --root-count 7
```

The separate 56-root example has interval `[1,48]` and independently checked witnesses. It is not an exhaustive 56-root search.

## Source boundary and endpoint contract

`external_inputs/source_cases.json` retains the eight synthetic controls. `external_inputs/public_patch_cases.json` retains the exact consumed public patch fragments; its manifest and `THIRD_PARTY_NOTICES.md` record repository, language, license-file path, project-specific copyright notice, and inclusion scope. The patch adapter parses header-free unified hunks and computes:

- one **endpoint mass** from the retained old and new token multisets;
- hunk- and contiguous-block path sums;
- an adversarial delete-then-add path sum; and
- an edit/reverse cycle sum.

For a retained endpoint pair `(x,z)`, endpoint-anchored extraction evaluates the deterministic extractor once as `E(x,z)`. Two history spellings that retain the same endpoints, use that same extractor, and preserve complete origin/entity declarations therefore expose the same event surface by construction. This is a representation contract, not proof that the endpoints are behaviorally equivalent, that extraction is semantically complete, or that an origin map is authentic. Path-additive activity accounting remains subject to the cycle obstruction and the observed decomposition mismatches.

`results/source_boundary.csv`, `results/public_patch_boundary.csv`, and their summaries record every case. `proofs/guarantees.md` gives the conditional event theorem, exact recoverability boundary, alias proof, winner-radius argument, nonnegative-cycle obstruction, and endpoint-anchored proposition.

## Input provenance and limits

`data/public_windows.json` is the authoritative normalized-history input. It contains numeric events and pseudonymous labels, not upstream source snapshots. Its recorded extraction rule used an oldest-first prefix of 2,141 non-merge records and a fixed candidate grid, but the original source derivation cannot be reconstructed from this package. Optional re-extraction from a compatible local checkout is documented in `external_inputs/README.md`; it is not part of offline reproduction.

The twelve public patch cases are a separate lawful source-boundary corpus. Only the exact bounded patch fragments consumed by the experiment are redistributed under their declared MIT licenses and notices. The sample is deliberately convenience-based and stratified by language; it cannot establish cross-ecosystem frequency, ranking validity, or semantic accuracy. No commit identifiers, personal identities, messages, timestamps, or repository history are retained.

Event ingestion uses half-even rounding to twelve decimal places and rejects coefficients above sixty digits. Aggregate and alias calculations use exact integer units. Exact local alias enumeration is capped at seven roots per component; exact event-witness minimization is capped at fourteen events. A consistent ledger cannot authenticate fabricated events, incorrect origins, or an invalid extractor.

## Layout and license

`src/rivet/` contains the implementation and deterministic experiments; `tests/` contains the checks; `replayer/` contains independently structured consumers; `proofs/` contains the mathematical obligations; `data/` and `external_inputs/` contain fixed lawful inputs; and `results/` contains complete numerical surfaces. `claim_evidence_ledger.csv` links public claims to evidence objects.

Original Rivet code and synthetic fixtures use the MIT license in `LICENSE`. Upstream public patch notices are in `external_inputs/THIRD_PARTY_NOTICES.md`. No upstream program, model, service, or private dataset is executed.
