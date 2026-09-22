# Final main-agent quiet measurements

The main agent reran commit `0b2b65c` sequentially on CPU0 after pausing team
builds. Commands, environment, extension hashes and exit codes are recorded in
the accompanying `experiments/results/*.run.json` files in the main report.
No runtime changes followed these measurements. These conclusions supersede the
earlier exploratory numbers in the experiment README.

## Approach 13: small whole-workload benefit

The fixed 1024-word pool with complete single-segment arena reset is a useful
preselected comparison; selecting the fastest of every tested size would amplify
measurement noise. Median microseconds per event from nine randomized rounds:

| Workload | Default | Arena reset | Time reduction |
|---|---:|---:|---:|
| Route from_dict + encode | 28.608 | 28.280 | 1.15% |
| Route field writes + encode | 24.338 | 23.898 | 1.81% |
| Held-out from_dict + encode | 25.167 | 24.913 | 1.01% |
| Held-out field writes + encode | 19.257 | 18.977 | 1.45% |
| Route empty builder + encode | 0.476 | 0.331 | 30.46% |
| Held-out empty builder + encode | 0.469 | 0.325 | 30.70% |

The full-workload ranges overlap. Treat these as modest approximately1–2%
median differences, not a decisive broad performance gain. The roughly30%
empty-message improvement is an allocator microbenchmark, not an openpilot CPU
saving. The trained pool was nearly null on held-out data: from_dict
25.167→25.102us and field writes19.257→19.255us. Presizing by a learned per-service
maximum does not create a compelling additional benefit here.

All construction variants were validated semantically before timing. Training
used the first41,290 of82,580 events from Subaru segment0, SHA256
`d34169fa4af2109089f56dc474f05ca6fac7bd19f57ba20cd5d453e78727619c`.
Evaluation used Subaru segment1 and the Ascent route, with different input hashes
recorded in the outputs. Trained timings include service-to-factory lookup.

Raw evidence: [route](../results/allocation-route.txt),
[held-out](../results/allocation-heldout.txt),
[route provenance](../results/allocation-route.run.json),
[held-out provenance](../results/allocation-heldout.run.json).

The implementation covers first-segment buffers, native object storage, and
complete single-segment arena reuse with bounded caches and last-alias ownership.
Preserving arbitrary multisegment allocation graphs is a possible additional
research direction, but the observed full-workload opportunity does not justify
calling it an obvious missing optimization. No production default is changed.

## Approach 16: substantial startup and repeated-reflection benefit

The archive is380,680 bytes. Internal setup includes loading and constructing the
first Event; values are medians across15 fresh subprocesses. Hyperfine measured
20 complete harness processes per mode after3 warmups:

| Mode | Internal setup median | Complete harness mean ± standard deviation |
|---|---:|---:|
| Source schema compiler | 14.298ms | 46.796 ±0.226ms |
| Eager compiled archive | 5.628ms | 37.4 ±0.3ms |
| Lazy compiled archive | 2.199ms | 33.7 ±0.3ms |
| Create archive from source | 15.287ms | 48.0 ±0.5ms |

Lazy archive loading is approximately6.5× faster for measured setup, but only
approximately1.39× faster for the complete harness. These are fresh processes
with warm filesystem caches, not cold storage, and the harness is not all of
openpilot startup. Artifact creation includes file writes without fsync. The
source schemas and dependencies must trigger explicit archive regeneration.

Raw evidence: [internal timings and reflection](../results/schema-startup.txt),
[hyperfine output](../results/schema-hyperfine.txt),
[hyperfine individual samples](../results/schema-hyperfine.json).

Repeated WebRTC reflection with independent mutable result containers fell from
307.77 to7.23us (approximately42.6×) using the declaration-keyed cache. The first
cache fill still pays reflection and encoding costs. Returning cached immutable
JSON took0.10us but changes the API, so it must not be presented as an equivalent
fresh-dictionary result. Returning a shared dictionary is also a different
mutability contract and is only a lower-bound measurement.

There is **no demonstrated steady-state serialization speedup** from archived
schemas. Eager and lazy adapters both completed all12 cases with the original
corpus SHA256 `836f53c3742a79bbce5712f67e19f3cd4fe92e8155b68f5d53b4f42c22fdafde`.
They use the same dynamic message implementation after schemas are loaded.
For example, dictionary export was62.99us eager versus63.05us lazy. The lazy
kwargs run was unstable (44.26us median,30.45–52.95us range, versus eager29.60us);
these isolated unpaired runs do not establish an inherent regression or gain.
The supported speed claims are startup and explicitly cached reflection.

Raw evidence: [eager unchanged workload](../results/schema-eager.txt),
[lazy unchanged workload](../results/schema-lazy.txt).

Final assessment: both bounded approaches are implemented and benchmarked.
Allocator reuse is a modest optional optimization on these workloads. Schema
archives and reflection caching offer clear benefits in their intended phases,
with explicit API/lifetime/artifact tradeoffs. Static linked schema descriptors
belong to the separately evaluated generated-binding approach.
