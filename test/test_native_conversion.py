"""Correctness and lifetime boundaries of native recursive conversion."""

import gc
import struct
import sys
from pathlib import Path

import capnp
import pytest


@pytest.fixture
def schema():
    return capnp.load(str(Path(__file__).with_name("all_types.capnp")))


def test_union_value_is_snapshot(schema):
    msg = schema.UnionAllTypes.new_message(unionStructField1={"textField": "old"})
    which = msg.which
    raw = which.raw
    msg.init("unionStructField2")
    del msg
    gc.collect()
    assert which() == "unionStructField1"
    assert which == "unionStructField1"
    assert which.raw == raw
    assert str(which) == "unionStructField1"


def test_nested_tuple_kwargs(schema):
    msg = schema.TestAllTypes.new_message(int32List=(1, 2, 3))
    assert msg.to_dict()["int32List"] == [1, 2, 3]


def test_native_conversion_reader_builder_equal(schema):
    msg = schema.TestAllTypes.new_message(textField="hé\0llo", dataField=b"\0\xff", int32List=[-1, 0, 4])
    for verbose in (False,):
        expected = msg.to_dict(verbose)
        with schema.TestAllTypes.from_bytes(msg.to_bytes()) as reader:
            assert reader.to_dict(verbose) == expected
        rebuilt = schema.TestAllTypes.new_message(**expected)
        assert rebuilt.to_dict(verbose) == expected
        msg.clear_write_flag()


def test_invalid_nested_assignment_is_python_exception(schema):
    with pytest.raises(Exception):
        schema.TestAllTypes.new_message(int32Field={"oops": 1})


def test_recursive_input_is_guarded(schema):
    values = {}
    values["structField"] = values
    with pytest.raises(RecursionError):
        schema.TestAllTypes.new_message(**values)


def test_recursive_verbose_defaults_are_guarded(schema):
    with pytest.raises(RecursionError):
        schema.TestAllTypes.new_message().to_dict(verbose=True)


def test_iterator_pins_message_and_preserves_mutability(schema):
    msg = schema.TestAllTypes.new_message(structList=[{"textField": "one"}, {"textField": "two"}])
    iterator = iter(msg.structList)
    del msg
    gc.collect()
    one = next(iterator)
    one.textField = "changed"
    assert one.textField == "changed"
    two = next(iterator)
    with pytest.raises(StopIteration):
        next(iterator)
    with pytest.raises(StopIteration):
        next(iterator)
    del iterator
    gc.collect()
    assert two.textField == "two"


def test_empty_and_numeric_iterators(schema):
    msg = schema.TestAllTypes.new_message(int32List=[1, 2, 3])
    assert list(msg.int32List) == [1, 2, 3]
    assert list(msg.as_reader().int32List) == [1, 2, 3]
    assert list(msg.textList) == []


def test_attribute_lookup_preserves_methods_and_missing_errors(schema):
    msg = schema.TestAllTypes.new_message(int32Field=7)
    for value in (msg, msg.as_reader()):
        assert value.int32Field == 7
        assert callable(value.to_dict)
        assert value.schema.fieldnames
        with pytest.raises(AttributeError):
            value.notAField


@pytest.mark.parametrize("base", [capnp._DynamicStructReader, capnp._DynamicStructBuilder])
def test_subclass_attribute_dispatch(base):
    class Child(base):
        @property
        def prop(self):
            return 123

        def method(self):
            return 456

        def __getattr__(self, name):
            return "child:" + name

    child = Child()
    assert child.prop == 123 and child.method() == 456 and child.missing == "child:missing"

    class Raises(base):
        @property
        def prop(self):
            raise ValueError("expected")

    with pytest.raises(ValueError, match="expected"):
        Raises().prop


def test_custom_parser_same_id_isolation(tmp_path):
    a, b = tmp_path / "a.capnp", tmp_path / "b.capnp"
    a.write_text("@0xabcdefabcdefabc1; struct S @0xabcdefabcdefabc2 {union{ a @0 :Int64; aa @1 :Text; }}")
    b.write_text("@0xabcdefabcdefabc1; struct S @0xabcdefabcdefabc2 {union{ b @0 :Int64; bb @1 :Text; }}")
    first, second = capnp.load(str(a)), capnp.SchemaParser().load(str(b))
    for _ in range(100):
        x, y = first.S.new_message(a=1), second.S.new_message(b=2)
        assert (x.which(), y.which()) == ("a", "b")
        assert x.to_dict() == {"a": 1} and y.to_dict() == {"b": 2}


@pytest.mark.parametrize(
    "field,values",
    [
        ("boolList", [True, False]),
        ("int8List", [-128, 127]),
        ("uInt64List", [0, 2**64 - 1]),
        ("int64List", [-(2**63), 2**63 - 1]),
        ("float64List", [float("inf"), -float("inf"), -0.0]),
    ],
)
def test_primitive_boundaries_and_attribute_refcounts(schema, field, values):
    msg = schema.TestAllTypes.new_message(**{field: values})
    assert msg.to_dict()[field] == values
    before = sys.getrefcount(msg)
    for _ in range(1000):
        msg.to_dict, msg.schema, msg.int32Field
    assert sys.getrefcount(msg) == before


def test_malformed_union_propagates(schema):
    # Previously to_dict accidentally swallowed malformed active union fields.
    data = struct.pack("<IIQQQ", 0, 3, (1 << 32) | (1 << 48), 0, 7)
    with schema.UnionAllTypes.from_bytes(data) as msg:
        with pytest.raises(capnp.KjException):
            msg.to_dict()


def test_primitive_list_schema_evolution(tmp_path):
    old, new = tmp_path / "old.capnp", tmp_path / "new.capnp"
    old.write_text("@0xcdefabcdefabcdef; struct S { values @0 :List(UInt32); }")
    new.write_text(
        "@0xcdefabcdefabcdef; struct S { values @0 :List(Entry); } struct Entry { x @0 :UInt32; y @1 :UInt32; }"
    )
    original = capnp.SchemaParser().load(str(old))
    evolved = capnp.SchemaParser().load(str(new))
    data = evolved.S.new_message(values=[{"x": 1, "y": 99}, {"x": 2, "y": 100}]).to_bytes()
    with original.S.from_bytes(data) as msg:
        assert msg.to_dict() == {"values": [1, 2]}
    malformed = struct.pack("<IIQQ", 0, 2, 1 << 48, 1 | (4 << 32) | (5 << 35))
    with original.S.from_bytes(malformed) as msg:
        with pytest.raises(capnp.KjException):
            msg.to_dict()


def test_iterator_retries_malformed_element(tmp_path):
    path = tmp_path / "texts.capnp"
    path.write_text("@0xfaabcdefabcdefab; struct S { values @0 :List(Text); }")
    schema = capnp.load(str(path))
    data = struct.pack("<IIQQQQ", 0, 4, 1 << 48, 1 | (6 << 32) | (2 << 35), 7, 0)
    with schema.S.from_bytes(data) as msg:
        values = iter(msg.values)
        for _ in range(2):
            with pytest.raises(capnp.KjException):
                next(values)


@pytest.mark.parametrize(
    "field,values",
    [
        ("float32List", [1.0, 2, 3.0]),
        ("int32List", [1, 2.0, 3]),
        ("float32List", [1e300, float("inf"), -0.0]),
    ],
)
def test_primitive_import_coercion_fallback(schema, field, values):
    msg = schema.TestAllTypes.new_message(**{field: values})
    expected = schema.TestAllTypes.new_message()
    items = expected.init(field, len(values))
    for i, value in enumerate(values):
        items[i] = value
    assert msg.to_dict() == expected.to_dict()


@pytest.mark.parametrize(
    "field,values",
    [
        ("int8List", [1, 128]),
        ("uInt64List", [1, -1]),
        ("uInt64List", [1, 2**65]),
        ("int64List", [1, -(2**65)]),
        ("boolList", [True, 1]),
        ("float64List", [1.0, "bad"]),
    ],
)
def test_primitive_import_error_and_partial_write(schema, field, values):
    msg = schema.TestAllTypes.new_message()
    with pytest.raises(Exception) as fast:
        setattr(msg, field, values)
    expected = schema.TestAllTypes.new_message()
    items = expected.init(field, len(values))
    with pytest.raises(type(fast.value)) as slow:
        for i, value in enumerate(values):
            items[i] = value
    assert str(fast.value).split("\nstack:")[0] == str(slow.value).split("\nstack:")[0]
    assert list(getattr(msg, field)) == list(items)
