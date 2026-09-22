# Openpilot binding performance experiments

All 19 approaches have executable implementations, correctness checks and measurements.
The original `benchmarks/bench_openpilot.py` remains unchanged at 100 lines.
The compatible dynamic implementation is merged into `faster-python`; the other six
branches retain opt-in APIs and build experiments. Their speedups must not be
multiplied together or presented as a whole-openpilot CPU reduction.

The controlled reruns and independent reviews are complete. The compatible dynamic
changes are merged into `faster-python`; optional API/build experiments remain on
the seven `speed/*` branches linked below.

## Workloads and measurement

The starting point is `b8ec065`, after minimization and vendoring. Measurements use
CPython 3.12.13 on an AMD Ryzen Threadripper PRO 5945WX. Competing experiment
builds and benchmarks were paused; this is still a shared host, not an exclusive
machine. Serial suites use CPU 0, except the LogReader suite: both its serial and
two-stream parallel cases share affinity to physical cores 0 and 1. GC stays enabled.
Startup measurements use fresh processes;
hyperfine repeats schema and runtime-compilation startup. File caches are warm.

The original benchmark samples 1,000 events evenly and adds the first event of
each type. Primary segment `/tmp/pr3704_logs/1.rlog.zst` yields 1,049 events,
49 types and 693,448 serialized bytes, SHA256
`836f53c3742a79bbce5712f67e19f3cd4fe92e8155b68f5d53b4f42c22fdafde`.
The held-out Ascent route yields 1,060 events and corpus SHA256
`e74408571fc8decef9b421d5cdc220071109bdc950b192ddd6c0b512d8f935d8`.
Compiler profiles and allocation policies train on segment 0, not these evaluation
segments. Openpilot revision is `7f6f13997c3c9b8e27e1581583f61e3fcabc5151`.

Optional APIs use equal-output comparisons and separately documented corpora:
projection scans use complete decompressed logs; the direct codec uses up to
1,000 events per supported type rather than frequency weighting. I/O and
decompression are excluded. CAN units are batches, numeric units are lists,
and startup units are processes. No aggregate mixes these units.

Raw output and per-job commands, commits, available binary hashes and return codes are in
[`results/`](results/). [`run_review.py`](run_review.py) reproduces the sequential
local evaluation; [`compare.py`](compare.py) alternates independent baseline and
candidate processes. Tiny or overlapping differences are not decisive wins.
Optional API suites instead use paired, rotated or randomized in-process cases.
Temporary direct-codec, framework and backend-control binaries were deleted by
their harnesses without retaining binary hashes; source revisions/build commands
and supplemental compiler/archive identity remain available. These are a provenance
limitation, not measured production artifacts.
The generated startup job initially failed because its child process imported an
unbuilt package from its working directory; the corrected job ran from the built
baseline checkout and passed. Successful earlier jobs were retained.

## The 19 approaches

| # | Approach and branch | Final finding |
|---|---|---|
| 1 | Cython field dispatch, `speed/dynamic` | Suppress intermediate missing-attribute exceptions; final native trampoline removes overhead on ordinary methods. Final controlled results below. |
| 2 | Native recursive dictionary conversion, `speed/dynamic` | Large construction/export gains without intermediate Python wrappers; preserves conversion fallback behavior. |
| 3 | Union lookup/cache, `speed/dynamic` | Parser-owned union names/discriminants avoid repeated reflection; ablation recorded separately. |
| 4 | Native CAN batches, `speed/bulk` | Same-parser read 1.70–1.76×; write 1.99–2.02×. Requires batch API changes. |
| 5 | Schema/field plans, `speed/dynamic` | Exact-schema cached native handles and conversion plans; separate knobs isolate plan and union effects. |
| 6 | Schema-generated Cython, `speed/generated` | Typed getters and native constructors cover the current Event graph; adapted API, same native core as #10. |
| 7 | Numeric lists and buffers, `speed/bulk` | List reads 3.10–3.18×, list writes 6.70–6.76×; native buffer writes 21.81–23.94× versus scalar Python assignment. |
| 8 | Native projection/filtering, `speed/logreader` | 5.79–13.12× for complete in-memory log queries with matching boxed results. |
| 9 | Compiled consumers, `speed/bulk` | 1.70–1.72× with matched attribute caching; schema-generated fused projection 16.90–17.31× on its narrower output contract. |
| 10 | Schema-generated CPython extension, `speed/generated` | Roughly 9–10× reads/dict construction; about 1.9× field construction versus original dynamic API. Python frontend alone explains only a small part. |
| 11 | Shared wire buffers/forwarding/pickle, `speed/logreader` | One RawLog containing sampled events has a 1.77× faster pickle roundtrip than the reader list; prepared forwarding about 6.2×. Out-of-band buffers add no convincing local roundtrip gain. |
| 12 | Wrapper allocation and iteration, `speed/dynamic` | Native list iteration/internal allocation included; freelist trial did not show a worthwhile gain and was removed. Generated inline handles are separately ablated. |
| 13 | Presizing/pools/arena reset, `speed/allocation` | About 1–2% on full construction workloads, overlapping ranges; roughly 30% on empty-message microcase only. Trained sizing is near-null on held-out data. |
| 14 | GCC/Clang/LTO/PGO, `speed/toolchain` | Twelve accepted builds screened; four strongest candidates independently rerun on both corpora. Final table below. |
| 15 | GIL-free parallel scanning, `speed/logreader` | Two workers give 7.52–26.30× versus serial Python across two independent streams, including executor creation. Staging uses more memory. |
| 16 | Precompiled schemas/reflection, `speed/allocation` | Setup 14.30→5.63 ms eager or 2.20 ms lazy through first Event; reflection 307.77→7.23 µs with fresh mutable output. No demonstrated serialization win. |
| 17 | Direct wire codec, `speed/alternative` | Specialized scalar/list readers and writers; shared-conversion libcapnp controls isolate its smaller backend benefit. Not a general replacement codec. |
| 18 | Runtime schema specialization/JIT, `speed/alternative` | On-demand native compilation/cache implemented; warm machine code is identical to AOT, with compilation/startup costs. No adaptive-JIT claim. |
| 19 | Other Python binding frameworks, `speed/alternative` | Same kernel measured through CPython, pybind11, CFFI API/ABI and ctypes; native batching matters more than a general framework ranking. |

## Compatible dynamic implementation

The final native trampoline removes the earlier CAN regression. The table uses
medians of fresh-process medians: three alternating rounds on the primary route
and two on the held-out vehicle, five samples per process. Speedup above one
favors the candidate. Raw samples and process variation are retained.

| Workload | Primary µs, baseline → final | Speedup | Held-out µs, baseline → final | Speedup |
|---|---:|---:|---:|---:|
| live read | 3.70 → 2.18 | 1.697× | 3.70 → 2.10 | 1.760× |
| field write+encode | 24.35 → 22.41 | 1.087× | 19.02 → 17.45 | 1.090× |
| kwargs write+encode | 28.92 → 8.87 | 3.260× | 25.78 → 7.33 | 3.517× |
| payload assignment | 1.22 → 1.25 | 0.976× | 1.26 → 1.25 | 1.008× |
| CAN cached read | 23.19 → 21.79 | 1.064× | 11.31 → 10.90 | 1.038× |
| CAN cached write | 20.18 → 19.15 | 1.054× | 10.80 → 10.36 | 1.043× |
| LogReader parse+scan | 3.57 → 1.84 | 1.940× | 3.38 → 1.83 | 1.849× |
| dict export | 64.84 → 10.43 | 6.217× | 48.95 → 8.52 | 5.746× |
| copy+encode | 0.70 → 0.70 | 1.000× | 0.70 → 0.69 | 1.007× |
| reader pickle | 2.89 → 2.53 | 1.142× | 2.84 → 2.54 | 1.116× |
| LogReader pickle | 3.34 → 3.18 | 1.050× | 3.28 → 3.26 | 1.006× |
| schema reflection | 299.78 → 131.33 | 2.283× | 298.09 → 131.57 | 2.266× |

The payload-assignment case is approximately flat: primary elapsed time is 2.5%
higher, held-out is 0.8% lower. Copy/encode is flat. The implementation is not
claimed to accelerate every operation. A direct pre/post-trampoline comparison
improves CAN read/write about 6.5%; kwargs construction shows process-level timing
bands, so its small pre/post difference is not treated as an isolated mechanism.
The earlier candidate and all ablations remain available rather than being discarded.

Compatibility targets valid openpilot messages. Native recursive conversion now
has an explicit 512-container limit, and malformed active union payload errors
propagate instead of being silently omitted. Unsupported interpreter configurations
retain the original attribute slot; runtime validation here covers CPython 3.12.

## Generated bindings and batching

Generation covers 263 branded structs, 2,209 fields and all 152 current Event
union arms. Both Cython and direct CPython frontends use the same library-backed
typed accessor core. Primary native results are 3.97→0.41 µs read,
30.30→3.21 µs dict construction and 24.83→13.01 µs field construction. The repeated
baseline read is 3.82 µs, so the read comparison is about 9.3–9.7× rather than an
exact universal ratio. Fresh-process first read/write is 50.65→21.92 ms.

Against the final optimized dynamic implementation in the same run, generated native
reads are 2.14→0.39 µs (5.49×), dict construction 8.87→2.83 µs (3.13×), and field
construction 22.75→12.14 µs (1.87×). This is the relevant incremental comparison
after adopting the compatible changes; the approximately 9× figures use the original
baseline. See `results/generated-vs-final-dynamic.txt`.

Sparse model access benefits from lazy list views (0.25 versus 0.37 µs), while
complete materialization favors eager lists (0.57 versus 0.73 µs). Both are retained.
Inline handles, borrowed exact bytes and cached union names each help in same-binary
ablations. Borrowed inputs retain ownership; bytes subclasses are copied.

This API changes enum representation, list behavior and construction. Reflection,
pickle, context managers, arbitrary runtime schemas and existing reader/builder
assignment conversion are not provided. Compile time, generated code size and
single-interpreter/GIL assumptions are recorded in the branch report. Library
accessors validate touched paths; this is not complete up-front message validation.

Bulk copied buffers and borrowed views are distinct semantics. A read-only borrowed
view pins its owner but a separate mutable builder alias can still change its data.
Borrowing improves buffer-to-NumPy access only 1.18–1.21× over the already fast copy.
The approximately 17× fused consumer result returns metadata and selected hot
payload fields, with `None` for other payloads; it is narrower than the original
benchmark. Both sides return the same boxed output.

## LogReader and allocation tradeoffs

Native scalar/wide/model/CAN/rare projections take respectively
27.53/33.53/30.43/182.79/20.56 ms across the two complete logs, versus
333.25/356.63/333.72/1058.67/269.88 ms for idiomatic Python LogReader queries.
Two workers take 15.17/24.27/17.92/140.73/10.26 ms. The wide threaded ablation
measured 18.84 ms in another run; the cause is unestablished, so comparisons use
the same run rather than selecting the best number.

Lazy setup avoids eager work, but reading every event's timestamp and union name
only reduces time 7.56%; that does not mean all payload fields were read. Sparse
access and raw forwarding benefit most. Cold forwarding avoids decoding/rebuilding
altogether and must not be advertised as a decoding speedup. Raw events can retain
the complete backing log until explicitly detached. Strict malformed-input errors
differ from LogReader's warning/partial-log policy.
Pickle and forwarding cases use every hundredth event from the first log, serialized
into one sampled RawLog; those timings do not cover either complete original log.

Arena reset retains only bounded cached single-segment storage, zeroes initialized
words, resets reader state and falls back to destruction for multi-segment arenas.
Large live messages and native metadata are outside the cached-buffer byte bound.
Full-workload gains are small; the best empty-message result is not a reason to
add pool complexity to the default API.

Schema archives require regeneration when schemas change. Loader retention is
process lifetime. The hyperfine full-process harness measures approximately
46.8 ms source, 37.4 ms eager and 33.7 ms lazy loading, with warm filesystem caches.
Archive creation is about 48 ms. These include interpreter/harness overhead and
should not be confused with the inner setup figures. A lazy steady-state kwargs
run was unstable (30.45–52.95 µs); no steady-state serialization advantage is claimed.

## Compiler and direct codec controls

The matched CarState control measures direct versus typed libcapnp reads at
0.1089 versus 0.1292 µs on the primary route, and 0.1086 versus 0.1282 µs held out.
Direct writes take 0.0632/0.0649 µs versus flat-buffer library writes at
0.1048/0.1063 µs. Thus bypassing the library saves 15–16% read time and 39–40%
write time for this operation; most larger gains over dynamic Python come from
specialization. The allocating library writer takes about 0.150 µs.

Runtime compilation takes 527.2 ms cold, 154.4 ms cached and 150.6 ms prebuilt
in the shared-import fresh-process harness (hyperfine, 15 runs). There is no warm
execution advantage. For the identical CarState kernel, direct CPython individual
calls take about 0.111 µs versus pybind11's 0.194 µs, while native batching takes
0.091–0.092 versus 0.085 µs respectively. CFFI API and ctypes with reused output
buffers take 0.365–0.377 and 0.521–0.523 µs, including Python field extraction.
The result supports native batching, not a universal framework ranking.

Compiler experiments use the original minimal runtime, not the combined final
dynamic implementation. Native CPU flags are host-specific. GCC 13 LTO incorrectly
folded enum comparison implementations; rejected evidence is retained, and every
accepted GCC LTO build uses `-fno-ipa-icf`. The accepted binaries passed the comparison
matrix and openpilot integration tests. This is x86 evidence, not ARM validation.

Controlled speedup ranges across the two corpora (not confidence intervals):

| Compiler candidate | Field construction | Kwargs construction | CAN write | Dict export |
|---|---:|---:|---:|---:|
| GCC PGO/LTO/hidden | 1.015–1.035× | 1.015–1.045× | 1.117–1.126× | 1.003–1.012× |
| Clang | 1.133–1.149× | 1.123–1.124× | 1.134–1.138× | 1.007–1.011× |
| Clang PGO/ThinLTO | 1.345–1.352× | 1.286–1.287× | 1.272–1.296× | 0.876–0.921× |
| Clang PGO/ThinLTO/native/hidden | 1.345–1.354× | 1.308–1.335× | 1.289–1.331× | 0.925–0.938× |

Values below one are regressions. Default compiler flags stay unchanged. The
portable Clang PGO held-out live-read run had an anomalous baseline sample; the
GCC primary pickle run had an anomalous candidate sample. Neither is used as a
headline win or regression. All eight ABBA comparisons have matching corpus hashes,
event distributions, workload counts and verified binary identities; details and
raw evidence are on `speed/toolchain` in `experiments/toolchain/final-review.md`.

The direct codec supports selected fields of five event types and constructors
for three, with explicit schema/layout and traversal restrictions. Writers receive
projection tuples while the idiomatic Python reference builds kwargs inside timing;
their large headline ratios combine construction, boxing and encoding changes.
The same-conversion typed internal libcapnp control estimates the extra benefit of
bypassing the library for CarState only (1,000 events per route); it does not isolate
the backend effect for all five codec types. Malformed-input acceptance is stricter
in some cases, not identical. Runtime compilation is schema specialization and
caching, not tracing JIT optimization. Framework results apply to this shared
kernel and output contract, not all extension workloads.

## Review and correctness evidence

Each team used independent correctness and performance reviewers and iterated on
their findings. Main-agent review found additional issues, including callback
mutation crashes in generated construction, deep recursive projection planning,
overlapping allocation training/evaluation, and direct-codec schema/cache assumptions.
Those findings drove fixes and permanent regression coverage. Bulk reviews also
found overlapping cross-width buffers; toolchain reviews caught the LTO miscompile.

Generated writers retain shallow reference snapshots before callbacks; this is not
an atomic deep snapshot of arbitrary mutable Python graphs. Direct-codec tests
include 90 adversarial fixtures, full-message writer checks, 10,000 differential
mutations and 100,000 ASan/UBSan mutations (interpreter leak detection disabled).
Dynamic conversion checks include 3,300 seeded differential numeric-list cases,
including exceptions and partial-write state. Corpus comparisons cover the primary,
Ascent and Kona logs. Installed headers establish API availability for CPython
3.13/3.14; actual runtime validation is on 3.12 only.

A clean review means no identified unresolved blocker or obvious
missing optimization within the implemented scope. It is not proof of an absolute
performance ceiling, nor a claim that every combination of approaches was tested.


## Final validation and branches

The main agent independently reran the merged package/openpilot messaging suite:
**382 passed** (one existing multiprocessing/fork deprecation warning). The merged
source matches the reviewed dynamic runtime exactly and uses its tested extension,
SHA256 `8e4c6b43db9f3c6dee2adfa1c7b5377009fd4ec21014c292d8c4a5622045e017`.
The runtime change is `62e4cd7`; merge commit is `cd702ba`.

Independent final optional-API checks: **102 bulk/integration tests**, both generated
modules' **152 Event-arm checks**, **22 reentrant subprocess regressions**, and all
four direct-codec regression scripts passed. Earlier main-agent allocation/logreader
suites passed **132/76 tests** with three-corpus equality. The final dynamic team
also passed **31 fallback-mode tests** and repeated exact three-corpus fingerprints.
All **38 sequential comparison jobs** completed successfully, followed by final
pre/post-trampoline, baseline/held-out, and generated-versus-optimized comparisons.
The original benchmark remains exactly **100 lines**, byte-for-byte unchanged.

The report preserves null/regressive experiments and API limitations. Only the
compatible dynamic implementation is merged; build flags and optional APIs remain
separate. The following committed branches contain their full implementations,
reproduction instructions, tests and team review records.

| Experiment | Final branch commit | Source/report |
|---|---|---|
| dynamic | `b6ed823a` | [speed/dynamic](https://github.com/commaai/pycapnp/tree/speed/dynamic/experiments/dynamic) |
| bulk | `51617a58` | [speed/bulk](https://github.com/commaai/pycapnp/tree/speed/bulk/experiments/bulk) |
| generated | `b40241af` | [speed/generated](https://github.com/commaai/pycapnp/tree/speed/generated/experiments/generated) |
| logreader | `cc04d144` | [speed/logreader](https://github.com/commaai/pycapnp/tree/speed/logreader/experiments/logreader) |
| allocation | `f2ebe9bf` | [speed/allocation](https://github.com/commaai/pycapnp/tree/speed/allocation/experiments/allocation) |
| toolchain | `82fe615b` | [speed/toolchain](https://github.com/commaai/pycapnp/tree/speed/toolchain/experiments/toolchain) |
| alternative | `fb149e91` | [speed/alternative](https://github.com/commaai/pycapnp/tree/speed/alternative/experiments/alternative) |
