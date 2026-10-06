# Rivet artifact

Rivet checks technical contribution scores over **frozen normalized events**, not program behavior, effort, or identity truth. A valid event certificate supplies a total one-to-one map over positive events and preserves each event's canonical twelve-place weight, declared origin class, entity class, and active identity-uncertainty partition. Commit containers, order, and local event identifiers may change. Unknown positive origins or unresolved may-links produce abstention or interval answers rather than fabricated point rankings.

The artifact contains three complementary evidence layers:

1. **Normalized histories.** Forty windows of eight commits from one noVNC history contain 320 commits and 610 positive token-change events. They support event-level certificate, baseline, alias, influence, witness, and replay experiments. They are not forty repositories, and the original source snapshots are absent.
2. **Exact source controls.** Eight bounded synthetic source histories demonstrate identical-endpoint path dependence, a positive reversible cycle, and three behavior-changing edits missed by the token proxy. They delimit, rather than validate, source semantics.
3. **Public patch boundary corpus.** Twelve exact MIT-licensed patch cases from twelve public repositories span fourteen source files in Python, JavaScript, TypeScript, Rust, and C++; one case is a comment-only negative control. Endpoint extraction certifies all 12 retained endpoint pairs. Path-additive alternatives disagree with the endpoint mass for 3 hunk decompositions, 3 contiguous-block decompositions, and 8 delete-then-add decompositions; all 11 positive endpoint edits induce a positive edit/reverse cycle. These are descriptive boundary cases, not a representative prevalence study. No upstream program is executed.

## Reproduction

A standard Python 3.10 or newer installation and a POSIX shell suffice. No third-party package, private input, or network connection is required. The alias campaign is intentionally split into bounded resumable generation and independent-check chunks; run the stages in this order and then the joint checker:

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

The low chunk covers ternary masses through six roots; the cap chunk covers binary masses at seven roots. Their independent consumers write receipts binding the exact gzip bytes and independent checker source (SHA-256) before the boundary summary is finalized. The finalizer rejects stale, legacy or mismatched receipts; these local content bindings are not signatures or provenance authentication. The checker runs 156 unit/integration tests, validates all 41 claim-ledger rows and their current evidence surfaces, independently replays canonical ledgers, checks frozen rows and summaries, and validates every source-control and public-patch contract. Scientific stage outputs are written to same-directory temporary files and published by atomic replacement only after successful close; a restarted stage removes stale siblings left by a hard interruption. The boundary finalizer and joint checker read every gzip member to end of stream, verify the frozen problem-row count, and reject residual temporary files. The stages regenerate every reported numerical result from retained inputs. Unknown stage names and extra arguments fail with exit code 2 before scientific execution. `sh scripts/reproduce.sh all` remains a convenience wrapper around the same ordered stages, while the explicit commands expose resumable checkpoints.

The bounded campaigns include 3,510 tiny histories with 27,570 obligations, 2,514 exact winner-radius oracle cases, 320 frozen-event public comparisons, 40 origin erasures, 480 one-component alias trials, 200 influence rows, 280 certificate mutations, seven replay faults, eight synthetic source controls, twelve public patch cases, and 1,742,198 whole-set target cases across 274,250 mass/component problems. Adverse outcomes and abstentions are retained.

## Certificate features and result conventions

Rewrite certification computes the must-link classes and may-link connectivity
of each endpoint separately, retaining declaration-only and other zero-mass
aliases. Only then does a validated cross-endpoint class bridge translate the
active partitions to common keys; it cannot inject one endpoint's must-links
into the other endpoint's connectivity or merge distinct local classes.

For an actor-local vector statistic, `certify_rewrite` additionally accepts
`original_features` and `rewritten_features`: complete maps from every local
event identifier to a nonempty tuple of finite nonnegative canonical coordinates
of one common dimension. It checks every mapped positive vector and requires
every zero-scalar event's vector to be all zero. The scalar-only interface and
the scalar ledger replayer certify no unprovided vector features. Nonzero vector
support on a zero-scalar event needs an extended event-map interface; it is
refused by the current checked-premise mode even if that event is retained.

Kendall tau-b aligns scores on the alias-label union with absent scores set to
zero and uses exact integer signs for ordering and ties. A zero denominator
returns `None`, serialized as a blank CSV value, never an imputed zero or one.
`public_summary.csv` reports defined, undefined, and unavailable counts beside
each mean; unavailable means no point scores due to alias or origin abstention.
Only defined values enter a mean. The 2,400 rows contain 2,288 defined, 32
undefined, and 80 unavailable correlations. Split/commit-count has 36 defined
and four undefined cases, mean 0.9213169466181262; certified-squash/commit-count
has 38 defined and two undefined, mean 0.09220607987853582.

`exact_minimal_atom_witness` includes the empty subset. Its result is `()` for
a found empty witness, a nonempty tuple for a found nonempty witness, or `None`
for no solution. Test `is None`, not tuple truthiness. Restricted histories keep
their containers and declarations, so a container-only predicate can have an
empty event witness. The default fourteen-event cap is checked before searching.

The winner-flip radius is strict overtaking of the initial leader: its gain must
exceed the deficit. Tying the leader can lose unique leadership earlier; three
unit events owned by A and one by B tie after one relabeling but require two
for a strict overtake. The existing strict radii and witnesses are retained.

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

## Directed reviewer regressions (F1--F11)

The current directed regression tests run in the primary checker. To run them
without regenerating numerical results, use:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests -v
```

These tests are deliberately bounded. They check endpoint-local alias
state, exact integer rank influence, the vector-feature support premise,
class-level tie semantics, empty versus absent minimal witnesses, the actual
tiny-history categories, three independently readable decision records,
current gzip members and stale-receipt rejection, per-case upstream
provenance status, the two different winner radii, and the separate cost of
aggregation, sorting, pairwise output, and component search.  The decision
records are a local replay interface; they are not described as a complete
repository-wide certificate service.

The older `scripts/reproduce-reviewer.sh` editorial generator is not part of
the current scientific route: its summary/member-schema assumptions do not
match the retained results. Do not use its output as evidence for this paper.
The supported numerical route is `scripts/reproduce.sh`, followed by the
retained and strengthened failure gates in `scripts/check.sh`.

Literal event and actor labels are opaque: replay validates nonblank labels
without trimming meaningful whitespace. Across certified rewrites, score
equality and competition ranks are compared under common class keys; the
alphabetical display order of tied local aliases need not be invariant.
`analyze_history(..., include_pairwise=False)` suppresses only the quadratic
pairwise judgment report. It preserves the numeric and abstention decisions;
the current API does not provide a streaming pairwise report.
Witness search defaults to 14 shared structural event identifiers and refuses
larger surfaces before testing any subset. A caller may explicitly change
`maximum_atoms` to another positive integer; this changes its exponential
resource envelope. It does not raise either immutable seven-root alias cap.

## Native Linux reproduction and measurements

The completed native run 37433637628 used head
`9bb0d56ac15f357fa554649c341ca23f2f96dc5f` and the flat-artifact
`sh scripts/reproduce.sh all` workflow, configured for Ubuntu 24.04 and Python
3.12. Its archived output records 156 passing tests in 1.392 seconds, canonical
replay of 641 rows across 40 histories, and passing claim-ledger, frozen-result,
alias/source-boundary, and public-patch/license-notice gates. The independent
alias receipts report zero bound mismatches and zero invalid witnesses across
274,250 problems and 1,742,198 targets in the stated finite domains.

The native archive's 25 structured data files and two license/notice files match
the retained files as parsed data or exact notice text. Twenty-three also match
byte-for-byte, including all seven gzip members and both digest-bound receipts;
the remaining differences are text serialization. No timing, source metadata,
operation counts, decisions, or scientific digest fields were omitted from the
comparison. Both identical-endpoint path counterexamples remain in
`results/source_boundary.csv`; they are negative extraction results, not failed
alias bounds. The decision-record examples are retained fixtures rather than
outputs regenerated by the whole-run command.

`results/measurements/native-linux.json` retains the native unit-suite timing.
The supplied archive contains no whole-run wall time, child CPU time, or peak
RSS measurement, so those fields remain null. This observation is not a speedup
or scalability result. `execution_observations.json` remains the separate,
unchanged historical host record, including its older 117-test count and stage
measurements. The earlier 156-test Windows replay is also distinct from this
native run. The scientific datasets are kept once; the native raw archive and
integration comparison remain outside the artifact.
