# Independent review record

Correctness reviewer (separate agent, lifetime-first prior): found and prompted
fixes for imported dependency pickling, fractional/off-by-one size validation,
GC clearing of the pool owner, combined ready/buffer capacity, and reset of an
uninitialized arena. Final source signoff: no actionable findings. Independently
ran75 tests and5,000 additional mixed-schema reset cases covering XOR defaults,
unions, bool/struct lists, text, overflow, cross-schema reuse and empty-after-use.
Final author verification after forced build:127 passed,5 skipped; compiled
cross-file assignment and shared archive loader also passed.

Performance reviewer (different agent, skeptical of maximality and measurements):
rejected initial sequential timing drift, mislabeled kwargs case, unstable schema
wrapper cache keys, unvalidated trained/input-size variants and buffer-only reset.
Changes: randomized repeated timing rounds; actual public kwargs plus separately
labeled from_dict; stable declaration cache keys; every policy checked on train
and held-out logs; complete single-segment arena reset and GIL-confined native
pool operations. Final conditional signoff: practical allocator/schema approaches
sufficiently explored, no further implementation blocker. Requested final quiet
measurements, input-size naming, and runtime service dispatch; all benchmark code
requests are addressed. Final quiet timing remains for the main-agent phase.

Allocator single-segment reset is a deliberate endpoint: full-workload impact is
small in exploratory measurements. Reusing arbitrary multisegment graphs adds
substantial state-reset complexity while affecting only a subset of events.
