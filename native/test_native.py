"""Native compiler regression tests; see README for build and integration commands."""

import gc
import importlib
import math
import os
from pathlib import Path
import struct
import subprocess
import sys

import capnp
import pytest


def fill(builder, values):
    for key, value in values.items():
        if isinstance(value, dict):
            fill(builder.init(key), value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            for child, fields in zip(builder.init(key, len(value)), value):
                fill(child, fields)
        else:
            setattr(builder, key, value)
    return builder


def equal(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def compare(actual, expected, schema):
    for name, value in expected.items():
        got, field = getattr(actual, name), schema.fields[name]
        kind = field.proto.slot.type.which() if field.proto.which() == "slot" else "struct"
        if isinstance(value, dict):
            compare(got, value, field.schema)
        elif isinstance(value, list):
            assert len(got) == len(value)
            if value and isinstance(value[0], dict):
                for g, v in zip(got, value):
                    compare(g, v, field.schema.elementType)
            elif field.proto.slot.type.list.elementType.which() == "enum":
                assert got == [field.schema.elementType.enumerants[x] for x in value]
            else:
                assert equal(got, value)
        elif kind == "enum":
            assert got == field.schema.enumerants[value]
        else:
            assert equal(got, value)


def primitive(t):
    k = t.which()
    if k == "bool":
        return True
    if k.startswith("int"):
        return -(2 ** (int(k[3:]) - 2))
    if k.startswith("uint"):
        return 2 ** (int(k[4:]) - 1)
    if k.startswith("float"):
        return 1.25
    return {"text": "héllo 🙂", "data": b"\x00\xffbinary"}.get(k)


def values(schema, depth=0):
    if depth > 10:
        return {}
    result, union = {}, False
    for name, f in schema.fields.items():
        p = f.proto
        if p.discriminantValue != 65535:
            if union:
                continue
            union = True
        if p.which() == "group":
            result[name] = values(f.schema, depth + 1)
            continue
        t = p.slot.type
        k = t.which()
        if k == "struct":
            result[name] = values(f.schema, depth + 1)
        elif k == "list":
            inner = t.list.elementType
            if inner.which() == "struct":
                result[name] = [values(f.schema.elementType, depth + 1)]
            elif inner.which() == "enum":
                result[name] = [next(iter(f.schema.elementType.enumerants))]
            elif inner.which() == "list":
                result[name] = []
            else:
                result[name] = [primitive(inner)]
        elif k == "enum":
            result[name] = next(iter(f.schema.enumerants))
        elif k != "anyPointer":
            result[name] = primitive(t)
    return result


@pytest.fixture(scope="module")
def fixture():
    # Missing native builds must fail, rather than silently skipping this suite.
    return importlib.import_module("native_fixture"), capnp.load(str(Path(__file__).with_name("test.capnp")))


def test_defaults_and_schema_evolution(fixture):
    mod, schema = fixture
    empty = mod.from_bytes(struct.pack("<IIQ", 0, 1, 0))
    assert (empty.signed, empty.unsigned, empty.truth, empty.fraction, empty.mode) == (-17, 42, True, -1.25, 1)
    assert empty.group.value == 7 and empty.child.value == 0
    assert empty.which() == "nothing" and empty.text == "" and empty.data == b""
    assert empty.nested == empty.children == empty.floats == []
    with schema.Root.from_bytes(mod.new().to_bytes()) as reader:
        assert reader.signed == -17 and reader.group.value == 7


def test_nested_roundtrip(fixture):
    mod, schema = fixture
    record = dict(
        signed=-(2**63),
        unsigned=2**64 - 1,
        truth=False,
        fraction=2.5,
        mode="first",
        child={"value": 1.5, "text": "child"},
        children=[{"value": 3.5}],
        floats=[-1.25, 2.5],
        modes=["second", "first"],
        nested=[[1, 65535], []],
        text="héllo 🙂",
        data=b"\x00\xff",
        group={"value": -9},
        object={"value": 7.5},
    )
    with schema.Root.from_bytes(schema.Root.new_message(**record).to_bytes()) as reader:
        expected = reader.to_dict()
    compare(mod.from_bytes(schema.Root.new_message(**record).to_bytes()), expected, schema.Root.schema)
    for wire in (mod.from_dict(record), fill(mod.new(), record).to_bytes()):
        with schema.Root.from_bytes(wire) as reader:
            assert equal(reader.to_dict(), expected)


def test_ownership_and_child_serialization(fixture):
    mod, schema = fixture
    root = mod.new()
    child = root.init("child")
    child.value = 7.5
    view = root.init("floats", 3)
    view[-1] = 2.5
    wire = root.to_bytes()
    del root
    gc.collect()
    child.value = 8.5
    assert list(view) == [0, 0, 2.5]
    with schema.Root.Child.from_bytes(child.to_bytes()) as reader:
        assert reader.value == 8.5
    read = mod.from_bytes(wire).view("floats")
    gc.collect()
    assert read[-1] == 2.5
    for index in (-4, 3):
        with pytest.raises(IndexError):
            read[index]
    with pytest.raises(ValueError):
        read[0] = 2
    reader_child = mod.from_bytes(wire).child
    assert reader_child.value == 7.5
    with pytest.raises(ValueError):
        reader_child.to_bytes()


def test_group_reinitialization(fixture):
    mod, schema = fixture
    for root in (mod.new(), schema.Root.new_message()):
        root.signed = 999
        root.group.value = 123
        root.group.nested.text = "old"
        group = root.init("group")
        assert group.value == 7 and group.nested.text == ""
        group.value = 456
        group.nested.text = "again"
        root.group = {}
        assert root.group.value == 456 and root.group.nested.text == "again"
        group = root.init("group")
        assert group.value == 7 and group.nested.text == ""
        assert root.signed == 999


def test_union_group_reinitialization(fixture):
    mod, schema = fixture
    for root in (mod.new(), schema.Root.new_message()):
        root.signed = 999
        root.group.value = 88
        root.number = 123
        group = root.init("grouped")
        assert group.value == 11 and group.text == "" and group.child.value == 0
        group.value = 45
        group.text = "old"
        group.init("child").value = 2.5
        root.grouped = {}
        assert root.grouped.value == 45 and root.grouped.text == "old" and root.grouped.child.value == 2.5
        group = root.init("grouped")
        assert group.value == 11 and group.text == "" and group.child.value == 0
        root.init("object").value = 3.5
        group = root.init("grouped")
        assert group.value == 11 and group.text == "" and group.child.value == 0
        assert root.which() == "grouped" and root.signed == 999 and root.group.value == 88


def test_union_and_reader_mutation(fixture):
    mod, _ = fixture
    root = mod.new()
    root.number = 8
    assert root.which() == "number" and root.number == 8
    root.init("object").value = 2.5
    assert root.which() == "object"
    with pytest.raises(ValueError):
        root.number
    reader = mod.from_bytes(root.to_bytes())
    with pytest.raises(ValueError):
        reader.signed = 2
    with pytest.raises(ValueError):
        reader.init("child")


@pytest.mark.parametrize(
    "record",
    [
        {"signed": 2**63},
        {"signed": -(2**63) - 1},
        {"unsigned": -1},
        {"unsigned": 2**64},
        {"truth": "true"},
        {"mode": "INVALID"},
        {"mode": -1},
        {"mode": 65536},
        {"unknown": 1},
        {1: 1},
        {"text": b"bytes"},
        {"data": "text"},
    ],
)
def test_invalid_inputs(fixture, record):
    mod, _ = fixture
    with pytest.raises((ValueError, TypeError, OverflowError)):
        mod.from_dict(record)


@pytest.mark.parametrize("bad", [b"", b"bad", b"\xff" * 8, struct.pack("<IIQ", 0, 1, 0xFFFFFFFFFFFFFFFF)])
def test_malformed_messages(fixture, bad):
    mod, _ = fixture
    before = sys.getrefcount(bad)
    for _ in range(100):
        with pytest.raises(ValueError):
            mod.from_bytes(bad).which()
    assert sys.getrefcount(bad) == before


def test_recursive_root_child(fixture):
    mod, schema = fixture
    root = mod.new()
    child = root.init("link")
    child.signed = 123
    with schema.Root.from_bytes(child.to_bytes()) as reader:
        assert reader.signed == 123
    record = {}
    for _ in range(200):
        record = {"link": record}
    with pytest.raises((ValueError, RecursionError)):
        mod.from_dict(record)


@pytest.mark.parametrize(
    "declaration",
    [
        'text @0 :Text = "unsupported";',
        'data @0 :Data = 0x"0102";',
        "list @0 :List(UInt16) = [1, 2];",
        "pointer @0 :AnyPointer;",
    ],
)
def test_unsupported_schemas_rejected(tmp_path, declaration):
    schema = tmp_path / "unsupported.capnp"
    schema.write_text("@0xd87cbe8e936c60ab; struct Root { " + declaration + " }")
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("generate.py")),
            "--schema",
            str(schema),
            "--root",
            "Root",
            "--output",
            str(tmp_path / "output"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, result.stdout
    assert "unsupported" in result.stderr.lower(), result.stderr


def test_bytes_subclass_cycle(fixture):
    mod, _ = fixture
    collected = []

    class OwnedBytes(bytes):
        def __del__(self):
            collected.append(True)

    data = OwnedBytes(mod.from_dict({"child": {"value": 2.5}}))
    reader = mod.from_bytes(data)
    data.reader = reader
    del data, reader
    gc.collect()
    assert collected == [True]


def test_multisegment(fixture):
    mod, schema = fixture
    wire = mod.from_dict({"data": b"x" * 100_000})
    assert mod.from_bytes(wire).data == b"x" * 100_000
    with schema.Root.from_bytes(wire) as reader:
        assert reader.data == b"x" * 100_000


@pytest.fixture(scope="module")
def event():
    if not os.environ.get("NATIVE_OPENPILOT"):
        pytest.skip("set NATIVE_OPENPILOT=1 to run the separately built openpilot integration")
    from openpilot.cereal import log

    return importlib.import_module("generated_native"), log.Event


def test_event_arms(event):
    mod, schema = event
    arms = [name for name, field in schema.schema.fields.items() if field.proto.discriminantValue != 65535]
    assert len(arms) >= 152
    for name in arms:
        f = schema.schema.fields[name]
        t = f.proto.slot.type
        if t.which() == "struct":
            payload = values(f.schema)
        elif t.which() == "list":
            payload = [values(f.schema.elementType)] if t.list.elementType.which() == "struct" else []
        else:
            payload = primitive(t)
        record = schema.new_message(**{name: payload}).to_dict()
        compare(mod.from_bytes(schema.new_message(**record).to_bytes()), record, schema.schema)
        for wire in (mod.from_dict(record), fill(mod.new(), record).to_bytes()):
            with schema.from_bytes(wire) as reader:
                assert equal(reader.to_dict(), record)


CASES = (
    "clear_list",
    "clear_outer_dict",
    "mutate_keys",
    "property_list",
    "list_view",
    "nested_lists",
    "raise_after_clear",
    "property_dict",
    "list_view_dict",
    "index_callback",
    "length_hint",
)


def run_mutation(case):
    import generated_native as mod
    from openpilot.cereal import log

    def parse(wire):
        with log.Event.from_bytes(wire) as reader:
            return reader.as_builder().as_reader()

    class Mutator:
        def __init__(self, action, fail=False):
            self.action = action
            self.fail = fail

        def __float__(self):
            self.action()
            if self.fail:
                raise RuntimeError("conversion failed")
            return 1.5

    if case == "clear_list":
        values = []
        values.extend([Mutator(values.clear), 2.5])
        wire = mod.from_dict({"longitudinalPlan": {"speeds": values}})
        assert list(parse(wire).longitudinalPlan.speeds) == [1.5, 2.5]
    elif case == "clear_outer_dict":
        record = {}
        record.update(
            {"longitudinalPlan": {"speeds": [Mutator(record.clear), 2.5], "shouldStop": True}, "valid": False}
        )
        wire = mod.from_dict(record)
        reader = parse(wire)
        assert (
            list(reader.longitudinalPlan.speeds) == [1.5, 2.5]
            and reader.longitudinalPlan.shouldStop
            and not reader.valid
        )
    elif case == "mutate_keys":
        child = {}

        def mutate():
            child.clear()
            child.update({str(i): i for i in range(1000)})

        child.update({"speeds": [Mutator(mutate)], "shouldStop": True})
        wire = mod.from_dict({"longitudinalPlan": child})
        assert parse(wire).longitudinalPlan.shouldStop
    elif case == "property_list":
        event = mod.new()
        plan = event.init("longitudinalPlan")
        values = []
        values.extend([Mutator(values.clear), 2.5])
        plan.speeds = values
        assert plan.speeds == [1.5, 2.5]
    elif case == "list_view":
        event = mod.new()
        view = event.init("longitudinalPlan").init("speeds", 2)
        # Replacement can orphan the old list but cannot free its arena while a view exists.
        view[0] = Mutator(lambda: event.init("carState"))
        assert view[0] == 1.5
    elif case == "nested_lists":
        # A struct-list item can clear the outer collection containing the live item.
        event = mod.new()

        class Iterable:
            def __iter__(self):
                leads.clear()
                return iter([1.0, 2.0])

        leads = [{"x": Iterable()}]
        wire = mod.from_dict({"modelV2": {"leadsV3": leads}})
        assert list(parse(wire).modelV2.leadsV3[0].x) == [1.0, 2.0]
    elif case == "property_dict":
        event = mod.new()
        child = {}
        child.update({"speeds": [Mutator(child.clear), 2.5], "shouldStop": True})
        event.longitudinalPlan = child
        assert event.longitudinalPlan.speeds == [1.5, 2.5] and event.longitudinalPlan.shouldStop
    elif case == "list_view_dict":
        view = mod.new().init("modelV2").init("leadsV3", 1)
        child = {}
        child.update({"x": [Mutator(child.clear), 2.5], "prob": 0.5})
        view[0] = child
        assert view[0].x == [1.5, 2.5] and view[0].prob == 0.5
    elif case == "index_callback":
        root = {}

        class Index:
            def __index__(self):
                root.clear()
                return 7

        root.update({"longitudinalPlan": {"speeds": [Index(), 2.5]}, "valid": False})
        reader = parse(mod.from_dict(root))
        assert list(reader.longitudinalPlan.speeds) == [7.0, 2.5] and not reader.valid
    elif case == "length_hint":
        root = {}

        class Values:
            def __init__(self):
                self.index = 0

            def __iter__(self):
                return self

            def __length_hint__(self):
                root.clear()
                return 2

            def __next__(self):
                self.index += 1
                if self.index > 2:
                    raise StopIteration
                return float(self.index)

        root.update({"longitudinalPlan": {"speeds": Values()}, "valid": False})
        reader = parse(mod.from_dict(root))
        assert list(reader.longitudinalPlan.speeds) == [1.0, 2.0] and not reader.valid
    elif case == "raise_after_clear":
        values = []
        values.extend([Mutator(values.clear, True), 2.5])
        try:
            mod.from_dict({"longitudinalPlan": {"speeds": values}})
        except RuntimeError as exc:
            assert str(exc) == "conversion failed"
        else:
            raise AssertionError("missing conversion exception")


@pytest.mark.parametrize("case", CASES)
def test_mutation_callback(event, case):
    subprocess.run([sys.executable, str(Path(__file__).resolve()), case], check=True, timeout=30)


if __name__ == "__main__":
    run_mutation(sys.argv[1])
