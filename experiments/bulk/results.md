# Exploratory results

CPython 3.12.13, Threadripper PRO 5945WX, CPU5; seven alternating paired samples.
Other teams were running builds/experiments on other cores. Several route1 samples show
synchronized CPU-frequency/SMT contention changes; final selection should use a quiet rerun.
Raw distributions are committed, and these ratios are not on-device/onroad CPU claims.

| Case | Route1 speedup | Held-out ascent speedup |
|---|---:|---:|
| CAN read, identical parser | 1.90x | 1.75x |
| CAN write | 2.50x | 2.10x |
| Further CAN reader specialization | 1.08x | 1.19x |
| Further CAN writer specialization | 1.06x | 1.05x |
| Float list to Python list | 3.08x | 3.23x |
| Python iterable to float list | 7.67x | 6.95x |
| NumPy array through copied native buffer | 3.51x | 4.74x |
| Borrowed versus copied buffer to NumPy | 1.12x | 1.15x |
| Native buffer write versus scalar NumPy loop | 22.38x dedicated repeat | 22.44x |
| Compiled consumer, matched caching | 1.73x | 1.70x |
| Compiled consumer + numeric | 1.75x | 1.75x |
| Live parse + compiled consumer + numeric | 1.45x | 1.41x |
| LogReader parse + compiled consumer + numeric | 1.88x | 1.84x |

Route1 has 1,049 messages, 54 CAN batches with 26–84 frames, and 13 sampled model float lists
of length 33. Ascent has 1,060 messages, 58 CAN batches with 12–45 frames, and 10 float lists
of length 33. These sizes explain why native buffer setup remains material even after removing
all per-element Python operations. Copied-to-borrowed buffer comparison changes aliasing semantics.

The original 100-line benchmark also completes unchanged (`original-benchmark.txt`). Core
package tests: 50 passed, 5 skipped; bulk-specific tests: 26 passed.
