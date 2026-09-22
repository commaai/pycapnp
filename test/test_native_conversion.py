"""Correctness and lifetime boundaries of native recursive conversion."""

import gc
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
