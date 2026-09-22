# Initial baseline

Implementation: `minimal` at `caee18aeef0a9a54ad8f98292a325a1675a43bec`.
Openpilot: `7f6f13997c3c9b8e27e1581583f61e3fcabc5151`.
CPython 3.12.13, Linux x86_64, AMD Ryzen Threadripper PRO 5945WX, pinned to CPU 0.
Default `--messages 1000 --repeat 5`, cyclic GC enabled.

Local input: `/tmp/pr3704_logs/1.rlog.zst` (not included in the repository).
Input SHA-256: `0cd538d9c73d64271d98f908d02465f7513ed2d79c8e4ea0d76a59ff26f6446b`.
Corpus SHA-256: `836f53c3742a79bbce5712f67e19f3cd4fe92e8155b68f5d53b4f42c22fdafde`.
Corpus: 1,049 Events, 49 event types, 693,448 serialized bytes.

| Case | Median us/item | Min, max | Items/batch |
| --- | ---: | ---: | ---: |
| live read | 3.83 | 3.80, 3.93 | 1049 |
| field write+encode | 25.58 | 25.34, 26.49 | 1049 |
| kwargs write+encode | 29.78 | 29.54, 30.03 | 1049 |
| payload assignment | 1.23 | 1.23, 1.25 | 1049 |
| CAN cached read | 24.39 | 24.15, 26.66 | 54 |
| CAN cached write | 20.54 | 20.36, 20.73 | 54 |
| LogReader parse+scan | 3.68 | 3.61, 3.80 | 1049 |
| dict export | 65.04 | 64.01, 67.00 | 1049 |
| copy+encode | 0.70 | 0.70, 0.90 | 1049 |
| reader pickle | 3.11 | 2.98, 3.57 | 1049 |
| LogReader pickle | 3.89 | 3.63, 4.95 | 1049 |
| schema reflection | 377.68 | 318.45, 511.81 | 1 |

These are workload-specific starting measurements, not a speedup claim or CI
threshold. See [README.md](README.md) for item definitions and comparison rules.
