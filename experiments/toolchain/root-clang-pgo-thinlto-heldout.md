# root-clang-pgo-thinlto-heldout: baseline versus clang-pgo-thinlto

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.64/6.57 | 3.06/3.17 | 1.190/2.073 | 1.631 |
| field write+encode | 19.10/20.90 | 14.46/15.26 | 1.321/1.370 | 1.345 |
| kwargs write+encode | 25.54/27.18 | 20.06/20.94 | 1.273/1.298 | 1.286 |
| payload assignment | 1.23/1.24 | 1.03/1.09 | 1.194/1.138 | 1.166 |
| CAN cached read | 11.54/11.26 | 9.44/9.87 | 1.222/1.141 | 1.182 |
| CAN cached write | 10.80/10.76 | 8.40/8.24 | 1.286/1.306 | 1.296 |
| LogReader parse+scan | 3.39/3.43 | 2.85/2.87 | 1.189/1.195 | 1.192 |
| dict export | 49.40/49.61 | 53.39/54.06 | 0.925/0.918 | 0.921 |
| copy+encode | 0.69/0.70 | 0.64/0.66 | 1.078/1.061 | 1.069 |
| reader pickle | 2.81/2.89 | 2.62/2.68 | 1.073/1.078 | 1.075 |
| LogReader pickle | 3.25/3.33 | 3.13/3.17 | 1.038/1.050 | 1.044 |
| schema reflection | 305.47/301.84 | 250.70/254.90 | 1.218/1.184 | 1.201 |
