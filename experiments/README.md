# Speed experiments

All experiments start at `b8ec065` on `faster-python`. The original 100-line
benchmark stays unchanged. Optional APIs have separate equal-output benchmarks;
their results are not presented as drop-in binding speedups.

| Approaches | Branch | Directory | Status |
| --- | --- | --- | --- |
| 1, 2, 3, 5, 12: dynamic Cython, conversion, unions, plans, wrappers | speed/dynamic | dynamic | Implemented and independently reviewed |
| 4, 7, 9: CAN batches, numeric lists, compiled consumers | speed/bulk | bulk | Implemented and independently reviewed |
| 6, 10: generated Cython and CPython bindings | speed/generated | generated | Implemented and independently reviewed |
| 8, 11, 15: projection, forwarding/pickle, parallel scanning | speed/logreader | logreader | Implemented and independently reviewed |
| 13, 16: arenas, precompiled schemas/reflection | speed/allocation | allocation | Implemented and independently reviewed |
| 14: compiler optimization | speed/toolchain | toolchain | Implemented and independently reviewed |
| 17, 18, 19: direct codec, JIT, alternate binding framework | speed/alternative | alternative | Implemented and independently reviewed |

## Acceptance and measurement

Each approach needs executable source, reproducible commands, correctness and
lifetime checks where relevant, measured results, and documented compatibility
and coverage. Independent correctness and performance reviewers challenge both
the implementation and whether another concrete improvement remains. The main
agent repeats that review. A clean review means no identified unresolved issue,
not proof that no faster implementation can ever exist.

Exploratory runs use separate CPU affinities while teams build; these are noisy
and cannot establish small gains. Final dynamic/toolchain comparisons alternate
baseline and candidate processes on CPU 0 with competing builds paused. Optional
API suites use paired, rotated or randomized in-process measurements; the
LogReader suite uses affinity 0,1 for both serial and parallel cases. CPU 12 shares
CPU 0’s physical core and must also be idle. Record source revisions, extension hashes, input and
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

Final measured findings, compatibility limits and validation: [RESULTS.md](RESULTS.md).
