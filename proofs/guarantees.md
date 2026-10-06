# Formal obligations and proofs

## 1. Model

A normalized structural event is a tuple

\[
e=(\iota,q,w,o),
\]

where `iota` is a nonblank local event identifier, `q` a nonblank entity label,
`w` a positive finite weight on the frozen twelve-place decimal surface, and
`o` an origin alias or the distinguished unknown value. Cosmetic events have
exactly zero weight. A history groups events into commits and orders commits by
a finite acyclic predecessor relation. The scoring layer does not use the
commit grouping or order. A declared must-link relation induces origin classes;
a declared entity-equivalence relation induces entity classes. May-link
relations express unresolved identity alternatives and never certify equality.

For a nonnegative additive event functional, the score of origin class `a` is

\[
S_H(a)=\sum_{e\in E_H,\,[o(e)]=a} w(e).
\]

The bundled experiment instantiates `w` with formatting-insensitive
token-multiset edit mass times a bounded co-change salience term. The theorems
apply to any frozen nonnegative weights; they do not assert that the chosen
weights measure human value.

## 2. Certified rewrite invariance

**Definition 1 (certificate).** A rewrite from `H` to `H'` is certified when
both endpoints are locally valid and the comparison supplies a total one-to-one
map from the structural events of `H` onto those of `H'`. The map preserves
canonical event weight, declared origin class, and declared entity class. Each
endpoint first collapses its own must-links over all local aliases, including
zero-mass and declaration-only aliases, and computes connectivity from only its
own may-links. It then restricts this partition to score-bearing roots. A
cross-endpoint class bridge supplies common keys only after checking that it
does not merge distinct local classes on either side. The local active partitions
must agree through that correspondence; unioned must-links are never substituted
for endpoint-local connectivity. Different
edge sets may pass when they induce the same active partition, including through
inactive intermediary aliases. Local event identifiers only name the two sides
of the map and therefore need not be equal. When no explicit map is supplied, equal identifiers define the candidate
map. Cross-history declarations may connect corresponding labels but may not
merge two distinct local classes on either endpoint. Cosmetic zero-weight
events may be added or removed. Commit grouping, commit identifiers, and commit
order are outside the score.

**Theorem 1 (additive invariance).** If the certificate from `H` to `H'` is
valid, then `S_H(a)=S_H'(a)` for every declared origin class `a`, and the active
may-link partition is unchanged. The endpoints therefore agree on whether a
point ranking is admissible; when all active components are resolved, every
deterministic ranking rule applied to the vector indexed by common class keys
is invariant. Endpoint-local alias spelling is not an invariant tie key.

**Proof.** The certificate gives a bijection `f` from structural events of `H`
to structural events of `H'`. For each origin class `a`, restrict `f` to events
whose origins lie in `a`. Origin-class preservation makes this a bijection onto
the corresponding events of `H'`, and weight preservation makes each paired
summand equal. The two finite sums are equal. Applying the same deterministic
ranking rule to equal vectors gives equal rankings whenever the common active partition is resolved; otherwise both endpoints retain the same interval-valued decision regime. QED.

The implementation validates endpoint identifiers, event kinds, finite
canonical weights, cosmetic zero weight, origin availability, predecessor
references, acyclicity, relation consistency, event-map totality and
injectivity, cross-history class compatibility, and the active may-link
partition. Equality,
ordering, alias intervals, and influence decisions are made on exact integer
event units. Malformed evidence receives no score. The public study covers
eight certified transformation families over forty histories; the exhaustive
study checks seven certified families over one through four events, with a
fixed cyclic entity assignment and contiguous single-actor commit blocks.
Certified alias splitting is covered by the public-window layer, not the tiny
generator. A seven-family mutation campaign independently violates map
coverage, event-set coverage, weight, origin, entity, class compatibility, and
the active may-link partition; all 280 injected certificates are rejected.

**Proposition 1a (actor-local summary criterion).** Fix a finite event feature
vector `phi(e)`, and let `T_H(a)` be its coordinate-wise sum over the events
assigned to actor class `a`. Equality of every `T_H(a)` and `T_H'(a)` is
necessary and sufficient for equality of every deterministic presentation that
receives only these actor-local sums.

**Proof.** Sufficiency follows because a deterministic function maps equal
inputs to equal outputs. For necessity, if one actor and coordinate differ,
the deterministic presentation that projects exactly that coordinate separates
the two histories. QED.

An event certificate on the positive scalar surface preserving actor class and
every coordinate of `phi` provides a sufficient witness only under the support
premise `w(e)=0 => phi(e)=0` on both endpoints. Under this premise, mapped terms
cancel coordinate by coordinate and all unmatched zero-scalar terms vanish.
Without it, deleting a cosmetic event of weight zero and vector `(0,1)` changes
the vector sum despite preserving scalar mass. `certify_rewrite` checks the
premise when complete `original_features` and `rewritten_features` maps are
provided: every event must have a finite nonnegative vector of the common
dimension on the twelve-place canonical surface; every cosmetic vector must be
all zero; paired positive-event vectors must agree. A scalar-only call certifies
no unprovided coordinate, and the scalar ledger replayer does not validate vector
features. A nonzero feature on a zero-scalar event requires an extended support
interface rather than this positive-surface certificate. The criterion also
locates its limit: cross-actor interaction scores require preservation of the
pairwise or graph summaries they consume, and unknown origins or unresolved
may-links remain uncertain inputs rather than becoming precise under a
nonlinear display function.

**Proposition 1b (certificate composition).** If valid certificates relate
`H_0` to `H_1` and `H_1` to `H_2` under compatible origin, entity, and active
may-link declarations, then composing their event bijections yields a valid
certificate from `H_0` to `H_2`.

**Proof.** A composition of bijections is a bijection. Weight, origin-class,
and entity-class equality each hold across both edges and therefore across the
composition. Compatibility carries the same active may-link partition through
the middle endpoint. Endpoint validity is inherited from the premises. QED.

Compatibility is required: changing a class declaration, active may-link
partition, or feature interpretation crosses evidence or decision regimes and
needs an explicit bridge rather than a cached verdict.

## 3. Recoverability and provenance erasure

Let `O` map a latent prehistory to the observation available to an analysis,
and let `F` be the target output (for example, the actor score vector).

**Theorem 2 (observation-fiber criterion).** A deterministic recovery function
`g` on the image of `O` satisfying `g(O(H))=F(H)` for every admissible prehistory `H` exists if and
only if `F` is constant on every fiber of `O`: whenever `O(H_1)=O(H_2)`, then
`F(H_1)=F(H_2)`.

**Proof.** If `g` exists and two prehistories have the same observation, applying
`g` to that common observation gives equal target outputs. Conversely, if `F`
is constant on every fiber, define `g(y)` to be that common value for any
prehistory in the fiber `O^{-1}(y)`; the value is well-defined on the image of
`O`. This also covers an empty prehistory domain without requiring a value
outside that image. QED.

**Corollary 2a (cross-origin squash impossibility).** Let the target functional
distinguish at least two origin assignments over the same weighted event set.
No deterministic analysis that receives only a post-squash history with erased
per-event origins can be correct for every compatible prehistory.

**Proof.** Choose two compatible prehistories with the same event weights and
post-squash observation but different origin assignments and therefore
different target score vectors. The target is not constant on that observation
fiber, so Theorem 2 rules out deterministic universal recovery. QED.

Rivet therefore returns `ABSTAIN_ORIGIN` whenever a positive structural event
lacks origin provenance. This is an information boundary, not a claim that more
computation can reconstruct evidence absent from the input. Total event mass
may remain conserved while the actor allocation is unrecoverable.

## 4. Alias uncertainty

After must-link collapse, let a may-link connected component contain score roots
`C={c_1,...,c_k}`. Any partition of `C` is treated as an admissible identity
resolution for the bounded model.

**Lemma 3 (component score interval).** For any root `c` in `C`, its resolved
actor score lies in

\[
[s(c),\;\sum_{d\in C}s(d)].
\]

**Proof.** No admissible partition removes the mass already assigned to `c`,
giving the lower bound. The largest block containing `c` is the entire
component, giving the upper bound. The singleton and one-block partitions attain
the two endpoints. QED.

**Corollary 4 (certified cross-component order).** If the lower bound of one
root exceeds the upper bound of another root in a different may-link component,
their order is fixed under every admissible resolution. Otherwise the interval
test does not certify their order.

For one selected complete may-link component of size at most seven, the local
routine enumerates every partition and returns exact competition-rank bounds
while holding every outside root fixed. It is not the all-component routine below. It refuses a larger component rather than returning
an incomplete interval. The sensitivity generator partitions the source score
in exact integer units, so every one of the 480 trials conserves the component
mass exactly. On any unresolved component the analysis emits no single
person-level ranking or point influence result.

## 5. Attribution-tampering influence

The tampering model applies only after all structural origins and actor
identities are resolved. It relabels the origins of at most `b` existing
structural events to another observed actor class while preserving identifiers,
entities, weights, and the event set. This is an uncertified manipulation model.
If only one actor class is observed, no relabeling is admissible.

**Theorem 5 (exact score influence).** For actor `a`, the maximum score increase
under budget `b` is the sum of the `b` largest weights not currently assigned
to `a`. When a distinct observed destination exists, the maximum decrease is
the sum of the `b` largest weights currently assigned to `a`; otherwise it is
zero.

**Proof.** To increase `a`'s score, relabeling an event already owned by `a` has
no benefit, while relabeling another event adds exactly its weight. Selecting
the `b` largest eligible weights is optimal by exchange: replacing a selected
smaller weight with an unselected larger weight never decreases the objective.
The decrease case is symmetric. With one observed class, the eligible
relabeling set is empty. QED.

Combining independently optimized per-actor intervals yields a conservative
rank interval because the competitors share one global budget. The interval is
sound but its two endpoints need not both be attainable.

**Theorem 6 (exact strict-winner flip radius).** Let `l` be the unique current
winner and `c` a challenger with deficit `d_c=S(l)-S(c)`. Give each event a
challenger-specific gain

\[
g_c(e)=\begin{cases}
2w(e),&o(e)=l,\\
w(e),&o(e)\notin\{l,c\},\\
0,&o(e)=c.
\end{cases}
\]

Sort the positive gains nonincreasingly. The minimum number of origin
relabelings that makes `c` strictly outrank `l` is the shortest prefix whose
sum is greater than `d_c`. The strict-winner flip radius is the minimum of this
quantity over all challengers.

**Proof.** Relabeling a leader-owned event directly to `c` lowers the leader by
`w` and raises `c` by `w`, closing the gap by `2w`. Relabeling a third-party
event to `c` closes it by `w`; no change to a `c`-owned event helps. Any useful
set of `k` actions therefore closes at most the sum of the `k` largest gains,
and choosing those events attains that sum by sending each to `c`. A strict flip
occurs exactly when the cumulative gain exceeds `d_c`; the preceding prefix
proves that no smaller action set suffices. Minimizing across challengers gives
the global radius. QED.

This radius concerns strict overtaking of the initial leader, not first loss of
unique leadership. With three unit events assigned to A and one to B, one
relabeling ties the scores at `(2,2)`; two relabelings yield `(1,3)` and strictly
overtake A. The strict threshold remains `cumulative gain > deficit`.

The implementation returns the selected event identifiers, challenger,
pre-threshold cumulative gain, and strict winning margin. Exhaustive enumeration
of every origin reassignment agrees on all 2,514 generated tiny histories with
a unique winner and at least two actors.

## 6. Counterexample minimization

The exact witness routine enumerates subsets in increasing cardinality starting
with the empty subset, including when the shared universe is empty. It returns
`()` for a successful empty witness, a nonempty tuple for a nonempty witness,
and `None` for no solution. Commit containers and declarations are retained by
event restriction; a container-only predicate can therefore have an empty event
witness. Callers must use `is None` rather than tuple truthiness. When the
shared structural event set contains at most fourteen events, the first
satisfying subset is minimum cardinality for the supplied predicate. When the
surface exceeds the cap, the routine raises an error instead of truncating the
universe; it therefore emits no witness that could be mistaken for a globally
minimum result.

## 7. Independent replay

The replayer parses the serialized ledger using only the language standard
library, validates required columns and nonblank labels, accepts only structural
or cosmetic kinds, enforces positive finite structural weights and zero
cosmetic weights, checks unique event identifiers and structural origin
presence, recomputes actor totals as exact integer multiples of the twelve-place
quantum, serializes them as fixed-width decimal strings, and compares canonical
rows and totals with the separately serialized expectation. Nonblank labels
remain literal keys, including leading or trailing whitespace; kind tags are
matched exactly. It imports none of
the scoring package. This separation detects serialization and scoring-path
disagreement but is not a cryptographic authenticity claim; commit-graph
validity is checked before ledger export because the replay ledger intentionally
contains events rather than commit edges.


## 8. Exact global alias ranks

The roots have nonnegative exact integer-unit masses `s(u)`. The supplied
components form a partition `G` of every root, including singleton components.
All set partitions inside each component are admissible, and no block crosses a
component. This is a declared free-partition model, not an inference procedure
for sparse, probabilistic, or inconsistent identity evidence. Competition rank
is one plus the number of actor blocks with strictly greater mass.

**Theorem 7 (all-component decomposition).** For target `t` in component `G_t`,
put `T=sum(s(u),u in G_t)`, and let `B_tau(X)` be the largest number of blocks
with mass strictly above `tau` in a partition of `X`. Then

- best rank = `1 + sum(max(s(u),u in H)>T for H != G_t)`;
- worst rank = `1 + B_s(t)(G_t minus {t}) + sum(B_s(t)(H),H != G_t)`.

Both bounds are attained by full partitions of all roots.

**Proof of best rank.** Merging all roots of `G_t` into the target maximizes
its mass and removes all within-component competitors. This cannot worsen its
rank. An outside component containing a root above `T` must contain at least
one block above `T` under any partition, by nonnegativity. Merging that entire
component attains one. If every root is at most `T`, singleton blocks attain
zero. The independent component choices establish and attain the formula.

**Proof of worst rank.** Split the target out of its actor block, leaving any
nonempty remainder intact. Its mass cannot increase; every previously ahead
block remains ahead, and the detached remainder cannot remove a competitor.
Thus a maximum is attained with the target alone. At the resulting threshold
`s(t)`, the number of ahead blocks adds independently across the remaining
components and the remainder of `G_t`. Optimizing each yields the second formula.
Ties never count as ahead; the arguments remain valid for zero masses. QED.

**Subset recurrence.** Set `B_tau(empty)=0`. For a nonempty set `X`, choose its
least-labelled root `p`. Then

`B_tau(X)=max( int(sum(s(u),u in Y)>tau) + B_tau(X minus Y) )`,

where the maximum ranges over every subset `Y` of `X` containing `p`.
Every partition of `X` has exactly one such block containing `p`. Its remainder
is a smaller partitioning problem. Induction on cardinality proves both the
upper bound and attainability of the recurrence. The table stores one selected
block and reconstructs a full partition; deterministic tie-breaking changes the
witness spelling, never the optimum.

For one target and component sizes `k_H`, this takes `O(sum(3**k_H))` exact
integer operations. Processing components sequentially and releasing their
tables uses `O(number_of_roots + 2**max(k_H))` working storage. This excludes
the implementation's persistent, unlimited-entry mass-pattern memoization,
its all-target component-witness cache, and its batch output of two full
partitions per target. Bit complexity additionally depends on mass magnitude. The
executable routine refuses any component with more than seven roots, including
when a caller attempts to raise that cap. It also refuses negative or boolean
masses, duplicate or uncovered roots, and absent targets. The total root count
need not be at most seven.

**Theorem 7a (strong complexity boundary).** The decision problem that asks,
for positive integer masses, threshold `tau`, and integer `K`, whether some set
partition contains at least `K` blocks of mass strictly above `tau` is strongly
NP-complete. Consequently, deciding whether the worst alias rank of a singleton
target is at least `K+1` is strongly NP-complete when component size is
unbounded.

**Proof.** Membership in NP follows because a proposed partition is a
polynomial-size certificate whose block masses can be checked directly. Reduce
from 3-PARTITION. Given `3m` positive integers `a_i` with
`B/4 < a_i < B/2` and total mass `mB`, set `tau=B-1` and `K=m`. A valid
3-partition gives `m` blocks of mass `B`, so all are strictly above `tau`.
Conversely, `m` blocks above `B-1` each have integer mass at least `B`; their
total already reaches the available mass `mB`. Thus they consume every item and
each has mass exactly `B`. The 3-PARTITION bounds force each such block to
contain exactly three items. The reduction preserves the strong restriction on
number magnitudes. For alias rank, give a singleton target mass `B-1` and put
all `a_i` roots in one other free-partition component. Theorem 7 makes its
worst rank `1+B_(B-1)({a_i})`, establishing the second statement. QED.

The best-rank formula is linear after component sums and maxima are known; the
hardness concerns the worst-rank packing term. The seven-root cap is therefore
a declared exact-tractability boundary rather than an implication that the
unbounded problem has a polynomial exact algorithm.

**Independent finite check.** The oracle imports none of the component optimizer
or scoring package. It enumerates canonical restricted-growth label strings for
the whole root set, discards blocks crossing a declared component, computes all
block sums directly, and compares both extrema and attaining partitions. The
frozen domains contain consecutively named roots, every component partition,
and every target. Masses range over `{1,2,3}` through six roots and `{1,2}` at
the seven-root implementation cap. There are

`sum(Bell(n)*3**n, n=1..6) + Bell(7)*2**7 = 274250`

mass/component problems and

`sum(n*Bell(n)*3**n, n=1..6) + 7*Bell(7)*2**7 = 1742198`

target cases. The target-case strata are 3, 36, 405, 4,860, 63,180, 887,922,
and 785,792. The producer writes every target answer for one problem row and
uses incremental insertion for component partitions. The consumer imports none
of the optimizer, enumerates restricted-growth strings, checks both bounds and
attaining partitions, and rejects duplicate or incomplete root-count members.
Seven deterministic compressed members permit bounded generation and checking
without weakening coverage. Each independent-check receipt binds the member
bytes and checker source by SHA-256. The finalizer checks those bindings and
refuses a same-row-count member change or a stale checker receipt. These are
integrity bindings, not authenticated scientific attestations. All 1,742,198 target cases agree, with zero invalid
witnesses. Zero, tie, magnitude, hardness, and cap boundaries also have directed
tests. The 56-root example checks its two witness ranks independently; it is not
an exhaustive oracle check for 56 roots.

## 9. Source-to-event obstruction and exact controls

**Proposition 8 (nonnegative cycle obstruction).** Consider a directed graph of
source states and fixed nonnegative transition weights. A path's score is the
sum of its transition weights, and the empty path has score zero. Suppose an
admitted rewrite erases each admitted cycle at its initial state without
changing the score. Every transition on any such cycle has zero weight. If
every transition admits a return path whose cycle may be erased, all weights
are zero.

**Proof.** A cycle and the empty path must have equal score, so the sum of the
cycle's nonnegative weights is zero. Each summand is therefore zero. Apply this
to a return cycle containing any given transition for the second assertion.
QED.

This is a statement about fixed nonnegative additive activity weights, not a
prohibition on signed deltas, endpoint functionals, or restricted rewrite
algebras. The bundled salience is contextual rather than a fixed edge weight;
its counterexamples are established directly, not by silently imposing the
proposition's hypothesis on that extractor.

All eight source fixtures are included in `external_inputs/source_cases.json`.
A source fixture has at most three states and 512 UTF-8 bytes per state. No
fixture program is executed. The adapter generates a unified textual patch and
calls the unchanged token extractor for every transition. The source identity
and syntax checks precede evaluation of the normalized certificate.

S01 has two independent one-token edits in one file. Its two-event mass is
`5.169925001442`, while the separately extracted direct squash has one event of
mass `4.000000000000`, despite identical initial and final bytes. S02 edits and
then restores a file, retaining positive mass against an empty comparison path
of mass zero. Both comparisons reject as event certificates; retaining the
original events during a normalized squash still certifies. These are minimal
in transition count for the selected two-step/direct-step and nonempty-cycle
patterns, not globally smallest histories over every possible extractor.

S03 and S04 preserve the syntax tree under whitespace and comment changes. S05
changes a returned integer and is detected as positive token mass. S06 reverses
the operands of subtraction and differs at arguments one and zero, despite an
unchanged token bag. S07 changes a returned string after a quoted double slash;
comment stripping wrongly removes the distinguishing suffix. S08 moves a return
into a conditional body; on the false branch its return changes from zero to
Python's implicit None. These last three have distinct syntax and a direct
behavioral distinction but zero extracted mass. The event certificate accepts
their zero-mass comparison because it is not a semantic checker. The result
limits the extractor rather than invalidating the frozen-event proof.


## 10. Endpoint-anchored extraction

Let `X` be a set of retained source states and let `E:X x X -> L` be a
deterministic extractor from an ordered endpoint pair to a canonical normalized
event ledger. An endpoint-anchored history representation carries its retained
initial state `x`, final state `z`, complete origin/entity declarations for the
events in `E(x,z)`, and any internal path description only as non-scoring
context. Its scored ledger is defined to be `E(x,z)` exactly once.

**Proposition 9 (path-spelling invariance by endpoint anchoring).** If two
history representations retain byte-identical endpoints `(x,z)`, invoke the
same deterministic extractor `E`, and carry compatible complete origin,
entity, and active may-link declarations for `E(x,z)`, then their normalized
event surfaces are identical and the identity map is a valid rewrite
certificate. Any certified additive actor statistic is therefore equal.

**Proof.** Both representations define their scored ledger as the same
mathematical value `E(x,z)`. The identity map is total and one-to-one and
preserves every event field and declaration. Theorem 1 then gives equality of
the certified actor statistics. QED.

The proposition is intentionally construction-level. It does not say that two
different endpoint pairs are behaviorally equivalent, that `E` captures every
semantic change, that a patch fragment is a complete program, or that a claimed
origin is authentic. If a positive event in `E(x,z)` lacks a total origin map,
Theorem 2 still requires attribution abstention. A path-additive score
`sum_i E(x_i,x_{i+1})` is a different functional and receives no conclusion
from Proposition 9; Proposition 8 and the exact controls show why.

The public patch boundary corpus supplies twelve exact endpoint pairs from
twelve MIT-licensed repositories. All twelve endpoint certificates validate.
The single comment-only control has zero endpoint and cycle mass. The eleven
positive endpoint cases all have positive edit/reverse cycle mass. Relative to
one-shot endpoint mass, three hunk decompositions, three contiguous-change-block
decompositions, and eight delete-then-add paths disagree. The cases span five
language strata, but their selection is convenience-based and supports no
population frequency or semantic-accuracy estimate. No upstream code is
executed.

## Algorithmic relation

For integer masses, a block contributes to the maximum-above-threshold objective exactly when it reaches capacity `threshold + 1`. This is the bin-covering objective, not a new generic optimization problem. An item reaching capacity by itself can be isolated in a covered block without decreasing the optimum; the remaining smaller items give the standard small-item formulation. Theorem 7a supplies the exact complexity boundary needed here by reducing 3-PARTITION to the target-rank decision problem. The global alias result contributes the extremal target-block argument, component decomposition, and attaining partition witnesses for the stated identity model. Sources: M. R. Garey and D. S. Johnson, *Computers and Intractability: A Guide to the Theory of NP-Completeness*, W. H. Freeman, 1979, 3-PARTITION; J. Csirik, J. B. G. Frenk, M. Labbé, and S. Zhang, *Two simple algorithms for bin covering*, Acta Cybernetica 14(1), 13–25 (1999), introduction; https://cyber.bibl.u-szeged.hu/index.php/actcybern/article/view/3507.

## Numeric executable fragment

The event reader canonicalizes inputs by half-even rounding to twelve fractional places with a sixty-digit decimal coefficient limit. An event outside that representable canonical range is refused rather than treated as a theorem-covered executable input. The additive proofs apply to the supplied canonical values; aggregate sums use unbounded integers and are not rounded back through event ingestion. The direct all-component alias API consumes exact nonnegative integer masses and does not call the event canonicalizer. Fixed-width decimal replay and numeric report projections must not be confused with the integer units used for decisions.
