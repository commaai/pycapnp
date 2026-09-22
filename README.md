# pycapnp for openpilot

A serialization-only fork of [pycapnp](https://github.com/capnproto/pycapnp).
The `minimal` branch starts at upstream commit
`a0cb5cdf0673481f2f9850541f4d42b89698c476`, including the `from_dict` reference-cycle
fix in upstream PR #407.

The supported surface is based on openpilot at
`7f6f13997c3c9b8e27e1581583f61e3fcabc5151`, including its opendbc checkout:

- Explicit schema loading with `capnp.load()` and schema imports.
- Dynamic structs, lists, enums, unions, nested groups, and constants.
- Message construction, field access (including cached `_get_by_field` and
  `_set_by_field`), dictionaries, reader/builder copies, and pickling.
- Unpacked `to_bytes()`, `from_bytes()`, and `read_multiple_bytes()`, including
  traversal/nesting limits and readers that retain their underlying message.
- Schema reflection for cereal, CAN conversion, WebRTC, fuzzing, and replay tools.

Removed: RPC/capabilities, promises, KJ event loops, asyncio/network streams,
packed serialization, file-descriptor I/O, segment APIs, borrowed Data views,
custom allocators, orphans/resizable lists, AnyPointer wrappers, type registration,
the Python schema import hook, and the Cython code generator. Their examples,
tests, docs, dependencies, and unsupported-platform CI were removed too.
Also removed are generated per-schema `Reader`/`Builder` classes, synthetic
`.Union` enums, `_has_by_field`/`_init_by_field`, allocation-size overrides,
`from_bytes(builder=True)`, and `to_dict` ordering/base64 options. Incoming base64
Data values in `from_dict` remain supported. Unused schema reset/metadata helpers,
schema equality, `_which_str`, and legacy exception arguments were removed too.
`remove_import_hook()` remains a no-op for cereal/opendbc compatibility.

This is intentionally not a full upstream API replacement. The import and
package names remain `capnp` and `pycapnp`. It must replace the installed pycapnp,
not be installed alongside another distribution providing `capnp`.

## Build and test

Targets: CPython 3.12, Linux x86_64/aarch64, and macOS arm64. A C++17 compiler and
CMake are required to build the vendored library.

```sh
uv venv --python 3.12
uv pip install cython setuptools wheel pytest build
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -m pytest
.venv/bin/python -m build
```

The C++ library is vendored under [`vendor/capnproto`](vendor/capnproto), based on
Cap'n Proto 1.4.0. Every build compiles and statically links this copy; it does not
search for a system Cap'n Proto installation or download sources. The source
archive includes the vendored files, and wheels contain the compiled library.
Runtime schema parsing remains included, so cereal schemas need no generated
Python bindings. See the vendor README for provenance and the removed features.

The retained upstream tests cover message construction, schema loading,
reflection, binary fixtures, serialization, and exceptions. Added lifetime tests
check kwargs construction with GC disabled and readers surviving their input or
iterator. Optional integration tests use real openpilot schemas and exercise
messaging, CAN conversion, WebRTC reflection, LogReader, pickling, and replay:

```sh
# Run in an environment with openpilot's dependencies and this fork installed.
OPENPILOT_PATH=/path/to/openpilot python -m pytest test/test_openpilot.py
python -m pytest /path/to/openpilot/openpilot/cereal/messaging/tests \
  /path/to/openpilot/openpilot/tools/lib/tests/test_logreader.py
```

The [100-line openpilot benchmark](benchmarks/README.md) measures live messaging
and LogReader workloads. Its [initial baseline](benchmarks/baseline.md) records
the starting point for Python performance work.

See [LICENSE.md](LICENSE.md) for the upstream BSD license and attribution.
