# root-clang-heldout: baseline versus clang

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.70/3.70 | 3.55/3.47 | 1.042/1.066 | 1.054 |
| field write+encode | 19.44/18.99 | 17.03/16.90 | 1.142/1.124 | 1.133 |
| kwargs write+encode | 26.06/25.87 | 23.22/22.99 | 1.122/1.125 | 1.124 |
| payload assignment | 1.26/1.23 | 1.23/1.20 | 1.024/1.025 | 1.025 |
| CAN cached read | 11.87/11.23 | 11.30/11.53 | 1.050/0.974 | 1.012 |
| CAN cached write | 10.87/10.76 | 9.48/9.59 | 1.147/1.122 | 1.134 |
| LogReader parse+scan | 3.45/3.46 | 3.24/3.22 | 1.065/1.075 | 1.070 |
| dict export | 49.78/49.36 | 49.00/49.05 | 1.016/1.006 | 1.011 |
| copy+encode | 0.71/0.69 | 0.73/0.74 | 0.973/0.932 | 0.953 |
| reader pickle | 2.90/2.84 | 2.82/2.83 | 1.028/1.004 | 1.016 |
| LogReader pickle | 3.61/3.29 | 3.32/3.33 | 1.087/0.988 | 1.038 |
| schema reflection | 303.72/308.84 | 287.20/288.52 | 1.058/1.070 | 1.064 |
