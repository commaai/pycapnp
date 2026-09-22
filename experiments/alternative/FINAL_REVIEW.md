# Final independent review: approaches 17–19

Reviewed root's quiet CPU-0 results on 2026-09-22. All five runs have `.run.json` sidecars with `returncode: 0`, recording commit `37730ac`, commands, working directory, and import paths. No benchmarks or builds were run during this review. A separate performance-focused reviewer independently checked the same completed files and approved the bounded conclusions below.

The original corpus is `/tmp/pr3704_logs/1.rlog.zst`; the held-out corpus is the different-car `/tmp/opendbc_logs/ascent_1.rlog.zst`. Each contains 1,000 selected messages for each of the five measured event types. Every per-type corpus hash differs between routes. These are per-type workloads, not service-frequency-weighted onroad CPU measurements.

## 17. Direct wire codec

The typed library control isolates the backend using shared compiled Python conversion functions, borrowed bytes, the same projection, and byte-identical writer output. The optimized library writer uses its known final buffer directly, avoiding an allocation/copy disadvantage.

| Median µs/Event | Original | Held out |
|---|---:|---:|
| Direct read | 0.1089 | 0.1086 |
| Typed libcapnp read | 0.1292 | 0.1282 |
| Direct write | 0.0632 | 0.0649 |
| Typed libcapnp flat-buffer write | 0.1048 | 0.1063 |
| Typed libcapnp allocating write | 0.1504 | 0.1509 |

This supports approximately **15–16% less read time and 39–40% less write time** for direct wire access in the selected scalar/nested CarState operation. It does not support attributing the much larger dynamic-pycapnp comparison to bypassing libcapnp: most of that gain comes from native specialization and removing Python work.

The broader direct-reader measurements also reproduce:

| Median µs/Event | Original dynamic/direct | Held-out dynamic/direct |
|---|---:|---:|
| CarState | 5.302 / 0.114 | 5.378 / 0.108 |
| CarControl | 5.132 / 0.089 | 5.053 / 0.083 |
| ModelV2 | 10.970 / 1.638 | 11.191 / 1.602 |
| LongitudinalPlan | 6.103 / 0.710 | 6.118 / 0.820 |
| CAN batch | 68.157 / 5.904 | 36.439 / 3.339 |

Native CarState/plan/CAN writer medians are 0.062/0.247/0.940 µs on the original route and 0.062/0.251/0.489 µs held out. These comparisons include fused tuple-to-message construction; the reference builds kwargs/dictionaries within the timed call. CAN units are batches, not individual frames. Different CAN costs across routes are consistent with different batch contents and also appear in the reference implementation.

Correctness scope remains explicit: five supported read projections and three specialized writers, not a general codec. Readers reject some malformed inputs accepted by libcapnp: 312 original-route and 305 held-out mutations out of 10,000. No sampled input accepted by the direct reader was rejected by the library control. The isolated timing comparison concerns successful inputs, not identical parser semantics. The prior adversarial, mutation, full-message writer, schema validation, and sanitizer evidence remains applicable.

Sources: [original backend control](../results/backend-control-route.txt), [held-out backend control](../results/backend-control-heldout.txt), [original projections](../results/alternative-route.txt), [held-out projections](../results/alternative-heldout.txt).

## 18. Runtime schema compilation

Fresh-process hyperfine means over 15 runs, including shared harness imports:

| Variant | Mean |
|---|---:|
| Cold native compilation | 527.2 ms |
| Populated compiler cache | 154.4 ms |
| Prebuilt extension | 150.6 ms |

On this host, runtime compilation adds approximately 377 ms cold and 4 ms cached relative to prebuilt loading. The cold series retains a 558.8 ms outlier, explicitly reported by hyperfine; it does not alter the conclusion. Warm machine code is identical to prebuilt code, so this experiment establishes deployment/cache costs, not an additional execution speedup. It is schema-specialized C compilation on demand, not an adaptive tracing JIT.

Sources: [startup output](../results/jit-startup.txt), [all hyperfine samples](../results/jit-startup.json).

## 19. Alternative binding frameworks

| Median µs/Event | Original | Held out |
|---|---:|---:|
| CPython individual call | 0.1104 | 0.1110 |
| pybind11 individual call | 0.1939 | 0.1947 |
| CPython native batch | 0.0919 | 0.0914 |
| pybind11 native batch | 0.0854 | 0.0851 |
| CFFI compiled API, batch-local output reuse | 0.3649 | 0.3771 |
| ctypes PyDLL, batch-local output reuse | 0.5211 | 0.5234 |

The pattern reproduces across both corpora. Direct CPython wins for individual calls; pybind11's batch is approximately 7% faster in this particular implementation. This supports batching and direct native Python-result construction, not universal superiority of a framework. CFFI/ctypes comparisons retain their Python-side struct-field extraction. No unimplemented framework or language is covered by these results.

## Final regression commands

Root can run these after the quiet performance queue. They compile the small experiment kernel, so they were not rerun during this read-only review. The existing openpilot environment supplies CFFI; pybind11 is unnecessary for these regression scripts.

```sh
cd /tmp/capnp-speed/alternative
export PYTHONPATH=/tmp/capnp-speed/baseline:/home/batman/openpilot
PYTHON=/home/batman/openpilot/.venv/bin/python
"$PYTHON" experiments/alternative/test_wire.py
"$PYTHON" experiments/alternative/test_adversarial.py
"$PYTHON" experiments/alternative/test_writers.py
"$PYTHON" experiments/alternative/test_layout.py
```

The final-source 100,000-mutation ASan/UBSan run already passed. No new native implementation change occurred in this review, so repeating it is not necessary absent a new concern.
