# Native batches and compiled consumer experiments

These opt-in APIs keep Cap'n Proto wire compatibility. They do not change existing API paths.
The original `benchmarks/bench_openpilot.py` remains 100 lines.

Implemented approaches:

* **4 — CAN batches:** `_bulk_can_read` walks native frame readers and returns the exact
  `(timestamp, [(address, bytes, source), ...])` shape. `_bulk_can_write` initializes native
  frame builders. `_BulkCanFields` pins cached schema fields. The specialized inner path
  converts unsigned integers/Data directly; writes use direct setters for ordinary int/bytes
  tuples and retain the generic setter fallback for other previously supported values.
  `specialized=False` retains the intermediate implementation for ablation.
* **7 — numeric lists:** `_bulk_float_read` copies Float32/64 lists directly into Python floats;
  `_bulk_float_write` supports iterables and contiguous native float buffers. Iterable source
  references are snapshotted before invoking conversion callbacks. Matching primitive buffer
  writes use guarded `memmove`; differing widths/layouts use typed native conversion loops.
  `_bulk_float_buffer_read` produces an independent immutable native-format buffer, avoiding
  Python float allocation. `_bulk_float_view` borrows little-endian contiguous primitive data
  and pins the list reader; non-native endian or inline-composite evolved layouts use a copy.
  Borrowed views are read-only through the view, but a separate builder alias can mutate them.
  They deliberately have different ownership semantics from copied lists/arrays.
* **9 — compiled consumers:** `_bulk_read_fields` implements every branch and field access in
  the representative benchmark with typed Cython locals, plus local actuator caching. The
  `numeric` switch isolates bulk numeric conversion. The `collect` switch provides an untimed
  output oracle. The LogReader adapter explicitly unwraps `CachedEventReader._evt`.

Run from this worktree:

```
PYTHONPATH="$PWD:/home/batman/openpilot" taskset -c 5 \
  /home/batman/openpilot/.venv/bin/python experiments/bulk/bench.py \
  /tmp/pr3704_logs/1.rlog.zst --output experiments/bulk/route1.json
```

The script uses the exact original 1,000-event sampling plus first-of-every-type corpus.
It validates CAN results, float copies, NumPy results, and hot consumer projections outside
measurement. Seven paired samples alternate old/new order; each calibrated sample is about
120 ms. JSON includes all sample times, message counts, CAN batch sizes and float list lengths.
GC stays enabled; collection runs outside timed samples. Startup, file I/O and decompression
are excluded. Results are microseconds per event, CAN batch, or float list as appropriate.

Attribution controls include the same CAN parsing wrapper, generic versus specialized CAN,
matching Python actuator caching, float-only versus compiled-consumer gains, and scalar NumPy
writes versus native buffer writes. NumPy borrowed versus copied buffers is explicitly a
representation/ownership comparison, not interchangeable semantics. End-to-end live parsing
and LogReader scanning are included separately.

The held-out `/tmp/opendbc_logs/ascent_1.rlog.zst` tests another vehicle's message shapes.
These CPU5 measurements are exploratory: other teams were building on other cores, so the
main agent should perform final controlled measurements before selecting a production change.

Correctness coverage includes both CAN union members, empty batches, maximum addresses and
sources, owned copied bytes, type/range errors, wrong cached schema fields, Float32/64 and
empty lists, NaN/infinity, source mutation during `__float__`, invalid buffers, overlapping
source/target buffers, borrowed-view lifetime/aliasing, evolved inline-composite fallback,
and `None` rejection. Existing package tests also pass.

Review history: independent correctness and performance reviewers rejected the initial pass.
Their findings led to stable conversion snapshots (fixing a reproducible callback-mutation
segfault), non-null argument checks, output oracles, paired samples, parser/caching controls,
CAN specialization, guarded zero-copy views, and direct native-buffer writes. Final review
records/results are kept with this experiment; no claim of a universal optimization ceiling
is implied by approval of these implemented paths.
