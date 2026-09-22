# Independent review record

Two different reviewers were used: one focused on correctness/portability,
the other on measurement validity and whether promising compiler dimensions
were missing. The main experiment owner independently audited the build flags
and rejected the first incorrectly configured baseline.

Correctness reviewer identified GCC LTO folding opposite Cython comparison
helpers to one address, required a six-operator comparison matrix, stronger
profile coverage checks, complete source/binary provenance, and binary
restoration in helper scripts. These changes were implemented. The final
review independently verified hashes, all 12 accepted binaries' **61 passing
integration tests**, the GCC LTO workaround, source hashes, and profile checks.
Correctness signoff was granted for this tested x86 host configuration.

Measurement reviewer required fresh-process paired comparisons, SMT sibling
reservation, per-workload ratios and regressions, and a separate-car held-out
PGO evaluation. The exploratory sequential results are explicitly not a
controlled speedup comparison. Final measurement signoff was granted after the coordinated quiet-host
comparisons and separate-car heldout evaluation; see `final-review.md` for
tradeoffs, noisy cases, independent artifact/corpus checks, and precise limits.

No production optimization default has been changed. `PYCAPNP_OPT_FLAGS` is
optional; the package header dependency fix applies to ordinary builds too.
