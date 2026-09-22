# root-pgo-lto-hidden-heldout: baseline versus pgo-lto-hidden

ABBA fresh-process comparison; speedup >1 favors candidate.

| Workload | Baseline us (A1/A2) | Candidate us (B1/B2) | Speedup (pair1/pair2) | Median speedup |
|---|---:|---:|---:|---:|
| live read | 3.71/3.68 | 3.62/3.59 | 1.025/1.025 | 1.025 |
| field write+encode | 19.24/19.20 | 18.93/18.95 | 1.016/1.013 | 1.015 |
| kwargs write+encode | 25.65/25.84 | 25.75/25.00 | 0.996/1.034 | 1.015 |
| payload assignment | 1.24/1.23 | 1.12/1.12 | 1.107/1.098 | 1.103 |
| CAN cached read | 11.76/11.49 | 10.40/10.56 | 1.131/1.088 | 1.109 |
| CAN cached write | 10.92/10.72 | 9.55/9.67 | 1.143/1.109 | 1.126 |
| LogReader parse+scan | 3.47/3.40 | 3.37/3.38 | 1.030/1.006 | 1.018 |
| dict export | 49.70/49.57 | 49.03/49.09 | 1.014/1.010 | 1.012 |
| copy+encode | 0.70/0.69 | 0.58/0.61 | 1.207/1.131 | 1.169 |
| reader pickle | 2.85/2.89 | 2.67/2.61 | 1.067/1.107 | 1.087 |
| LogReader pickle | 3.36/3.30 | 3.05/3.03 | 1.102/1.089 | 1.095 |
| schema reflection | 302.21/302.69 | 280.52/283.21 | 1.077/1.069 | 1.073 |
