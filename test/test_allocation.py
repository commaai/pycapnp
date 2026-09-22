import gc
import pickle
from pathlib import Path

import capnp
import pytest


@pytest.fixture
def schema():
    return capnp.load(str(Path(__file__).with_name('addressbook.capnp')))


@pytest.mark.parametrize("recycle", [False, True])
@pytest.mark.parametrize("reset", [False, True])
def test_pool_aliases_and_pool_lifetime(schema, recycle, reset):
    pool = capnp.BuilderPool(64, 1, recycle_builder=recycle, reset_arena=reset)
    first = pool.new_message(schema.AddressBook, people=[{'id': 42, 'name': 'first'}])
    child = first.people[0]
    reader = first.as_reader()
    people = first.people
    del first
    gc.collect()
    for i in range(100):
        msg = pool.new_message(schema.AddressBook, people=[{'id': i, 'name': 'next'}])
        assert msg.people[0].id == i
    del pool, msg
    gc.collect()
    assert child.id == reader.people[0].id == 42
    assert child.name == reader.people[0].name == people[0].name == 'first'


@pytest.mark.parametrize('words', [1, 16, 1024, 8192])
@pytest.mark.parametrize('capacity', [0, 1, 3])
@pytest.mark.parametrize('recycle', [False, True])
@pytest.mark.parametrize('reset', [False, True])
def test_pool_zeroing_and_overflow(schema, words, capacity, recycle, reset):
    pool = capnp.BuilderPool(words, capacity, recycle_builder=recycle, reset_arena=reset)
    for i in range(20):
        msg = pool.new_message(schema.AddressBook, people=[{'name': 'x' * 16384, 'id': i}])
        encoded = msg.to_bytes()
        with schema.AddressBook.from_bytes(encoded) as reader:
            assert reader.people[0].name == 'x' * 16384
        del msg
        empty = pool.new_message(schema.AddressBook)
        assert len(empty.people) == 0
        del empty


@pytest.mark.parametrize('value', [0, -1, 2**29, 2**29 + 1])
def test_invalid_segment_size(value):
    with pytest.raises(ValueError):
        capnp._MallocMessageBuilder(value)
    with pytest.raises(ValueError):
        capnp.BuilderPool(value)


def test_presizing(schema):
    owner = capnp._MallocMessageBuilder(4)
    msg = owner.init_root(schema.AddressBook)
    msg.from_dict({'people': [{'name': 'bob'}]})
    with schema.AddressBook.from_bytes(msg.to_bytes()) as result:
        assert result.people[0].name == 'bob'


def test_schema_archive(schema):
    data = schema._parser.export_schemas()
    compiled = capnp.load_compiled(data, schema.schema.node.id)
    expected = schema.AddressBook.new_message(people=[{'id': 11, 'name': 'alice'}])
    actual = compiled.AddressBook.new_message(people=[{'id': 11, 'name': 'alice'}])
    assert actual.to_bytes() == expected.to_bytes()
    assert actual.to_dict() == expected.to_dict()
    actual.clear_write_flag()
    assert pickle.loads(pickle.dumps(actual)).to_dict() == expected.to_dict()
    field = compiled.AddressBook.schema.fields['people']
    del compiled
    gc.collect()
    assert field.schema.elementType.node.displayName
    assert actual.people[0].name == 'alice'


@pytest.mark.parametrize('data', [b'', b'x', bytes(8), bytes(16)])
def test_invalid_schema_archive(data):
    with pytest.raises(capnp.KjException):
        capnp.load_compiled(data, 1)


@pytest.mark.parametrize('value', [0.5, 1.5, "32"])
def test_noninteger_sizes(value):
    with pytest.raises(TypeError):
        capnp._MallocMessageBuilder(value)
    with pytest.raises(TypeError):
        capnp.BuilderPool(value)
    with pytest.raises(TypeError):
        capnp.BuilderPool(32, value)


@pytest.mark.parametrize("recycle", [False, True])
@pytest.mark.parametrize("reset", [False, True])
def test_pool_failed_construction(schema, recycle, reset):
    pool = capnp.BuilderPool(32, 1, recycle_builder=recycle, reset_arena=reset)
    with pytest.raises(Exception):
        pool.new_message(schema.AddressBook, people=[{'name': 'large' * 1000}], nonexistent=5)
    assert len(pool.new_message(schema.AddressBook).people) == 0


@pytest.mark.parametrize("lazy", [False, True])
def test_compiled_dependency_pickle(tmp_path, lazy):
    (tmp_path / 'dep.capnp').write_text('@0xdffffffffffffffe; struct Child { value @0 :Int32; }')
    root = tmp_path / 'root.capnp'
    root.write_text('@0xdfffffffffffffff; using D = import "dep.capnp"; struct Root { child @0 :D.Child; }')
    source = capnp.SchemaParser().load(str(root))
    compiled = capnp.load_compiled(source._parser.export_schemas(), source.schema.node.id, lazy=lazy)
    child = compiled.Root.new_message(child={'value': 73}).child.as_reader()
    assert pickle.loads(pickle.dumps(child)).value == 73


def test_lazy_compiled(schema):
    compiled = capnp.load_compiled(schema._parser.export_schemas(), schema.schema.node.id, lazy=True)
    assert 'AddressBook' in dir(compiled)
    assert 'AddressBook' not in compiled.__dict__
    first = compiled.AddressBook
    assert first is compiled.AddressBook
    msg = first.new_message(people=[{'name': 'lazy'}])
    assert msg.people[0].name == 'lazy'
    assert pickle.loads(pickle.dumps(msg.as_reader())).people[0].name == 'lazy'
    with pytest.raises(AttributeError):
        _ = compiled.nonexistent


def test_pool_subclass_cycle(schema):
    class CustomPool(capnp.BuilderPool):
        pass
    for _ in range(100):
        pool = CustomPool(32, 1, recycle_builder=True)
        pool.message = pool.new_message(schema.AddressBook)
        del pool
    gc.collect()


def test_lazy_nested_enum_constant(tmp_path):
    source = tmp_path / 'lazy.capnp'
    source.write_text('@0xcfffffffffffffff; const n :UInt32 = 42; enum E { a @0; b @1; } struct S { struct Child { x @0 :Int32; } child @0 :Child; }')
    parsed = capnp.SchemaParser().load(str(source))
    compiled = capnp.load_compiled(parsed._parser.export_schemas(), parsed.schema.node.id, lazy=True)
    assert compiled.n == 42
    assert compiled.E.b == 1
    assert compiled.S.Child.new_message(x=3).x == 3


def test_pool_threads_and_retained_aliases(schema):
    from concurrent.futures import ThreadPoolExecutor
    pool = capnp.BuilderPool(64, 4, recycle_builder=True, reset_arena=True)
    def work(seed, pool=pool):
        retained = []
        for i in range(100):
            value = seed * 1000 + i
            msg = pool.new_message(schema.AddressBook, people=[{'id': value, 'name': str(value)}])
            retained.append((msg.people, value))
        return retained
    with ThreadPoolExecutor(4) as executor:
        retained = sum(executor.map(work, range(4)), [])
    del work, pool
    gc.collect()
    for people, value in retained:
        assert people[0].id == value
        assert people[0].name == str(value)


def test_pool_combined_cache_bound(schema):
    pool = capnp.BuilderPool(64, 1, recycle_builder=True, reset_arena=True)
    first = pool.new_message(schema.AddressBook, people=[{'id': 1}])
    overflow = pool.new_message(schema.AddressBook, people=[{'name': 'x' * 10000}])
    del overflow
    assert pool.cached_buffer_bytes == 64 * 8
    del first
    assert pool.cached_buffer_bytes == 64 * 8
    msg = pool.new_message(schema.AddressBook)
    assert pool.cached_buffer_bytes == 0
    assert len(msg.people) == 0


def test_archive_loader_shared(schema):
    data = schema._parser.export_schemas()
    first = capnp.load_compiled(data, schema.schema.node.id)
    second = capnp.load_compiled(bytes(bytearray(data)), schema.schema.node.id, lazy=True)
    assert first._parser is second._parser
    assert first.AddressBook.new_message(people=[{'name': 'shared'}]).people[0].name == 'shared'
