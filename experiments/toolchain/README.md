# Compiler optimization experiment

`PYCAPNP_OPT_FLAGS` is an optional build switch applied to the vendored library,
the Cython extension, and the extension link. The default build is unchanged.
Use a clean build directory when changing it: CMake caches compiler flags.

The experiment compares GCC O3, O2, host-native tuning, LTO, PGO, PGO+LTO,
and PGO+LTO+native. It deliberately excludes fast-math, unsafe floating-point
options, and disabled exception handling. Native binaries are for this CPU,
not portable wheels. GCC-specific PGO flags are not a cross-platform default.

Run from the repository root (absolute paths recommended):

```sh
python experiments/toolchain/run.py \
  --build-python /path/to/build/venv/bin/python \
  --bench-python /path/to/openpilot/.venv/bin/python \
  --openpilot /path/to/openpilot \
  --train /path/to/0.rlog.zst --evaluate /path/to/1.rlog.zst \
  --cpu 17 --build-cpus 18,19
```

The script uses the unchanged 100-line benchmark. It retains per-case medians
and ranges, compiler/build logs, tests, binary artifacts, log hashes, and build
times under `results/`. PGO training uses a separate log; profiles encompass
both the extension and the vendored static library. Instrumented and optimized
builds reuse the same object paths so GCC can find the profiles. Every build
starts clean, with only profile data retained between generation and use.

Measurements on this x86 host cannot establish gains on openpilot's ARM device.
Training/evaluation segments from one route also cannot establish cross-car
PGO generalization; a separate-car held-out check is required for a candidate.
Concurrent work elsewhere on the host can affect timings despite CPU affinity.
Do not treat one global average of these different workloads as onroad speedup.

GCC flag semantics: https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html

## Correctness exclusions

With GCC 13.3 and Cython 3.3.0, plain LTO produced an incorrect binary:
`enum(1) != 0` returned false, and both `<` and `>` could return true for the
same inputs. The generated C++ comparison helpers differ, but `nm` showed
Eq/Ne at one address, Lt/Gt at another shared address, and Le/Ge likewise.
Disabling strict aliasing did not fix it. Disabling IPA identical-code folding
with `-fno-ipa-icf` did. Every accepted GCC LTO variant includes that workaround;
rejected build/test logs remain available. `test/test_toolchain.py` checks all
six operators across enum, integer, and string operands.

PGO rejects mismatched profiles and missing profiles except the precise
`kj/source-location.c++` archive member: it supplies debug diagnostics and is
not linked into the Release extension, so its instrumentation cannot run.
Required extension and vendor hot-path profile files are checked explicitly.

Training exercises the whole benchmark suite with two repetitions per case,
including process startup and corpus preparation. That balances benchmark
cases by elapsed time; it is not a measured onroad CPU-frequency weighting.
PGO results therefore describe this broad benchmark training policy, not an
optimal profile for every individual daemon.

Clang O3, ThinLTO, and instrumentation PGO+ThinLTO are also evaluated when
requested through `--variants clang clang-thinlto clang-pgo-thinlto`.
These require `clang`, `clang++`, `ld.lld`, and `llvm-profdata`. Profile-use
warnings reject stale/incompatible function profiles. No GCC-specific ICF
workaround is passed to Clang.

An initial O3 baseline was also excluded from comparisons: setting generic
`CFLAGS` had replaced Python's usual extension flags, including `-DNDEBUG`.
The accepted baseline is rebuilt through the same `PYCAPNP_OPT_FLAGS` switch
as every candidate, preserving Python's default flags. Its predecessor is
retained under `baseline-flags-rejected` solely as audit evidence.
