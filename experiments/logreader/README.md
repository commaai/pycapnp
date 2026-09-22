# Native log experiments

This branch implements approaches 8 (native filtering/projection), 11 (retained
serialized buffers and pickle), and 15 (parallel native scanning). Existing
pycapnp reader/builder APIs are unchanged; these are opt-in adapters.

## APIs

```python
from capnp.lib.capnp import project_stream
from capnp.logstream import RawLog, project_many

paths = ['logMonoTime', 'modelV2.position.x', 'modelV2.leadsV3.x']
rows = project_stream(unpacked_bytes, log.Event.schema, 'modelV2', paths)
rows = project_stream(unpacked_bytes, log.Event.schema, 'modelV2', paths, fused=True)
per_segment = project_many([segment1, segment2], log.Event, 'modelV2', paths, workers=2)
raw = RawLog(unpacked_bytes, log.Event)
assert raw.to_bytes() is raw.data
```

Projection returns tuples in input order. Dotted paths can traverse structs and
arbitrarily nested lists; list dimensions are retained. Leaves may be primitive
values, enums (raw integers), Text, Data, or lists of these. Full struct/dict
conversion is deliberately left to the existing APIs and separate conversion
experiments. Signed integers and UInt64 timestamps preserve exact values.

The default staged scan releases the GIL while native readers validate and
collect results. Compact float/integer/byte-string lists avoid heavyweight
per-element staging objects. `fused=True` constructs Python output directly,
reducing single-thread overhead but retaining the GIL. `project_many` uses
independent streams and keeps output order; executor creation is included.
Shared nested-prefix plans resolve field handles once per query and fetch shared
struct/list prefixes once per matching event. `shared=False` and `flat=True`
exist to reproduce measured ablations, not as recommended settings.

`RawLog` validates framing and retains immutable bytes. Iteration yields lazy
frame views without copying their bytes. One surviving event or child reader
retains the whole original log; `event.detach()` creates an isolated frame for
long-lived use. `serialized_view()` supports contiguous forwarding; `to_bytes()`
returns bytes. Mutation through `as_builder()` remains an independent copy.
Whole-log pickle serializes one buffer; protocol 5 supports out-of-band buffers.
Individual-event pickle detaches its frame. Restoring requires schema registration,
like existing pycapnp pickle. Out-of-band transfer still depends on the caller's
transport; this benchmark does not claim free interprocess transfer.

Malformed framing and accessed pointer data raise instead of LogReader's
warning-and-partial-return policy. Unaccessed payloads remain lazily unvalidated.
Projection retains Cap'n Proto traversal and nesting limits per message. Shared
prefixes naturally consume fewer traversal-budget units than repeated accesses.
Forwarding preserves original bytes, including unknown fields and segment layout.
It does not validate every unaccessed payload or canonicalize serialization.

## Validation and measurement

`test_logstream.py` covers scalar widths/defaults, lists and nested lists of
structs, far pointers/multiple segments, enums, Unicode errors, framing and
pointer errors, threading exceptions, limits, input validation, builder isolation,
backing-buffer lifetimes, buffer shapes/alignment, and pickle protocols 4/5.

```sh
python setup.py build_ext --inplace -j2
python -m pytest -q test experiments/logreader/test_logstream.py
PYTHONPATH="$PWD:/home/batman/openpilot" taskset -c 0,1 \
  /home/batman/openpilot/.venv/bin/python experiments/logreader/bench.py \
  /tmp/pr3704_logs/1.rlog.zst /tmp/opendbc_logs/ascent_1.rlog.zst --repeat 5
PYTHONPATH="$PWD:/home/batman/openpilot" taskset -c 0,1 \
  /home/batman/openpilot/.venv/bin/python experiments/logreader/ablate.py \
  /tmp/pr3704_logs/1.rlog.zst /tmp/opendbc_logs/ascent_1.rlog.zst --repeat 5
```

The original <=100-line openpilot benchmark is unchanged. This experiment adds
five explicit idiomatic LogReader query baselines: scalar, wide/shared-prefix,
model trajectories, CAN lists, and rare carParams events. A generic recursive
oracle checks equality but is excluded from timing. I/O and decompression are
excluded from every case. Result destruction is included. Cases run in seeded
random order, with calibrated inner loops targeting at least 0.1 seconds/sample.
Both requested training log and held-out Ascent log are checked for equal outputs.

Lazy setup is explicitly not equivalent to eager LogReader construction: its
missing work is deferred. Full consumption and sparse consumption include setup
and expose that tradeoff. Pickle comparisons decode and consume equivalent
results. Forwarding compares cold and prepared inputs separately. Threads1,
threads2, fused, staged, flat storage and unshared plans use the same data/output.

`exploratory.json`, `expanded.json`, and `refined.json` are historical development
measurements; they are not final headline results. `final.json` uses calibrated
fair references. `ablations.json` records the architectural alternatives. All
runs are exploratory on a shared host; final isolated evaluation belongs to the
main benchmark coordinator. Original versions used slower generic references or
single-core threading as noted in the review history; their numbers must not be
mixed with final comparisons.

## Review history and outcome

An API/lifetime reviewer and an independent performance/methodology reviewer
reviewed each implementation twice, then reviewed the structural ablations.
Their requests led to concrete fixes: None/NUL input validation, generator path
materialization, safe descendant buffer ownership, authoritative buffer lengths,
nested-list handling, compact numeric/CAN staging, shared prefix plans, fused
Python output, flat storage experiments, idiomatic baselines, and calibrated
randomized timing. Final API review found no remaining blockers; final performance
review judged this bounded architecture scope complete. The complete available
repository plus experiment tests passed: 71 passed, 5 skipped.

Shared prefix plans are retained. Fused sequential conversion and staged parallel
conversion remain distinct useful choices. Flat storage's approximately 0–2%
change overlaps timing spread and is rejected as a performance recommendation.
Full raw object consumption has only a modest benefit, not the large projection
speedups. Individual raw-event pickle can regress; whole-log pickle is the useful
batched form. Out-of-band buffers show no additional local roundtrip speed benefit.

The main-agent review additionally required iterative cached-ancestor resolution
and iterative linear path traversal. A 10,000-component path regression now runs
across staged/fused and shared/unshared variants, avoiding Python/C++ call-stack
growth before reader-limit checks. The final rebuilt suite contains 21 new tests.
