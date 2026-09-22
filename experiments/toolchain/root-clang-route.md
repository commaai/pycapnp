# root-clang-route: baseline versus clang

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.66/3.71 | 3.63/3.59 | 1.008/1.033 | 1.021 |
| field write+encode | 24.23/24.35 | 21.26/21.04 | 1.140/1.157 | 1.149 |
| kwargs write+encode | 28.85/29.29 | 25.85/25.90 | 1.116/1.131 | 1.123 |
| payload assignment | 1.21/1.22 | 1.23/1.22 | 0.984/1.000 | 0.992 |
| CAN cached read | 22.86/22.59 | 23.22/23.12 | 0.984/0.977 | 0.981 |
| CAN cached write | 20.11/19.81 | 17.50/17.59 | 1.149/1.126 | 1.138 |
| LogReader parse+scan | 3.51/3.50 | 3.31/3.34 | 1.060/1.048 | 1.054 |
| dict export | 63.90/64.48 | 63.84/63.62 | 1.001/1.014 | 1.007 |
| copy+encode | 0.70/0.70 | 0.73/0.73 | 0.959/0.959 | 0.959 |
| reader pickle | 2.86/2.89 | 2.95/2.96 | 0.969/0.976 | 0.973 |
| LogReader pickle | 3.32/3.33 | 3.43/3.37 | 0.968/0.988 | 0.978 |
| schema reflection | 298.40/300.82 | 285.62/288.20 | 1.045/1.044 | 1.044 |
