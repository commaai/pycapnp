# Independent review record

## Correctness reviewer (allocation, ownership, error-path prior)

Initial review reproduced a source-list mutation crash: `__float__` cleared a list held by
`PySequence_Fast`. Fixed with an immutable tuple snapshot. Also required non-None typed
extension arguments, since Cython otherwise accepts None and native member access is invalid.

Rereview found no remaining concrete blocker in core paths. Independently checked Float64,
empty views, parent deletion/GC, same-buffer writes, and None rejection. Confirmed cached
field access validates containing schemas. Requested edge-case tests were added (27 pass).

Borrowed views intentionally differ from independent copies: they pin storage and expose
mutations through separate builder aliases. Tests and documentation preserve this distinction.

## Performance reviewer (attribution and unexploited-work prior)

Initial review rejected a maximization claim: generic per-field CAN conversion remained,
buffer reads copied, scalar/NumPy representations differed, and Python actuator caching
confounded the compiled comparison. Also requested same-parser controls and paired samples.

Implemented native CAN specialization with retained generic ablation; borrowed contiguous
views; guarded native-buffer memmove; scalar NumPy comparison; matching actuator caching;
seven alternated sample pairs; batch/list-length distributions and exact projection checks.
Rereview approved the bounded implemented paths, with no further concrete performance blocker.

Route1 float-buffer timings initially had roughly 2x within-side spread. A dedicated paired
repeat (`buffer-repeat.json`) measured 22.38x, with baseline 2.467–2.552 us/list and native
0.111–0.112 us/list. Held-out ascent measured 22.44x with similarly narrow spread.

These approvals concern implemented paths and evidence, not a proof that every conceivable
optimization has been exhausted. Main-agent review and quiet final measurements remain separate.

Additional main-worker self-review found overlapping buffers with different float widths could
clobber unread source values. The conversion fallback now snapshots source bytes first; the
same-width path remains memmove. Independent correctness rereview approved the fix, and its
new regression passes. The dedicated cross-width benchmark measures 17.66x with tight spreads.
