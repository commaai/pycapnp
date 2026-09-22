# root-pgo-lto-hidden-route: baseline versus pgo-lto-hidden

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.69/3.72 | 3.64/3.61 | 1.014/1.030 | 1.022 |
| field write+encode | 24.20/25.33 | 23.99/23.87 | 1.009/1.061 | 1.035 |
| kwargs write+encode | 29.01/29.36 | 27.79/28.08 | 1.044/1.046 | 1.045 |
| payload assignment | 1.22/1.22 | 1.12/1.10 | 1.089/1.109 | 1.099 |
| CAN cached read | 23.18/24.19 | 20.89/21.03 | 1.110/1.150 | 1.130 |
| CAN cached write | 20.15/19.74 | 18.08/17.63 | 1.114/1.120 | 1.117 |
| LogReader parse+scan | 3.47/3.46 | 3.49/3.48 | 0.994/0.994 | 0.994 |
| dict export | 63.90/63.75 | 63.89/63.41 | 1.000/1.005 | 1.003 |
| copy+encode | 0.72/0.70 | 0.59/0.59 | 1.220/1.186 | 1.203 |
| reader pickle | 2.89/2.88 | 2.65/2.78 | 1.091/1.036 | 1.063 |
| LogReader pickle | 3.30/3.30 | 3.05/4.74 | 1.082/0.696 | 0.889 |
| schema reflection | 301.09/300.03 | 289.21/290.15 | 1.041/1.034 | 1.038 |
