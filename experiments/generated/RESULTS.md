# Generated binding results

Exploratory measurements on the Ryzen Threadripper PRO 5945WX host, CPython 3.12.13, pinned CPU8, three approximately 0.2-second samples per workload. Main-agent quiet reruns remain the comparison authority; occasional outliers are retained in the raw files. Baseline is immutable `b8ec065b16290deb62e309b0443e6a8ccec23259`; optimized dynamic is `accb06de2c139f39e0458f3e0779d436c6c30934`. **All final timings include reentrant input snapshots and safe bytes-subclass ownership.**

| Corpus / operation | Original dynamic µs/event | Generated Cython | Generated CPython |
|---|---:|---:|---:|
| Training: Read | 3.88 | 0.44 | 0.41 |
| Training: Dict + encode | 28.98 | 3.16 | 3.14 |
| Training: Attributes + encode | 24.14 | 12.23 | 12.15 |
| Held out: Read | 3.66 | 0.38 | 0.36 |
| Held out: Dict + encode | 25.87 | 2.62 | 2.52 |
| Held out: Attributes + encode | 18.81 | 9.96 | 10.02 |

Training SHA256: `836f53c3742a79bbce5712f67e19f3cd4fe92e8155b68f5d53b4f42c22fdafde` (1,049 events). Held-out Ascent SHA256: `e74408571fc8decef9b421d5cdc220071109bdc950b192ddd6c0b512d8f935d8` (1,060 events). Both modules check all represented fields and read/dict-write/attribute-write parity before timing. Generation covers 263 branded structs / 2,209 fields; synthetic tests cover all 152 Event arms. These are distinct coverage measures.

Against optimized dynamic on the training corpus:

| Operation | Optimized dynamic µs/event | Generated Cython | Generated CPython |
|---|---:|---:|---:|
| Read | 2.16 | 0.42 | 0.40 |
| Dict + encode | 8.91 | 2.96 | 2.94 |
| Attributes + encode | 23.47 | 12.03 | 12.21 |

Native specialization retains approximately **5.4× read, 3.0× dict construction, and 1.9× attribute construction** improvement. Cython/native share a typed conversion core, so their small difference is frontend overhead, not evidence of an inherent language advantage. The last native attribute comparison has a noisy maximum sample; main quiet confirmation is important.

## Lists and CAN

Native sparse `position.x[0]` is 0.38 µs through eager properties versus 0.26 µs with the lazy view. Full extraction is 0.60 µs eager versus 0.75 µs lazy. Original dynamic sparse/full is 2.44/3.55 µs. These include parse/root/payload work. Retain both APIs: sparse and complete traversal prefer different representations.

Ordinary attribute-based CAN address/data/source extraction is 66.21 µs/batch dynamic, 7.92 Cython, 7.85 native. This is **per event/batch, not per frame**, and is separate from openpilot's cached-field CAN helper/bulk experiment. Envelope-only access is separately labeled and cannot support frame-conversion claims.

## Ablation, startup and build

`result-ablation.txt` independently disables inline handles, borrowed bytes and cached union names using fresh processes and sanitized flags. Enabled confirmation brackets the alternatives. Benefits are not additive measurements. Heap mode retains the same wrapper storage footprint, isolating the extra allocation rather than a separately optimized smaller wrapper layout.

Nine alternating fresh-process medians are 50.21 ms dynamic, 22.93 ms Cython, 21.75 ms native. This includes launch, Python startup, fixture reading, imports and first CarState read/write; it is not isolated schema compilation time.

Schema generation took 0.119 seconds and regenerated all four source/coverage outputs byte-for-byte in a fresh temporary directory. `/usr/bin/time` measured 63.56 seconds for both extension rebuilds with two CPUs and an existing static archive, including Cython translation but excluding schema generation/library compilation. Exact source/input/artifact hashes and binary sizes are in `build-manifest.json` (approximately 7.4 MiB Cython / 5.6 MiB native).

## Reviews and limits

Correctness reviewer `/root/generated_speed/correctness` independently reran 152-arm parity, retained-child/list lifetime, child serialization, malformed/default/range and GC-subclass cases. Main-agent adversarial review subsequently found a missed reentrant borrowed-container crash. The final writer takes immutable sequence snapshots and native RAII key/value reference snapshots before callbacks. Both modules pass all **22 subprocess mutation regressions**, including `__float__`, `__index__`, nested iteration/length hints, root/dictionary clearing, property/ListView mutation and exceptions. The reviewer independently re-reviewed those final changes and found no further blocker within scope.

Performance reviewer `/root/generated_speed/performance` reviewed matching work, both corpora, optimized dynamic comparisons, per-type behavior, list tradeoffs, ablations and stable baseline confirmations. Bulk's independent consumer suite additionally checks 20 projection/default/metadata/lifetime/malformed-refcount cases.

This remains an adapted experimental API: eager lists plus optional lazy views, integer enums, fixed generated schemas, and one interpreter/GIL. Reflection, pickle, dynamic schema loading, context managers, slicing and reader-object payload assignment are not implemented. Results establish gains for the tested API/workloads, not complete pycapnp compatibility or an absolute performance ceiling. Main-agent code/results review remains the final integration gate.
