# Openpilot capnp benchmark

`bench_openpilot.py` is 100 physical lines, including comments and blanks. It
measures steady-state Python binding work using actual messages from a local
rlog. Run it in an environment with openpilot and its dependencies available.

From this repository, after building the extension:

```sh
PYTHONPATH="$PWD:$HOME/openpilot" "$HOME/openpilot/.venv/bin/python" \
  benchmarks/bench_openpilot.py /path/to/rlog.zst
```

For installed-wheel comparisons, omit `$PWD` from `PYTHONPATH` and use the
candidate environment's Python. The output prints the imported capnp path and
Python version so you can check which implementation ran.

## Corpus

Use the same rlog and openpilot checkout for each comparison. The default takes
1,000 evenly spaced messages across the whole segment, plus the first message
of every event type present. This roughly preserves recorded service frequencies
while covering low-rate payloads such as `carParams`, text logs, and thumbnails.
It prints the normalized corpus SHA-256, byte size, and event counts. The log
must include `can`, `carState`, `carControl`, `modelV2`, `longitudinalPlan`, and
`carParams`; use an rlog rather than a decimated qlog. Nothing is downloaded.

The sample is reserialized outside timing, so this measures a repeatable set of
real payloads, not the original file's exact allocation/segment layout. The
benchmark does not add missing services or make up empty messages. Use multiple
cars/routes when evaluating an optimization that depends on payload shape.

## Workloads

| Case | Binding operations exercised |
| --- | --- |
| live read | Individual `from_bytes`, Event union dispatch, metadata, nested control/state fields, enum `.raw`, model/plan list iteration |
| field write+encode | `new_message`, recursive `init`, list allocation/indexing, attribute assignment, `to_bytes` |
| kwargs write+encode | Keyword/dictionary construction, recursive conversion, text/Data/enums, serialization |
| payload assignment | Assign existing struct/list readers into a new Event and serialize, as publishers do |
| CAN cached read/write | Actual pandad helpers using cached `_get_by_field`/`_set_by_field`, frame lists and Data bytes |
| LogReader parse+scan | Actual `LogReader.from_bytes`, bulk decoding, retained `CachedEventReader` objects, union dispatch and field reads |
| dict export | Verbose recursive `to_dict`, as time-series/export tools use |
| copy+encode | Reader-to-builder copying and serialization, as replay/edit/save tools use |
| reader pickle | Native capnp reader pickle/unpickle |
| LogReader pickle | Fresh LogReader construction plus cached-reader pickle/unpickle, as multiprocessing tools use |
| schema reflection | Actual WebRTC `generate_struct` traversal of the CarState schema |

The generic field writer and selected field reads are proxies for producer and
consumer work, not execution of the driving algorithms. The benchmark excludes
socket transport, file/network I/O, decompression, numpy conversion, and cold
schema imports. It does not model subscriber fan-out or report total onroad CPU.
Each case is reported separately; there is no equally weighted aggregate score.

## Measurement

`--messages` changes the evenly spaced sample count; `--repeat` defaults to five.
One batch warms the case and calibrates repetitions to approximately 0.2 seconds
per sample. Output is median microseconds per item with the minimum/maximum.
An item is one Event, one CAN batch (not one frame), or one schema traversal.
GC stays enabled; explicit collection happens before, outside, each timed sample.
Returned objects are released inside timing. Reusable reader fixtures use live
messaging's unlimited traversal setting; timed LogReader readers are recreated
on every invocation, so repeated benchmarking cannot exhaust their budgets.

For comparisons, keep the corpus hash, sample count, Python/openpilot versions,
and machine fixed. On Linux, `taskset -c 0` can pin the process to one CPU.
