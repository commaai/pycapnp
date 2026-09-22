import gc
import pickle
import struct

import capnp
import pytest
from capnp.logstream import RawEvent, RawLog, project_many
from capnp.lib.capnp import frame_offsets, project_stream


@pytest.fixture(scope='module')
def schema(tmp_path_factory):
    path = tmp_path_factory.mktemp('scan') / 'scan.capnp'
    path.write_text('''@0xcfbdf2105485d89c;
struct Event { stamp @0 :UInt64; union { car @1 :Car; other @2 :Void; } }
struct Car { speed @0 :Float32; flag @1 :Bool; signed @2 :Int64; text @3 :Text; data @4 :Data; nested @5 :Car; }
''')
    return capnp.load(str(path)).Event


def test_projection(schema):
    first = schema.new_message(stamp=2**63+7, car={'speed': 1.5, 'flag': True, 'signed': -5, 'text':'hello', 'data':b'\x00\xff'})
    other = schema.new_message(stamp=2, other=None)
    empty = schema.new_message(stamp=3)
    data = first.to_bytes() + other.to_bytes() + empty.to_bytes()
    paths = ['stamp','car.speed','car.flag','car.signed','car.text','car.data']
    expected = [(2**63+7,1.5,True,-5,'hello',b'\x00\xff'),(3,0.,False,0,'',b'')]
    assert project_stream(data,schema.schema,'car',paths) == expected
    assert project_many([data]*4,schema,'car',paths,workers=2) == [expected]*4
    assert project_stream(b'',schema.schema,'car',paths) == []
    with pytest.raises((TypeError, capnp.KjException)):
        project_stream(bytearray(data),schema.schema,'car',paths)
    with pytest.raises(capnp.KjException):
        project_stream(data,schema.schema,'stamp',paths)
    with pytest.raises(capnp.KjException):
        project_stream(data,schema.schema,'car',['car'])
    with pytest.raises(capnp.KjException):
        project_stream(data,schema.schema,'car',['car.noSuchField'])


def test_framing(schema):
    data = schema.new_message(car={'speed':5}).to_bytes()
    assert frame_offsets(data*3) == [0,len(data),2*len(data),3*len(data)]
    assert frame_offsets(b'') == [0]
    for bad in (data[:-1], data[:-8], struct.pack('<II',2**32-1,0), b'\x00'*8):
        with pytest.raises(capnp.KjException):
            project_stream(bad,schema.schema,'car',['stamp'])
    with pytest.raises(ValueError):
        RawEvent(data*2,schema)
    with pytest.raises(capnp.KjException):
        frame_offsets(data[:-8])


def test_lifetime_pickle(schema):
    source = bytearray(schema.new_message(stamp=10,car={'speed':7}).to_bytes())
    raw = RawLog(source,schema)
    events = list(raw)
    source[:] = bytes(len(source))
    del raw
    gc.collect()
    assert events[0].car.speed == 7
    assert pickle.loads(pickle.dumps(events))[0].stamp == 10
    changed = events[0].as_builder()
    changed.car.speed = 99
    assert events[0].car.speed == 7
    assert list(RawLog(events[0].to_bytes(),schema))[0].car.speed == 7


def test_limits(schema):
    data = schema.new_message(car={'nested': {'nested': {'speed': 7}}}).to_bytes()
    with pytest.raises(capnp.KjException):
        project_stream(data,schema.schema,'car',['car.nested.nested.speed'],nesting_limit=1)
    with pytest.raises(capnp.KjException):
        project_stream(data,schema.schema,'car',['car.nested.nested.speed'],traversal_limit_in_words=1)
    with pytest.raises(ValueError):
        project_stream(data,schema.schema,'car',['stamp'],nesting_limit=-1)


def test_invalid_api(schema):
    with pytest.raises(TypeError):
        project_stream(b'',None,'car',[])
    for selected, paths in [('car\x00junk',['stamp']), ('car',['stamp\x00junk'])]:
        with pytest.raises(ValueError):
            project_stream(b'',schema.schema,selected,paths)
    data = schema.new_message(stamp=12).to_bytes()
    assert project_many([data,data],schema,'car',iter(['stamp'])) == [[(12,)],[(12,)]]
    with pytest.raises(capnp.KjException):
        project_many([data,data[:-1]],schema,'car',['stamp'])


def test_shared_log_pickle(schema):
    data = schema.new_message(stamp=8).to_bytes() * 3
    log = RawLog(data,schema)
    view = next(iter(log)).serialized_view()
    assert view.readonly and view.obj is log.data
    assert log[-1].stamp == 8
    with pytest.raises(IndexError):
        log[3]
    for protocol in (4,5):
        assert pickle.loads(pickle.dumps(log,protocol=protocol)).to_bytes() == data
    buffers = []
    metadata = pickle.dumps(log,protocol=5,buffer_callback=buffers.append)
    assert len(buffers) == 1
    assert pickle.loads(metadata,buffers=buffers).to_bytes() == data
    detached = log[0].detach()
    assert isinstance(detached._data,bytes)


def test_lists_defaults_far_pointers(tmp_path):
    path = tmp_path / 'lists.capnp'
    path.write_text('''@0xe90b97ec05bb2634;
struct Event { union { car @0 :Car; other @1 :Void; } }
struct Car { speed @0 :Float32 = 3.5; children @1 :List(Car); xs @2 :List(Float32); enum @3 :Which; }
enum Which { a @0; b @1; }
''')
    module = capnp.load(str(path)).Event
    message = module.new_message(car={'children':[{'xs':[1,2,3]}, {'xs':[4,5]}], 'enum':65535, 'xs':[float(i) for i in range(10000)]})
    data = message.to_bytes()
    assert struct.unpack_from('<I',data)[0] > 0  # crosses malloc builder's first segment
    rows = project_stream(data,module.schema,'car',['car.speed','car.children.xs','car.enum','car.xs'])
    assert rows == [(3.5,[[1.,2.,3.],[4.,5.]],65535,[float(i) for i in range(10000)])]
    with module.from_bytes(data) as reader:
        assert reader.car.xs[-1] == rows[0][-1][-1]
    empty = module.new_message().to_bytes()
    assert project_stream(empty,module.schema,'car',['car.speed','car.children.xs']) == [(3.5,[])]


def test_bad_payload(schema):
    data = bytearray(schema.new_message(car={'text':'unique-sentinel'}).to_bytes())
    offset = data.index(b'unique-sentinel')
    data[offset] = 255
    with pytest.raises(UnicodeDecodeError):
        project_stream(bytes(data),schema.schema,'car',['car.text'])
    # A malformed pointer in an unselected field is intentionally not traversed.
    assert project_stream(bytes(data),schema.schema,'car',['stamp']) == [(0,)]


def test_nested_reader_owns_frame(schema):
    import sys
    data = schema.new_message(car={'speed':123}).to_bytes()
    original_refs = sys.getrefcount(data)
    raw = RawLog(data,schema)
    child = raw[0].car
    del raw
    gc.collect()
    assert sys.getrefcount(data) > original_refs
    del data
    churn = [bytes(4096) for _ in range(1000)]
    assert child.speed == 123
    assert churn


def test_bad_pointers(schema):
    data = bytearray(schema.new_message(car={'speed':7}).to_bytes())
    root_bad = data.copy()
    struct.pack_into('<Q',root_bad,8,0x000100007ffffffc)
    assert frame_offsets(bytes(root_bad)) == [0,len(root_bad)]
    with pytest.raises(capnp.KjException):
        project_stream(bytes(root_bad),schema.schema,'car',['stamp'])
    # Root starts at word2, has two data words (stamp+discriminant), then car pointer.
    pointer = struct.unpack_from('<Q',data,8)[0]
    root_start = 16 + ((pointer >> 2) & 0x3fffffff)*8
    pointer_start = root_start + ((pointer >> 32) & 0xffff)*8
    struct.pack_into('<Q',data,pointer_start,0x000100007ffffffc)
    malformed = bytes(data)
    assert project_stream(malformed,schema.schema,'car',['stamp']) == [(0,)]
    with pytest.raises(capnp.KjException):
        project_stream(malformed,schema.schema,'car',['car.speed'])
    with pytest.raises(capnp.KjException):
        project_many([malformed]*2,schema,'car',['car.speed'])
    with pytest.raises(capnp.KjException):
        RawLog(malformed,schema)[0].car.speed


def test_immutable_frame_buffer_lengths(schema):
    from capnp.lib.capnp import read_immutable_frame
    data = schema.new_message(stamp=8).to_bytes()
    class ByteSubclass(bytes):
        def __len__(self):
            return 2**30
    assert read_immutable_frame(ByteSubclass(data),schema.schema).stamp == 8
    multidimensional = memoryview(data).cast('B',shape=[len(data)//8,8])
    assert read_immutable_frame(multidimensional,schema.schema).stamp == 8
    # Misaligned immutable slices take the alignment-copy fallback.
    view = memoryview(b'!' + data)[1:]
    assert read_immutable_frame(view,schema.schema).stamp == 8


@pytest.mark.parametrize('options',[{}, {'flat':True}, {'shared':False}, {'fused':True}, {'fused':True,'shared':False}])
def test_projection_modes(schema,options):
    data = schema.new_message(stamp=2**63+7,car={'speed':3.5,'text':'abc','data':b'\xff','nested':{'speed':4}}).to_bytes()*3
    paths=['stamp','car.speed','car.text','car.data','car.nested.speed']
    assert project_stream(data,schema.schema,'car',paths,**options)==[(2**63+7,3.5,'abc',b'\xff',4.)]*3
    assert project_stream(data,schema.schema,'car',[],**options)==[()]*3
    bad=bytearray(data[:len(data)//3])
    bad[bad.index(b'abc')]=255
    with pytest.raises(UnicodeDecodeError):
        project_stream(bytes(bad),schema.schema,'car',['car.text'],**options)
    with pytest.raises(capnp.KjException):
        project_stream(data[:-1],schema.schema,'car',paths,**options)


def test_nested_lists_of_structs(tmp_path):
    path=tmp_path/'nested-lists.capnp'
    path.write_text('''@0x923145173821c894;
struct Event { union { cars @0 :List(List(Car)); other @1 :Void; } }
struct Car { stamp @0 :UInt64; }
''')
    module=capnp.load(str(path)).Event
    data=module.new_message(cars=[[{'stamp':1}],[{'stamp':2}]]).to_bytes()
    for options in ({},{'fused':True},{'flat':True},{'shared':False}):
        assert project_stream(data,module.schema,'cars',['cars.stamp'],**options)==[([[1],[2]],)]


@pytest.mark.parametrize("options", [{},{"shared":False},{"fused":True},{"shared":False,"fused":True}])
def test_deep_shared_plan(schema,options):
    # Resolving cached ancestors must not recurse before native limits apply.
    path='car.'+'nested.'*10000+'speed'
    data=schema.new_message(car={'speed':1}).to_bytes()
    try:
        rows=project_stream(data,schema.schema,'car',[path],**options)
    except capnp.KjException:
        pass  # Native traversal/nesting rejection is also a valid bounded result.
    else:
        assert rows==[(0.,)]
