# Dynamic binding optimization experiment

This branch implements approaches **1, 2, 3, 5, and 12** from the optimization
inventory. It preserves the dynamic reader/builder API and wire format. It does
not claim that all possible improvements are exhausted: two independent review
passes found no remaining high-confidence experiment within this implementation
family after the changes below. Root-level interleaved measurements are the
source of definitive baseline-versus-candidate results.

## Implemented changes

| Approach | Implementation | Attribution |
|---|---|---|
| 1: existing Cython hot paths | Suppress the intermediate AttributeError created on every successful dynamic attribute access; preserve descriptor/method lookup and original subclass slots. Add native list iterators, skip positive-index modulo, use exact internal `__new__` allocation, and guard recursion only for containers. | `CAPNP_FAST_GETATTR=0` isolates attribute dispatch. Commit `9e7b859` contains iterator/allocation changes together. |
| 2: direct conversion | Walk native structs/lists directly into Python dicts/lists and fill native builders directly from mappings/sequences. No intermediate reader/builder/enum wrappers during recursion. Specialize homogeneous primitive list reads and exact built-in numeric writes. | `CAPNP_PRIMITIVE_LISTS=0` and `CAPNP_PRIMITIVE_IMPORT=0` isolate primitive paths. Earlier `native-export.txt`/`native-import-export.txt` are exploratory stage measurements. |
| 3: union/metadata | Copy the field name and discriminant directly for callable which-enums; optionally reuse immutable union results from parser-owned metadata. Cache the last matching schema; an identity-only negative hint avoids repeated misses for static reflection schemas. | Union-only commit `cccc4d7`; `CAPNP_UNION_CACHE=0` disables result reuse. |
| 5: conversion plans | Cache native field handles, decoded names, and input-name lookup maps in the owning global parser. Check exact native schema identity, not just schema ID. Avoid exceptions to activate an inactive union struct during import. | `CAPNP_DICT_PLANS=0` disables plans. This also prevents union-result caching; set `CAPNP_UNION_CACHE=0` in both runs for a pure plan comparison. |
| 12: wrapper allocation/ownership | Remove intermediate conversion wrappers; bypass Python type calls for internal allocations; native iterators pin the original message owner and only advance after successful conversion. | Shared substrate with approaches 1/2, not an additive independent speedup. A 64-entry Cython freelist was tested and rejected. |

Primitive import fast paths handle exact built-in float/int/bool values. Other
values, integer overflow, and schema/type mismatches fall back to the original
dynamic setter, preserving coercions, exception types, and partial-write state.
The first element avoids probing native numeric paths for obvious struct/string
lists. Primitive readers use Cap'n Proto's typed list accessors, including their
layout/stride handling; they do not reinterpret arbitrary wire bytes.

## Exploratory measurements

All local measurements used CPU 2, CPython 3.12.13, the same unchanged 100-line
`benchmarks/bench_openpilot.py`, and the real `/tmp/pr3704_logs/1.rlog.zst` corpus.
These sequential runs experienced unrelated timing variation and are useful for
mechanism checks, **not definitive small speedup claims**. Builds used CPUs 3/4;
CPU 0 was reserved for the root's interleaved comparison.

| Case | Initial local baseline, µs/item | Final local candidate, µs/item |
|---|---:|---:|
| live read | 4.13 | 2.24 |
| field write + encode | 26.61 | 22.66 |
| kwargs write + encode | 29.96 | 9.01 |
| payload assignment | 1.28 | 1.30 |
| CAN cached read, per batch | 24.40 | 23.37 |
| CAN cached write, per batch | 21.58 | 20.90 |
| LogReader parse + scan | 3.77 | 1.92 |
| dictionary export | 70.43 | 10.67 |
| copy + encode | 0.73 | 0.74 |
| reader pickle | 3.15 | 2.57 |
| LogReader pickle | 3.78 | 3.29 |
| schema reflection, per traversal | 318.14 | 136.58 |

The last measured runtime change gates primitive import by the first element's
type; `final.txt` precedes that small gate. The frozen binary's exact hash and
commit are in `metadata.json`. Root measurements use that frozen final binary.

Focused same-binary primitive-import ablation (`details-primitive-import-off.json`
versus `details-final.json`): modelV2 kwargs **45.44 -> 24.39 µs**, longitudinalPlan
**5.79 -> 5.21 µs**. Unrelated export results remain similar, as expected. This is
native message construction, excluding serialization. Other per-type results
and attribute/list/union microcases are in the detail JSON files.

Freelist experiment (`details-cache-off.json` versus `details-freelist.json`):
nested attribute access **386.7 -> 384.8 ns**, plain attribute **156.3 -> 159.0 ns**.
No persuasive gain, so no freelists remain. Union-result reuse reduced the focused
which case **155.3 -> 126.7 ns**; the initial reflection regression motivated the
negative-cache hint. These focused cases include lambda-call overhead.

`first_export_us` means first export of that selected message type after corpus
preparation, **not** a storage-cold/process-cold/schema-cold measurement. Corpus
preparation already invokes `.which()`. Custom `SchemaParser` instances use
operation-local plans, deliberately foregoing persistent cross-call caching.

## Validation and review

- Clean forced extension rebuild; setup dependencies now include local headers,
  preventing stale incremental binaries after helper-only changes.
- **380 tests passed** across this repository and openpilot cereal messaging.
- Exact baseline fingerprints match on the original, held-out Ascent, and held-out
  Kona logs: wire messages, normal dictionaries, verbose dictionaries, and kwargs
  reconstruction. See `corpus-final.json`.
- New tests cover union snapshots after mutation/deletion, custom parsers reusing
  IDs, descriptor/subclass behavior, refcounts, iterator ownership and malformed
  element retry, recursion, primitive boundaries/coercions/errors, malformed
  pointers, and schema evolution from primitive lists to inline-composite lists.
- Correctness reviewer independently checked 3,300 seeded mixed primitive input
  cases across eleven list types against generic per-item setters, including
  exact serialized partial-write state and exception types/messages.
- GC-disabled repeated construction/export leaves zero additional live builders.
  This is a lifetime check, not a total native-allocation or RSS measurement.
  Persistent metadata is retained per encountered schema by its owning parser;
  there is no cache entry per message.
- A correctness skeptic and a performance skeptic reviewed twice, requested
  concrete improvements, and reviewed their completion. The performance reviewer
  found no remaining high-confidence prototype/test blocker in this bounded
  family after primitive import; final acceptance remains with the root review.

The first review found that CPython's native recursion guard permits a much deeper
C stack than is safe on this build. Native conversion now has an explicit
512-container guard in addition to the interpreter guard. Cyclic input and
recursive verbose defaults raise `RecursionError`, rather than overflowing the
native stack.

One intentional error-handling tightening: dictionary export propagates malformed
active union payload errors. The previous broad union exception handler silently
omitted that field. Valid-message behavior and dictionary ordering are unchanged.

The optimized attribute slot uses private CPython
`_PyObject_GenericGetAttrWithDict`. It is gated to CPython 3.12–3.14 without limited
API/free-threaded/PyPy builds, and otherwise retains Cython's original slot. Its
signature was checked in installed 3.12/3.13/3.14 headers; runtime validation here
covers **Linux CPython 3.12 only**, not all enabled versions/platforms.

## Reproduction

```sh
PYTHONPATH="$PWD:/home/batman/openpilot" taskset -c 2 \
  /home/batman/openpilot/.venv/bin/python benchmarks/bench_openpilot.py \
  /tmp/pr3704_logs/1.rlog.zst --repeat 5

CAPNP_PRIMITIVE_IMPORT=0 PYTHONPATH="$PWD:/home/batman/openpilot" taskset -c 2 \
  /home/batman/openpilot/.venv/bin/python experiments/dynamic/bench_details.py \
  /tmp/pr3704_logs/1.rlog.zst
```

All `CAPNP_*` switches default on and are experiment ablations, not required
runtime tuning. No GC disabling is used in timed throughput cases. No change to
wire format, schema generation, IPC, compression, or openpilot callers is needed.
