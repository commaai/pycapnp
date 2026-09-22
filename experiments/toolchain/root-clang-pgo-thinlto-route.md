# root-clang-pgo-thinlto-route: baseline versus clang-pgo-thinlto

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.95/3.86 | 3.20/3.23 | 1.234/1.195 | 1.215 |
| field write+encode | 25.44/26.03 | 19.06/19.00 | 1.335/1.370 | 1.352 |
| kwargs write+encode | 28.66/30.62 | 23.03/23.03 | 1.244/1.330 | 1.287 |
| payload assignment | 1.21/1.22 | 1.12/1.09 | 1.080/1.119 | 1.100 |
| CAN cached read | 22.62/22.82 | 20.17/20.53 | 1.121/1.112 | 1.117 |
| CAN cached write | 20.03/20.64 | 15.94/16.02 | 1.257/1.288 | 1.272 |
| LogReader parse+scan | 3.48/3.50 | 3.16/3.05 | 1.101/1.148 | 1.124 |
| dict export | 63.76/63.25 | 73.24/71.79 | 0.871/0.881 | 0.876 |
| copy+encode | 0.69/0.71 | 0.68/0.69 | 1.015/1.029 | 1.022 |
| reader pickle | 2.83/2.86 | 2.88/2.87 | 0.983/0.997 | 0.990 |
| LogReader pickle | 3.32/3.25 | 3.51/3.34 | 0.946/0.973 | 0.959 |
| schema reflection | 312.20/302.18 | 266.47/263.47 | 1.172/1.147 | 1.159 |
