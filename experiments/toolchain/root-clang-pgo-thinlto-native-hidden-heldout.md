# root-clang-pgo-thinlto-native-hidden-heldout: baseline versus clang-pgo-thinlto-native-hidden

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.72/3.67 | 3.12/3.11 | 1.192/1.180 | 1.186 |
| field write+encode | 20.17/19.17 | 14.44/14.62 | 1.397/1.311 | 1.354 |
| kwargs write+encode | 26.54/25.60 | 20.02/19.85 | 1.326/1.290 | 1.308 |
| payload assignment | 1.23/1.23 | 1.06/1.05 | 1.160/1.171 | 1.166 |
| CAN cached read | 11.37/11.52 | 9.29/9.52 | 1.224/1.210 | 1.217 |
| CAN cached write | 10.93/10.99 | 8.36/8.65 | 1.307/1.271 | 1.289 |
| LogReader parse+scan | 3.48/3.41 | 2.91/2.89 | 1.196/1.180 | 1.188 |
| dict export | 50.32/49.08 | 53.96/53.52 | 0.933/0.917 | 0.925 |
| copy+encode | 0.71/0.69 | 0.69/0.63 | 1.029/1.095 | 1.062 |
| reader pickle | 2.81/2.88 | 2.82/2.66 | 0.996/1.083 | 1.040 |
| LogReader pickle | 3.27/3.25 | 3.34/3.13 | 0.979/1.038 | 1.009 |
| schema reflection | 304.54/300.31 | 270.86/256.63 | 1.124/1.170 | 1.147 |
