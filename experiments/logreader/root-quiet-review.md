# Root-controlled quiet evaluation

Final read-only review of root-controlled outputs. No builds or benchmarks were run during this review. These measurements supersede the earlier shared-host exploratory headline numbers. Runtime source is unchanged by this report.

Recorded runtime revision: `dddd04747adc27d55fe41c1ca8c960784c8b8e9b`; extension `/tmp/capnp-speed/logreader/capnp/lib/capnp.cpython-312-x86_64-linux-gnu.so`. Both runs use affinity 0,1 and the same training/held-out real log pair. Full run: seven samples; ablation: five samples; seeded interleaving with calibrated inner loops.

Root-controlled sources:
- `/tmp/worktrees/tmp.v7Yjr2sXmw/our_capnp/pycapnp/experiments/results/logreader.txt`; SHA-256 `67ae133266a223c0405c7aabd356bf693154c7e56b377f1a2d15e6651ba0ad56`.
- `/tmp/worktrees/tmp.v7Yjr2sXmw/our_capnp/pycapnp/experiments/results/logreader-ablation.txt`; SHA-256 `2bdc6b8ef2936277ad9f3dbea1cdb15a76cbc4c29e9c3ddc8389447fb16ac1c6`.

## Cold in-memory projection

Medians cover both complete input logs, excluding I/O/decompression. Native and idiomatic LogReader queries produce equal requested values. These comparisons construct fresh LogReader instances; they do not measure repeated queries over an already cached LogReader. Each ratio below uses only measurements from the same full run.

| Query | LogReader ms | Native ms | Two workers ms | Native speedup | Two-worker speedup |
|---|---:|---:|---:|---:|---:|
| scalar | 333.25 | 27.53 | 15.17 | 12.11x | 21.97x |
| wide | 356.63 | 33.52 | 24.27 | 10.64x | 14.70x |
| model | 333.72 | 30.43 | 17.92 | 10.97x | 18.62x |
| can | 1058.67 | 182.78 | 140.73 | 5.79x | 7.52x |
| rare | 269.88 | 20.56 | 10.26 | 13.12x | 26.30x |

Native two-worker scaling is 1.81x scalar, 1.38x wide, 1.70x model, 1.30x CAN, and approximately 2.00x rare. CAN creates substantial Python output under the GIL; its smaller scaling benefit fits that architecture.

## Structural alternatives

Within the separate ablation run, fused Python output lowers serial time by 5.2–12.9%; it keeps the GIL and therefore serves a different use case from staged native concurrency. Shared prefix planning reduces wide-query time by 19.82%. Flat storage changes remain small/inconsistent and do not establish an improvement.

**Do not mix the two runs:** wide threading is 24.27 ms in the full run versus 18.84 ms in the ablation, with nonoverlapping sample ranges. The cause is unestablished. The table uses the full-run 24.27 ms value; combining the faster ablation time with the full-run LogReader baseline would overstate the demonstrated speedup.

## Adapter results and equivalence limits

- Header consumption across every event (timestamp and union name) takes 7.56% less time. This is not full payload decoding.
- Sparse header consumption, including setup, is 7.76x faster. Framing-only setup deliberately defers reader construction; its setup ratio must not be presented as equivalent decoding work.
- Individual-event pickle roundtrip plus header consumption takes 3.81% less time. Whole-log batched pickle is 1.77x faster.
- Protocol-5 out-of-band buffers lower the local median by 1.15%, with overlapping samples. No meaningful extra local roundtrip gain is established, and this does not measure interprocess transport.
- Prepared forwarding is 6.23x faster. Cold forwarding is 47.87x faster specifically because it validates framing and returns unchanged backing bytes, versus decoding/rebuilding serialized messages. It is not a 47.87x payload-decoding or serialization-engine gain.
- Shared frame views can retain the entire log; callers holding isolated events should use `detach()`.

## Final disposition

The independent performance reviewer re-read these actual root-controlled outputs and approved completion within the agreed practical scope. The implementation-team lead independently re-read the outputs and concurs: no unresolved concrete structural optimization blocks delivery of these experiments. A universal performance ceiling is not claimed. The wide-thread cross-run discrepancy remains an explicitly reported precision limitation, not grounds for selecting the more favorable value.

Root reports a 76-test validation run and equality checks across three corpora. The previous independent API/lifetime review and root-requested deep-path fixes remain documented in README.md. No runtime edits, tests, or benchmarks were performed as part of this final read-only measurement review.
