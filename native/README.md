# Native Python bindings

Generate a CPython extension specialized to a Cap'n Proto root struct. Python
attributes call typed native accessors backed by the vendored libcapnp. The
existing `capnp` package is unchanged; this is an opt-in API, not a drop-in replacement.

The generator needs pycapnp to read schemas. Building the generated extension
needs setuptools, CMake and a C++17 compiler, but not Cython. The resulting module
does not import pycapnp or openpilot at runtime. Tested with CPython 3.12; the
extension requires the GIL and main interpreter.

## Build

From a checkout with pycapnp installed in the active Python environment:

```sh
cd native
python generate.py --schema /path/to/openpilot/openpilot/cereal/log.capnp \
  -I /path/to/openpilot/opendbc_repo/opendbc/car
python setup.py build_ext --inplace
```

This writes generated sources into `native/build` and builds `generated_native`
in the current directory. Add that directory to `PYTHONPATH` when importing from
elsewhere. The build uses this checkout's vendored C++ library, not a system copy.

For other schemas, select `--root RootName` (default `Event`). Nested root names
are dot-qualified. `--module name` and `--output directory` select another module
and source directory; pass the same choices to the build via
`CAPNP_NATIVE_MODULE=name CAPNP_NATIVE_OUTPUT=directory`.

Regenerate after changing schemas, `generate.py`, or `runtime.h`, then rebuild.
Generated sources and compiled libraries are not committed.

## Use

```python
import generated_native as native

wire = native.from_dict({"carState": {"vEgo": 12.0}})
event = native.from_bytes(wire)
assert event.which() == "carState"
assert event.carState.vEgo == 12.0

builder = native.new()
builder.init("carState").vEgo = 15.0
wire = builder.to_bytes()
```

- `from_bytes(bytes)` returns an immutable reader. Children retain their owner.
- `from_dict(dict)` constructs and serializes in native code, returning bytes.
- `new()` creates a mutable root. Attributes, `init(name[, size])` and list views
  support mutation. `to_bytes()` serializes a builder's own struct.
- List attributes return Python lists. `view(name)` provides lazy indexing and
  iteration; builder views also allow assignment. There is no slicing API.
- Enums read as integers; setters accept an integer or enumerant name.

The compiler handles the current openpilot Event graph, including branded maps,
groups, unions, scalar defaults and nested lists. It rejects unsupported pointer
defaults, generic bindings, pointer types and method-name collisions. Reflection,
pickle, packed messages and dynamic schema loading are not part of this API.
Construction is bounded to 128 nested conversion levels. Library reader limits
apply, and validation is lazy rather than a complete up-front wire check.

## Validate

The small fixture exercises the compiler without an openpilot checkout:

```sh
python generate.py --schema test.capnp --root Root \
  --module native_fixture --output build-fixture
CAPNP_NATIVE_OUTPUT=build-fixture CAPNP_NATIVE_MODULE=native_fixture \
  python setup.py build_ext --inplace
python -m pytest test_native.py
```

After also building the Event module, run the openpilot integration cases with
the openpilot checkout and its dependencies on the import path:

```sh
NATIVE_OPENPILOT=1 python -m pytest test_native.py
python benchmark.py /path/to/segment.rlog.zst --repeat 5
```

Tests cover ownership, defaults, groups, recursive schemas, malformed inputs and
callback mutation. Integration tests exercise every Event union arm. The benchmark
checks matching outputs before timing selected-field reads and dict construction,
using 1,000 evenly sampled messages plus the first event of each type. It excludes
I/O/decompression, alternates case order, and reports raw samples with a corpus hash.
These are message-operation measurements, not a whole-openpilot speedup.

### Measured result

On CPython 3.12/x86, against the original minimal binding (two vehicle logs):

| Operation | Primary log | Held-out log |
|---|---:|---:|
| Sampled reads | 8.55× faster | 9.27× faster |
| Dict construction + encoding | 9.13× faster | 9.78× faster |

[Raw samples and source identities](benchmark-results.json). These numbers use the
adapted API above. The rebuilt compiler passed 41 fixture/integration tests, including
all 152 Event arms and 11 callback-mutation subprocess cases.
