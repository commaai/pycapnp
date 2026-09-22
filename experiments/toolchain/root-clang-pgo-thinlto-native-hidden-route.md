# root-clang-pgo-thinlto-native-hidden-route: baseline versus clang-pgo-thinlto-native-hidden

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.67/3.74 | 3.12/3.11 | 1.176/1.203 | 1.189 |
| field write+encode | 24.21/24.49 | 18.13/18.08 | 1.335/1.355 | 1.345 |
| kwargs write+encode | 28.85/28.91 | 21.68/21.60 | 1.331/1.338 | 1.335 |
| payload assignment | 1.23/1.22 | 1.04/1.05 | 1.183/1.162 | 1.172 |
| CAN cached read | 23.33/23.30 | 19.09/19.32 | 1.222/1.206 | 1.214 |
| CAN cached write | 20.32/19.78 | 15.02/15.11 | 1.353/1.309 | 1.331 |
| LogReader parse+scan | 3.50/3.50 | 2.96/2.93 | 1.182/1.195 | 1.188 |
| dict export | 64.43/64.49 | 68.50/68.88 | 0.941/0.936 | 0.938 |
| copy+encode | 0.69/0.69 | 0.65/0.65 | 1.062/1.062 | 1.062 |
| reader pickle | 2.86/2.89 | 2.68/2.70 | 1.067/1.070 | 1.069 |
| LogReader pickle | 3.30/3.37 | 3.15/3.16 | 1.048/1.066 | 1.057 |
| schema reflection | 302.43/298.55 | 257.08/256.19 | 1.176/1.165 | 1.171 |
