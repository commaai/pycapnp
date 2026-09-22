# Measured compiler variants

Exploratory sequential runs under concurrent host load; these are NOT controlled speedup comparisons.
Median microseconds per benchmark item; lower is better. Use the final paired results for conclusions.

| Workload | baseline | o2 | native | lto | pgo | pgo-lto | pgo-lto-native | pgo-lto-hidden | clang | clang-thinlto | clang-pgo-thinlto | clang-pgo-thinlto-native-hidden |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| live read | 7.10 | 3.74 | 3.85 | 3.93 | 3.55 | 3.69 | 3.76 | 3.79 | 3.61 | 6.15 | 3.20 | 3.14 |
| field write+encode | 24.47 | 25.78 | 26.92 | 25.86 | 23.56 | 25.64 | 25.52 | 25.25 | 21.26 | 39.56 | 18.24 | 18.81 |
| kwargs write+encode | 28.87 | 30.17 | 30.59 | 29.67 | 27.19 | 28.63 | 29.60 | 28.75 | 25.51 | 46.16 | 21.80 | 21.78 |
| payload assignment | 1.23 | 1.27 | 1.25 | 1.27 | 1.12 | 1.14 | 1.14 | 1.11 | 1.21 | 2.00 | 1.05 | 1.05 |
| CAN cached read | 22.77 | 23.91 | 25.73 | 22.67 | 22.32 | 21.20 | 21.64 | 20.98 | 23.22 | 38.39 | 19.20 | 18.79 |
| CAN cached write | 19.82 | 20.75 | 20.68 | 19.26 | 18.32 | 18.06 | 18.18 | 17.36 | 17.70 | 33.49 | 14.97 | 15.00 |
| LogReader parse+scan | 3.54 | 4.04 | 3.67 | 3.75 | 3.41 | 3.60 | 3.61 | 3.60 | 3.44 | 5.69 | 2.92 | 2.98 |
| dict export | 63.24 | 75.33 | 65.71 | 64.24 | 64.25 | 66.02 | 64.15 | 64.24 | 65.05 | 107.66 | 67.82 | 69.38 |
| copy+encode | 0.70 | 0.73 | 0.70 | 0.70 | 0.62 | 0.60 | 0.60 | 0.59 | 0.73 | 1.16 | 0.63 | 0.66 |
| reader pickle | 2.92 | 3.02 | 3.00 | 2.96 | 4.81 | 2.79 | 2.74 | 2.77 | 2.98 | 4.64 | 2.67 | 2.68 |
| LogReader pickle | 3.35 | 3.71 | 3.41 | 3.43 | 5.54 | 3.45 | 3.19 | 3.05 | 3.64 | 6.22 | 3.11 | 3.31 |
| schema reflection | 302.88 | 315.68 | 310.53 | 304.43 | 509.76 | 290.11 | 291.65 | 288.39 | 288.29 | 496.96 | 251.67 | 259.58 |

## Binary evidence

| Variant | Bytes (unstripped) | SHA256 |
|---|---:|---|
| baseline | 6477096 | e24ec361874287ef280d7492528594e2e7d613c32c51461036b15697055faece |
| o2 | 5989320 | 1bf0ca5908c90305104cf4d74a2942b182bebf2c13443d2976b16a9667f017cf |
| native | 6606880 | 501e3716f9eda02f0681818648cca5556bb553e1413e8f8185eb31e54c8ac27c |
| lto | 8406304 | 16eccacf3793e0793a9eb73059f878f8653eea13a15bfab79980c25a036c68d3 |
| pgo | 5497232 | e80a53ca89f00b921fcb21e376442b1ba1339b83e07be0b784feb83634dad090 |
| pgo-lto | 6884736 | cd8bb861bc465d2339794b6d3b51549901bfbd7c51fdbf3537e264d2db0166e3 |
| pgo-lto-native | 6946232 | ebc4c66429f16030512d73b6d3dbfa072b59e966af285ccc6cc8a2c5d07ff1d0 |
| pgo-lto-hidden | 6878888 | b83b2c03c2b5e28cdd0caf25a7943b2eea0a23eb52fb63e7b2677f710535f6c0 |
| clang | 4261112 | 8ca8ab387f77114dc6fa76caf00282c890770fc2a663f613ec6f4ed4c2492c94 |
| clang-thinlto | 4084512 | 6abaa82eb20e0b4c6a133b5105718964619116d2671f4f77db3360aabf3eb105 |
| clang-pgo-thinlto | 4260232 | b755e88230a26c5922b7f30606f670830bda6c6f63a17f1e19bbdd9c5d5438f9 |
| clang-pgo-thinlto-native-hidden | 4225768 | fec3c74c3a765dc19c5123759bb7b9c692117eff6c210232bd17fe372976f1a4 |
