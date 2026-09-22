# Final controlled compiler review

Four screened candidates were rerun against the corrected GCC O3 baseline in
fresh-process ABBA order on CPU 0, with five samples per benchmark process.
Other experiment builds and timings were paused. This reduces our own contention;
it does not establish exclusive host access. Each comparison has two process
medians per side, not a statistical confidence interval. Results apply to this
Threadripper x86 host, Python 3.12, Cython 3.3.0, GCC 13.3 and Clang 18.1.3.

Every ABBA has matching serialized corpus SHA256, byte count, event distribution,
and all 12 workload names/item counts. Primary corpus: 1,049 events, 49 types.
Different-car Ascent heldout: 1,060 events, 60 types. Saved binary hashes match the
comparison metadata. `results/root-validation.json` records these checks. The
review also independently matched all 12 accepted binaries to the artifact
manifest and confirmed their retained integration logs each report 61 passes.

## Results and choice

Ranges below span the primary and heldout process-pair median ratios; greater
than one favors the candidate. They are not uncertainty bounds.

| Candidate | Field write+encode | Kwargs write+encode | CAN write | Dict export |
|---|---:|---:|---:|---:|
| GCC PGO+LTO+hidden | 1.015–1.035x | 1.015–1.045x | 1.117–1.126x | 1.003–1.012x |
| Clang O3 | 1.133–1.149x | 1.123–1.124x | 1.134–1.138x | 1.007–1.011x |
| Clang PGO+ThinLTO | 1.345–1.352x | 1.286–1.287x | 1.272–1.296x | 0.876–0.921x |
| Clang PGO+ThinLTO+native+hidden | 1.345–1.354x | 1.308–1.335x | 1.289–1.331x | 0.925–0.938x |

Clang PGO combinations give the strongest broad construction gains in this search,
but dictionary export takes approximately 8–14% longer with portable flags and
7–8% longer with host-specific native/hidden flags. Ordinary Clang improves
construction without that substantial dictionary tradeoff, but copy+encode is
approximately 5% slower on both corpora. GCC PGO+LTO+hidden offers approximately
10–13% CAN and 17–20% copy speedups, with nearly flat dictionary/scan performance.
These tradeoffs do not justify an unconditional compiler default change.

The host-native combination gives stable live-read ratios around 1.19x on both
corpora and parse/scan around 1.19x. Its benefit cannot be attributed separately
to native CPU instructions or hidden visibility because both flags change in
that comparison; it cannot be distributed as a portable wheel.

Two individual comparisons are visibly noisy. GCC route LogReader pickle has
candidate medians 3.05 and 4.74 us against baseline 3.30/3.30 us; its displayed
0.889x ratio is inconclusive, while heldout is stable around 1.095x. Portable
Clang PGO heldout live-read has baseline medians 3.64 and 6.57 us against candidate
3.06/3.17 us. Its displayed 1.631x ratio must not be presented as a typical gain;
the first pair is 1.190x. No observations were discarded or replaced. Near-flat
ratios elsewhere are descriptive, not proof of a small improvement.

## Final signoff and limits

Independent final review found no unresolved correctness blocker or obvious
missing optimization inside this bounded compiler search. The retained raw
reports and provenance support the workload-specific conclusions above. Review
accepts the documented GCC identical-code-folding workaround and exclusion of
rejected binaries; it does not claim a compiler bug diagnosis beyond the observed
miscompilation and successful workaround.

These experiments compile the original minimal runtime, not the final optimized
dynamic branch. Do not multiply their speedups or claim a measured combined gain.
Actual ARM hardware, daemon-weighted PGO training, post-link optimization and
compiler optimization of other experimental runtimes remain unmeasured scope.
Training includes startup/corpus preparation and elapsed-time-balanced benchmark
cases, not measured daemon frequencies. Twelve screened variants plus controlled
reruns of four promising choices constitute a completed experiment, not a proof
that every possible compiler setting or workload-specific profile is maximal.

See `root-*.md` for all per-case values and `results/root-*.bench.txt` for raw
process output. No production optimization default has changed.
