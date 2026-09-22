# Allocation and precompiled-schema experiments

Final quiet measurements and conclusions are in [FINAL_RESULTS.md](FINAL_RESULTS.md).

These optional APIs leave the normal message API and wire format unchanged.

## Approach 13: allocation policies

`capnp._MallocMessageBuilder(first_segment_words).init_root(schema)` exposes
presizing. `capnp.BuilderPool(words, capacity, recycle_builder=False,
reset_arena=False).new_message(schema, **values)` adds three independently
measured mechanisms:

- First-segment buffer reuse after the final Python message alias disappears.
- Optional outer native builder storage reuse after destruction.
- Optional complete single-segment arena reset, preserving native allocation
  metadata. Multisegment messages fall back to destruction. Reset zeros every
  allocated word, restores the root reservation and read limiter, and clears
  output/allocation cursors. No reader, list, child, or root may survive release;
  existing parent ownership guarantees this without a caller lease protocol.

Python owners keep the pool alive, including during cyclic GC. This implementation
is GIL-confined, including native acquire/release; it is not a free-threaded API.
The first-segment caches share a strict `capacity * words * 8` byte bound,
observable as `cached_buffer_bytes`. Native metadata is additional (up to two
capacity-sized caches of builder storage); live messages are not capacity limited.
Temporary overflow segments are freed, never retained by the pool.

`bench_allocation.py` checks all outputs semantically (including NaN and Data),
reports multisegment counts, and randomizes policy order across repeated rounds.
It compares sizes 64/256/1024/4096/16384, all reuse mechanisms, input-size presizing,
and a maximum-observed-size per-service policy trained on the first half of a
separate log (`0.rlog.zst` by default). The output records both input file SHA256
hashes, whether their contents overlap exactly, and the training subset count.
Trained timings include a service-to-factory dictionary lookup;
service names are assumed known by the caller. `from_dict` is an intentionally
controlled construction comparison, while `public kwargs` runs the actual
`Event.new_message(**record)` API. `empty` cases are allocator microbenchmarks.
Input-size presizing is not an oracle: reconstruction can require more allocation
than the original reachable message size.

Exploratory CPU14 measurements (before the final cache-bound correction) showed
~28.6 vs28.1 us/event for from_dict and ~24.7 vs24.1 us/event for field writes
with a 1024-word arena-reset pool, but ~0.49 vs0.33 us for empty messages.
The full-workload benefit is modest; do not extrapolate the empty-message gain.
CPU14 shares a physical core with CPU2, so final quiet measurements must replace
these estimates. Those earlier local trained-policy measurements used the first
half of the evaluation log itself; they are overlapping-training results, not a
held-out training result. Final commands below use a separate training segment.
Prior sequential sweeps had drift and are not evidence of gains.

## Approach 16: schema compilation and reflection

`SchemaParser.export_schemas()` emits a binary snapshot of every loaded schema,
including dependencies. `capnp.load_compiled(data, root_file_id, lazy=False)`
loads validated schema nodes without invoking the source compiler. `lazy=True`
defers file namespace population until declarations are accessed and exposes
unloaded names through `dir()`. `__dict__` only contains realized declarations.
Identical archive bytes share a native loader; archives are retained for process
lifetime like the ordinary global source parser. Pickle resolves imported struct
IDs through the archive too. Archives must be regenerated explicitly when source
schemas/dependencies change; this is not an automatic disk-cache invalidation API.

The source/compiled/lazy startup benchmark includes loading and first Event
construction, in fresh processes with warm filesystem caches. Artifact creation
is a separate mode including source compilation and archive file writes (no
fsync). It is not a cold-storage measurement. An early exploratory run measured
14.2ms source vs5.6ms eager archive setup, with a 380,680-byte archive. Later lazy
runs showed further improvement but were affected by shared-core contention;
use the quiet hyperfine results for final numbers. Steady-state serialization
should not improve from this approach: it uses the same loaded dynamic schemas.
Generated static C++ schema tables are a separate generated-bindings approach.

`reflection.ReflectionCache` caches serialized WebRTC reflection by retained
field/module declaration identity, not fresh schema-wrapper identity or schema
ID. Its `generate_struct(declaration)` returns independent mutable containers;
`encoded(declaration)` returns an immutable JSON string for callers already
sending JSON. Both are optional application adapters. Shared-dict timing is only
a lower bound with different mutability semantics. First cache construction still
pays the full reflection and encoding cost.

## Reproduction

Use the openpilot Python and set `PYTHONPATH` to this checkout plus openpilot.
Keep both CPU0 and its SMT sibling CPU12 quiet for final measurements:

```sh
export PYTHONPATH="$PWD:/home/batman/openpilot"
PY=/home/batman/openpilot/.venv/bin/python
$PY experiments/allocation/bench_compiled_workload.py prepare

taskset -c 0 $PY experiments/allocation/bench_allocation.py /tmp/pr3704_logs/1.rlog.zst --train /tmp/pr3704_logs/0.rlog.zst --repeat 9
taskset -c 0 $PY experiments/allocation/bench_allocation.py /tmp/opendbc_logs/ascent_1.rlog.zst --train /tmp/pr3704_logs/0.rlog.zst --repeat 9

taskset -c 0 $PY experiments/allocation/bench_schema.py --repeat 11
hyperfine --warmup 3 --runs 15 --export-json experiments/allocation/startup.json \
  -L mode source,compiled,lazy,create \
  'taskset -c 0 /home/batman/openpilot/.venv/bin/python experiments/allocation/bench_schema.py --child {mode}'

taskset -c 0 $PY benchmarks/bench_openpilot.py /tmp/pr3704_logs/1.rlog.zst
taskset -c 0 $PY experiments/allocation/bench_compiled_workload.py eager /tmp/pr3704_logs/1.rlog.zst
taskset -c 0 $PY experiments/allocation/bench_compiled_workload.py lazy /tmp/pr3704_logs/1.rlog.zst
```

Held-out allocation validation passed for all variants on the Ascent log, with
the earlier training fixed to Subaru segment1 (separate from Ascent). Final
measurements use Subaru segment0 for both evaluation logs. The unchanged 100-line workload passed all12
cases with lazy compiled schemas in a smoke run. Tests cover alias lifetimes,
threaded callers under the GIL, cyclic ownership, size validation, overflow,
failed construction, shared cache bounds, malformed archives, imported-type
pickle, and lazy nested structs/enums/constants. Independent reviewers examined
correctness/lifetimes and performance/benchmark design separately; the latter
requires final quiet timings before numerical claims are accepted.
