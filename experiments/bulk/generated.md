# Typed native consumer projection

Dependency: the sibling `speed/generated` branch; exact measured source/binary hashes and
openpilot schema commit are recorded in `generated-build.json`.

This joint experiment uses the generated team's native typed field accessors and fuses a
consumer into one C++ call. It returns ordinary Python tuples, floats, booleans and lists:

```
(kind, (valid, logMonoTime), hot_fields_or_None)
```

Both Python and native implementations project the four hot payloads from the original
benchmark (`carState`, `carControl`, `modelV2`, `longitudinalPlan`), and return None for other
payloads. Both read kind and metadata for every event. This is a scoped query API and is not
an interchangeable implementation of the original mixed-message scan, which materializes
all active payload wrappers. The native projection preserves scalar boxing and numeric-list
materialization; it removes dynamic schema dispatch, transient struct wrappers and repeated
Python/native calls. Nested handles stay on the C++ stack.

`generate_consumer.py` resolves schema indices from the generated team's `coverage.json`,
resolves field getter indices and nested-pointer offsets from the actual openpilot schemas,
and emits `generated_consumer.h`. It refuses unsupported groups and non-null explicit
pointer defaults rather than silently generating incorrect pointer reads.

Reproduce from a checkout of the bulk branch and a sibling generated branch:

```
# In the generated branch, run its documented generator/build first.
# Then regenerate the fused header against that exact generated corpus:
PYTHONPATH="$PWD:/home/batman/openpilot" /home/batman/openpilot/.venv/bin/python \
  experiments/bulk/generate_consumer.py ../generated/experiments/generated/coverage.json \
  experiments/bulk/generated_consumer.h
```

The generated branch commits a copy of this header and generator and exposes `project(data)`
from both `generated_cython` and `generated_native`. Rebuild those modules after updating
this header. The source header includes after `accessors.h`; it is not separately linkable
because the generated runtime's factory and owner types are private to each module.

```
PYTHONPATH="$PWD:/home/batman/openpilot:../generated/experiments/generated" taskset -c 0 \
  /home/batman/openpilot/.venv/bin/python experiments/bulk/bench_generated_consumer.py \
  /tmp/pr3704_logs/1.rlog.zst --output /tmp/generated-consumer-route1.json
```

The same command with `/tmp/opendbc_logs/ascent_1.rlog.zst` tests a held-out vehicle.
It asserts exact boxed projection equivalence before seven alternating paired samples.
`test_generated_consumer.py` adds explicit/default payloads, metadata extremes, owned outputs,
malformed input and input-reference leak checks for both frontends.

Post-fix route1: Python 3.09–3.13 us/event versus native projection 0.181–0.182 us/event,
about 17x. Held-out: 3.05–3.07 versus 0.177–0.179 us/event, also about 17x. Cython and
CPython expose the same fused C++ kernel, so their near-identical performance is expected;
this is not evidence that one binding generator wins. Earlier samples showed synchronized frequency/SMT shifts; the committed post-fix
reruns are stable, and the main agent will still perform quiet final measurement.

Independent correctness review found a pre-existing reference leak in the shared generated
runtime: acquiring a pinned bytes reference before `FlatArrayMessageReader` construction
leaked when malformed input threw. The generated team moved pin acquisition after successful
construction. The projection regression exercises this failure 100 times and checks refcounts.

Final validation: 20 projection tests passed in both the author run and an independent
correctness-reviewer run. Both independent reviewers approved the bounded projection after
the leak fix and paired benchmark reruns. No concrete remaining blocker was identified.
