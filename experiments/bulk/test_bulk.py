import gc
import math

import capnp
import pytest
from capnp.lib.capnp import _bulk_can_read, _bulk_can_write, _bulk_float_read, _bulk_float_write, _bulk_float_buffer_read, _bulk_read_fields, _bulk_float_view
from openpilot.cereal import log, messaging
from openpilot.selfdrive.pandad.pandad_api_impl import can_capnp_to_list


@pytest.mark.parametrize('kind', ['can', 'sendcan'])
@pytest.mark.parametrize('frames', [[], [(0, b'', 0)], [(2**32 - 1, bytes(range(64)), 255)]])
def test_can(kind, frames):
    event = log.Event.new_message(logMonoTime=123, valid=True)
    wire = _bulk_can_write(event, frames, kind).to_bytes()
    reader = messaging.log_from_bytes(wire)
    assert _bulk_can_read(reader, kind) == (123, frames)
    assert can_capnp_to_list([wire], kind) == [(123, frames)]
    copied = _bulk_can_read(reader, kind)
    del event, reader, wire
    gc.collect()
    assert copied == (123, frames)


def test_can_errors():
    event = log.Event.new_message()
    with pytest.raises(ValueError):
        _bulk_can_write(event, [], 'carState')
    with pytest.raises((OverflowError, capnp.KjException)):
        _bulk_can_write(event, [(2**64, b'', 0)])
    event.init('carState')
    with pytest.raises(capnp.KjException):
        _bulk_can_read(event.as_reader())


@pytest.fixture
def schema(tmp_path):
    path = tmp_path / 'floats.capnp'
    path.write_text('@0xeed61b537e7f85dc; struct Floats { f32 @0 :List(Float32); f64 @1 :List(Float64); ints @2 :List(Int32); } struct Cell { value @0 :Float32; padding @1 :UInt64; } struct Expanded { f32 @0 :List(Cell); } struct FakeFrame { address @0 :UInt32; dat @1 :Data; src @2 :UInt8; } struct FakeEvent { can @0 :List(FakeFrame); logMonoTime @1 :UInt64; }')
    return capnp.SchemaParser().load(str(path))


@pytest.mark.parametrize('field', ['f32', 'f64'])
@pytest.mark.parametrize('values', [[], [1.5, -2.25, float('inf'), float('-inf'), float('nan')]])
def test_float_copy(schema, field, values):
    event = schema.Floats.new_message()
    target = event.init(field, len(values))
    _bulk_float_write(target, iter(values))
    reader = event.as_reader()
    copied = _bulk_float_read(getattr(reader, field))
    assert all(a == b or math.isnan(a) and math.isnan(b) for a, b in zip(copied, values))
    assert len(copied) == len(values)
    del target, reader, event
    gc.collect()
    assert len(copied) == len(values)


def test_float_errors(schema):
    event = schema.Floats.new_message()
    target = event.init('f32', 2)
    with pytest.raises(ValueError):
        _bulk_float_write(target, [1])
    with pytest.raises(TypeError):
        _bulk_float_write(target, [1, object()])
    ints = event.init('ints', 2)
    with pytest.raises(capnp.KjException):
        _bulk_float_write(ints, [1, 2])
    with pytest.raises(capnp.KjException):
        _bulk_float_read(event.as_reader().ints)


def test_float_source_mutation(schema):
    target = schema.Floats.new_message().init('f64', 2)
    values = []
    class Mutator:
        def __float__(self):
            values.clear()
            return 1.5
    values.extend([Mutator(), 2.5])
    _bulk_float_write(target, values)
    assert list(target) == [1.5, 2.5]


@pytest.mark.parametrize('call', [lambda: _bulk_float_read(None), lambda: _bulk_float_write(None, []),
                                  lambda: _bulk_can_read(None), lambda: _bulk_can_write(None, [])])
def test_none_arguments(call):
    with pytest.raises(TypeError):
        call()


def test_float_buffers(schema):
    import array
    target = schema.Floats.new_message().init('f64', 2)
    _bulk_float_write(target, array.array('f', [1.5, 2.5]))
    assert list(target) == [1.5, 2.5]
    event = schema.Floats.new_message(f32=[1.5, 2.5])
    view = _bulk_float_buffer_read(event.as_reader().f32)
    del event
    gc.collect()
    assert view.readonly and view.format == 'f' and list(view) == [1.5, 2.5]
    with pytest.raises(ValueError):
        _bulk_float_write(target, array.array('i', [1, 2]))
    with pytest.raises((ValueError, BufferError)):
        _bulk_float_write(target, memoryview(array.array('f', [1, 2, 3, 4]))[::2])
    with pytest.raises(TypeError):
        _bulk_read_fields([None])


def test_borrowed_float_view(schema):
    event = schema.Floats.new_message(f32=[1.5, 2.5])
    view = _bulk_float_view(event.as_reader().f32)
    assert view.readonly and view.format == 'f'
    event.f32[0] = 3.5
    assert view[0] == 3.5  # Borrowed, not copied.
    del event
    gc.collect()
    assert list(view) == [3.5, 2.5]
    with pytest.raises(TypeError):
        view[0] = 4.5
    expanded = schema.Expanded.new_message(f32=[{'value': 1.5, 'padding': 33}, {'value': 2.5, 'padding': 44}])
    with schema.Floats.from_bytes(expanded.to_bytes()) as reader:
        fallback = _bulk_float_view(reader.f32)
        assert list(fallback) == [1.5, 2.5]
    assert list(fallback) == [1.5, 2.5]


@pytest.mark.parametrize('field', ['f32', 'f64'])
@pytest.mark.parametrize('values', [[], [1.5, 2.5]])
def test_view_shapes(schema, field, values):
    event = schema.Floats.new_message(**{field: values})
    view = _bulk_float_view(getattr(event.as_reader(), field))
    assert list(view) == values
    _bulk_float_write(getattr(event, field), view)
    assert list(view) == values


@pytest.mark.parametrize('fn', [_bulk_float_view, _bulk_float_buffer_read])
def test_view_none(fn):
    with pytest.raises(TypeError):
        fn(None)


def test_cached_wrong_schema(schema):
    from capnp.lib.capnp import _BulkCanFields
    wrong = _BulkCanFields(log.Event.schema.fields['can'].schema.elementType)
    path = schema.FakeEvent.new_message(can=[{'address': 1, 'dat': b'a', 'src': 0}])
    with pytest.raises(capnp.KjException):
        _bulk_can_read(path.as_reader(), fields=wrong)


def test_different_width_buffer_alias(schema):
    event = schema.Floats.new_message(f64=[1., 2.])
    view = _bulk_float_view(event.as_reader().f64).cast('B').cast('f')[:2]
    expected = list(view)
    _bulk_float_write(event.f64, view)
    assert list(event.f64) == expected
