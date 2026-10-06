# Reviewer-directed proof clarifications (F1--F11)

These clarifications preserve the paper's frozen-event, free-partition alias,
and finite-experiment scope. They do not introduce a source-semantic
invariance claim.

## Endpoint-local declaration lemma (F1)

Let an endpoint state be a pair `(E,D)` of its event surface and declarations.
Its actor partition is computed from `D` only. A declaration added to the
rewritten endpoint is not an element of the original endpoint's `D`, so it
cannot change the original endpoint partition. A cross-endpoint decision is
therefore defined only after both endpoint states are computed separately. If
the endpoint statuses differ, the comparison abstains. The directed A--X,
Y--B may-link plus rewritten-only X--Y must-link case is executable evidence of
this rule; it is not a proof that declarations are true identities.

The production checker applies this rule to may-link connectivity as well as
must-link classes. In the A/X/Z regression, only A and Z carry mass. The left
endpoint has must(A,X) and may(X,Z), so its active partition is `(A,Z)`; the
right has only may(X,Z), so its active partition is `(A),(Z)`. Their status
differs and both comparison directions reject. All declaration-only aliases
participate in local class compatibility. Equivalent inactive intermediary
paths remain admissible when their locally computed active partitions agree.

## Exact-unit rank comparison lemma (F2)

Rank predicates compare integer unit sums directly. Hence adjacent integers
`10^20` and `10^20+1` remain ordered, including at budget zero. The bounded
rank interval encloses all competition ranks over legal integer transfers.
Its endpoints combine separately optimized score bounds and need not be
jointly attainable under a shared change budget. For example, scores
`(10,1,1)` from event units `(5,5,1,1)` and a one-relabeling budget give the
target conservative rank interval `[1,3]`, although only ranks 1 and 2 are
attainable. Finite enumeration checks sound enclosure, not attainment of every
rank endpoint. Exact integer comparison follows from the integer
representation, not from the finite experiment.

## Vector-support premise (F3)

Let `Phi(H)=sum_{e in H} phi(e)` be a vector sufficient statistic. A matched
mapping preserves `Phi` only if every nonzero-support event is either matched
with equal `phi` or otherwise accounted for by an explicitly preserved support
extension. An unmatched event may be ignored only when `phi(e)=0`. Scalar
weight zero is insufficient: a zero-weight event can still have nonzero
`phi(e)` and change `Phi`. Therefore the preservation proof assumes either
(1) every unmatched event has the zero vector, or (2) the mapping is extended
to include all unmatched nonzero-support events. Under either condition,
matched terms cancel pairwise and unmatched terms contribute zero, proving
`Phi(H_left)=Phi(H_right)`.

The current positive-surface implementation takes the checked-premise route:
complete optional feature maps must assign the zero vector to every zero-scalar
event and preserve each mapped positive vector. It does not implement a
nonzero-support extension or claim that its scalar ledger replayer checks
vectors. The more general support-extension statement above is a mathematical
condition, not an available production certificate mode.

## Tie-scope proposition (F4)

The invariant outputs are class scores, competition ranks, and unique-winner
status under endpoint-common class keys. A display-first representative chosen
from alias spelling is not an invariant output. In particular, a B/C score tie
combined with a rewritten A--C must-link can change a spelling-based display
order while preserving the stated class-level outputs. No theorem claims
otherwise.

## Minimal witness trichotomy (F5)

A witness search returns exactly one of `FOUND_EMPTY`, `FOUND_NONEMPTY`, or
`NO_SOLUTION`. The empty subset is evaluated before singleton subsets. If a
predicate depends on retained commit containers rather than selected events,
it may hold for the empty event set. The directed 1/2 to 2/2 commit-count case
therefore has a true empty witness. `NO_SOLUTION` uses a distinct null payload
and cannot be confused with the empty tuple.

The production API encodes this trichotomy directly as `()`, a nonempty tuple,
or `None`, respectively. Its existing directed-review model uses the named
statuses. Both evaluate the empty subset first; neither treats tuple truthiness
as a test for the existence of a witness.

## Winner radii (F10)

Loss of unique leadership occurs when a competitor reaches the leader's score;
strict overtaking requires a competitor to exceed it. Under unit transfers from
leader to competitor, starting from 3/1/1, one transfer yields 2/2/1 and loses
unique leadership, while two transfers can yield 1/3/1 and produce a strict
overtake. The radii are therefore one and two, respectively.

## Complexity decomposition (F11)

For `n` events and `a` actor classes, score aggregation is `O(n)` time with
`O(a)` score storage. Sorting is `O(a log a)`. Materializing all actor pairs is
`O(a^2)` time and space; the pairwise report is optional or can be streamed.
Exact uncertain-component search is exponential in roots per component (a
Bell-number partition space) and is subject to the stated finite cap. These are
separate costs and do not constitute a large-scale performance evaluation.
