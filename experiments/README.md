# Speed experiments

All experiments start at `b8ec065` on `faster-python`. The original 100-line
benchmark stays unchanged. Optional APIs have separate equal-output benchmarks;
their results are not presented as drop-in binding speedups.

| Approaches | Branch | Directory | Status |
| --- | --- | --- | --- |
| 1, 2, 3, 5, 12: dynamic Cython, conversion, unions, plans, wrappers | speed/dynamic | dynamic | Implementation and measurement |
| 4, 7, 9: CAN batches, numeric lists, compiled consumers | speed/bulk | bulk | Implementation and measurement |
| 6, 10: generated Cython and CPython bindings | speed/generated | generated | Implementation and measurement |
| 8, 11, 15: projection, forwarding/pickle, parallel scanning | speed/logreader | logreader | Implementation and measurement |
| 13, 16: arenas, precompiled schemas/reflection | speed/allocation | allocation | Implementation and measurement |
| 14: compiler optimization | speed/toolchain | toolchain | Implementation and measurement |
| 17, 18, 19: direct codec, JIT, alternate binding framework | speed/alternative | alternative | Implementation and measurement |

## Acceptance and measurement

Each approach needs executable source, reproducible commands, correctness and
lifetime checks where relevant, measured results, and documented compatibility
and coverage. Independent correctness and performance reviewers challenge both
the implementation and whether another concrete improvement remains. The main
agent repeats that review. A clean review means no identified unresolved issue,
not proof that no faster implementation can ever exist.

Exploratory runs use separate CPU affinities while teams build; these are noisy
and cannot establish small gains. Final comparisons alternate baseline and
candidate on CPU 0 with competing builds paused. CPU 12 shares its physical
core and must also be idle. Record source revisions, extension hashes, input and
corpus hashes, Python version, affinity, and all raw output. Keep GC enabled.
Report results per workload rather than averaging incompatible units.

Use `/tmp/pr3704_logs/1.rlog.zst` for the original benchmark. Other segments are
useful for training, but are not independent vehicles. Held-out vehicle logs
are available under `/tmp/opendbc_logs/`; identify their actual contents before
claiming cross-vehicle validation. Startup, generator compilation, retained
memory, and caller changes are separate costs and must not disappear from the
conclusions.

Experiments remain isolated until reviewed. A regression or unsuccessful
architecture is retained as evidence rather than silently dropped.
