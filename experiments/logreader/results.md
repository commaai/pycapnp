# Exploratory results

Two complete uncompressed real logs, training 1.rlog and held-out Ascent. Each number is the median milliseconds per complete two-log query; five randomized samples with calibrated inner loops. CPU affinity 0,1. Other teams were active on the shared host, so this is **not** the main-agent quiet final evaluation.

| Query | LogReader | Native staged | Two workers | Staged speedup |
|---|---:|---:|---:|---:|
| scalar | 328.48 | 27.87 | 14.97 | 11.79x |
| wide | 356.34 | 34.18 | 24.50 | 10.42x |
| model | 332.01 | 31.56 | 17.90 | 10.52x |
| can | 1054.90 | 176.83 | 141.64 | 5.97x |
| rare | 269.57 | 20.68 | 10.31 | 13.03x |

| Structural ablation | Staged/shared | Flat rows | Unshared paths | Fused/GIL held | Threads 1 | Threads 2 |
|---|---:|---:|---:|---:|---:|---:|
| scalar | 27.98 | 27.73 | 29.77 | 24.85 | 28.42 | 15.17 |
| wide | 33.78 | 33.33 | 42.15 | 28.43 | 34.34 | 19.58 |
| model | 31.24 | 31.57 | 31.64 | 28.18 | 31.01 | 18.55 |
| can | 184.87 | 181.77 | 180.75 | 165.01 | 197.94 | 142.44 |
| rare | 21.97 | 22.04 | 21.04 | 20.41 | 22.01 | 11.22 |

Structural ablations preceded the final iterative-path safety change; the final.json measurement above uses the rebuilt final implementation. Flat rows did not show a convincing benefit. Shared prefix planning helps wide queries. Fused serial avoids native staging, while staged scanning permits actual native concurrency.

| Adapter operation | ms |
|---|---:|
| setup_eager_logreader | 201.5121 |
| setup_lazy_rawlog | 11.0064 |
| consume_logreader | 425.7774 |
| consume_rawlog | 400.0084 |
| sparse_logreader | 145.3133 |
| sparse_rawlog | 16.8085 |
| pickle_logreader | 3.0102 |
| pickle_raw_events | 2.9508 |
| pickle_raw_log | 1.7252 |
| pickle_raw_log_oob | 1.7224 |
| forward_prepared_logreader | 0.6512 |
| forward_prepared_raw | 0.1063 |
| forward_cold_logreader | 1.0379 |
| forward_cold_raw | 0.0196 |

Setup-only comparison deliberately contrasts deferred versus eager work; full and sparse consumption quantify the result. Prepared forwarding excludes input creation, while cold forwarding includes it. Forwarding preserves original layout and unknown fields rather than reserializing them. Whole-log pickle batches storage; out-of-band buffers did not add a local roundtrip win.

All 12 original openpilot benchmark cases passed on the standardized 1,049-event/49-type corpus; SHA-256 `836f53c3742a79bbce5712f67e19f3cd4fe92e8155b68f5d53b4f42c22fdafde`. Its one-repeat run is a semantic smoke check, not a performance claim.

Validation: **71 passed, 5 skipped**, including 21 new experiment tests. Independent API/lifetime and performance/methodology reviews approved their bounded scopes. Main-agent final review remains authoritative.

Fresh-process RSS measurements (`memory.json`) found the staged CAN query reached
152,500 KiB peak versus 127,636 KiB for fused output. Flat storage was similar to
staged (152,708 KiB). Model-query peaks were hidden by the earlier import/decompression
high-water mark; a recorded zero incremental peak means **no new process high-water
mark**, not zero allocation. These coarse measurements support the staging-memory
tradeoff but do not replace an allocation profiler.
