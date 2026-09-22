"""Regression coverage for compiler folding of generated comparison helpers."""

import operator
from pathlib import Path

import capnp
import pytest


@pytest.mark.parametrize("compare", [operator.eq, operator.ne, operator.lt, operator.le, operator.gt, operator.ge])
def test_enum_comparisons(compare):
    schema = capnp.load(str(Path(__file__).with_name("addressbook.capnp")))
    builder = schema.Person.new_message()
    phones = builder.init("phones", 3)
    names = ["mobile", "home", "work"]
    for phone, name in zip(phones, names):
        phone.type = name
    for i, left in enumerate(phones):
        for j, right in enumerate(phones):
            assert compare(left.type, right.type) == compare(i, j)
            assert compare(left.type, j) == compare(i, j)
            assert compare(i, right.type) == compare(i, j)
            assert compare(left.type, names[j]) == compare(names[i], names[j])
