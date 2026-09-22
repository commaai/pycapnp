# Schema-generated bindings (#6 and #10)

This experiment generates **263 branded structs / 2,209 fields** reachable from openpilot's Event schema. It produces Cython extension classes and direct CPython extension types around the same specialized native accessor/construction core. Each getter uses the field's compile-time type, offset, default mask and discriminant. There is no DynamicValue conversion or runtime schema lookup on reads. Field-name lookup remains in native dictionary construction, using per-struct hash tables.

These are library-backed accessors: FlatArrayMessageReader and Cap'n Proto's StructReader/PointerReader/ListReader perform segment, pointer and nesting/traversal validation. This is deliberately separate from the direct-wire codec experiment. The generated accessors use the same layout primitives as stock generated C++ getters, without requiring the removed generic compiler/code-generator machinery in the shipped runtime.

## API and coverage

Both modules offer:

- `from_bytes(bytes)`: typed immutable Event; aligned exact builtin bytes are pinned (subclasses are copied to avoid hidden GC cycles), with an aligned-copy fallback.
- `new()`: mutable Event, typed scalar/struct/list properties, `init(name[, size])`, `which()`, `to_bytes()`.
- `from_dict(dict)`: native recursive dictionary construction directly to wire bytes.
- `view(name)`: lazy list view with length/index/iteration; builder views support per-element assignment. Struct list elements retain ownership and mutability.
- `project(bytes)`: the bulk team's fused native projection, separately benchmarked with matching returned values.

Field properties eagerly materialize lists; `.view()` is the explicit sparse-access alternative. Enums are integers. This is an adapted API, not a drop-in replacement: reflection, pickle, context managers, list slicing, arbitrary runtime schema loading, and builder/reader assignment conversion are outside this experiment. The class factory exposes Event roots; nested types are reached through fields. Generated Cython classes created directly contain no message and safely reject access.

Every current Event-reachable field is generated, including nested groups, generic Map(Text, Text) versus Map(Text, Data), primitive/struct/nested lists, union guards and scalar XOR defaults. The generator rejects unsupported complex generic bindings and explicit pointer defaults instead of silently misreading them. Future schemas using these need generator work. Static Python-type/name caches currently assume one interpreter and the GIL.

## Build and reproduce

Use CPython 3.12 with Cython/setuptools for building, and the openpilot environment for schema generation/tests. The command directory below is `experiments/generated`; `PYTHONPATH` must include the chosen built pycapnp checkout and openpilot checkout. When generating from an unbuilt checkout, run generation from `/tmp` or another directory so an unbuilt local `capnp` package does not shadow the installed binding.

```bash
python generate.py
python generate_consumer.py coverage.json generated_consumer.h
python setup.py build_ext --inplace -j2
python checks.py
python reentrant.py
python benchmark.py /path/to/log.rlog.zst --repeat 5
python ablate.py /path/to/log.rlog.zst
python startup.py /path/to/log.rlog.zst
```

`setup.py` builds the vendored static Cap'n Proto library if a root-build archive is absent. Both extensions declare all native/generated header dependencies. Generated C++/Cython outputs and binaries are ignored; generators, runtime, coverage manifest and measurements are committed. The original 100-line benchmark is unchanged.

## Validation and measurement interpretation

`checks.py` constructs synthetic records for all **152 Event union arms**, checking both modules against the existing binding for reads, dict-to-wire construction, and attribute/init construction. It also checks missing-section defaults (old smaller root layout), integer range/type errors, inactive unions, malformed inputs, malformed-input reference counts, large multi-segment payloads, child serialization, primitive list mutation/index bounds, and children surviving roots/input destruction. Real-log parity checks every field represented in the sampled records, including branded maps and list enums. Generated field count is not a claim that every possible field value or schema evolution has been exhaustively tested.

`benchmark.py` preserves the existing evenly sampled 1,000 messages plus first event per type and prints the same corpus digest. It compares identical selected field values, native dict construction, and the original Python field/init construction loop. It separately reports hot types, CAN frame traversal versus envelope-only access, and sparse/full-list access. Generated reads retain the library's default traversal limit; the existing messaging reader uses its unlimited setting. Generated list materialization/enum representation are explicitly adapted. These are LogReader-derived message workloads, not a replacement of LogReader itself.

`ablate.py` uses fresh processes and the same binary/layout, sanitizes inherited mode flags, and independently disables inline wrapper handles, borrowed input bytes, and cached union names. The heap-handle variant retains the same wrapper storage footprint, so it measures the extra allocation rather than a separately optimized smaller wrapper design. `startup.py` alternates fresh subprocesses including interpreter startup, module/schema initialization, fixture read and first CarState read/write; fixture preparation is excluded. Compile/code-generation time is separate.

The Cython/native comparison isolates Python frontend overhead over an identical typed native core. It does **not** show that rewriting an equally optimized Cython implementation in C++ inherently improves speed. The fused projection is separately labeled and preserves boxed output values, so compiled-consumer benefits can be measured independently.

## Review iterations

A correctness-focused reviewer found and prompted fixes for uninitialized Cython class crashes, factory allocation propagation, hardcoded root size, length narrowing, pointer-owner construction leakage, and child serialization. They independently reran all 152-arm checks and additional list-child lifetimes. A performance-focused reviewer prompted constant-time factories, interned union names, inline handles, attribute-construction timing, per-type/sparse-list comparisons, and clean ablation environments. Sparse access is supported by a separately measured lazy view; eager access remains available for complete materialization.

The final report records measured outcomes rather than asserting an unprovable absolute performance ceiling. Remaining API exclusions above are intentional experiment boundaries, not claims of production replacement readiness.

Main-agent adversarial review additionally found reentrant numeric callbacks could invalidate borrowed input containers. Writers now snapshot lists/iterables into immutable tuples and each dictionary into a native vector of retained key/value references before conversion. The subprocess reentrancy suite covers clearing lists, outer dictionaries, dictionary key changes, property and list-view assignment, nested iterables, and exceptions after mutation. Final timings include this safety fix.
