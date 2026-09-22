"""Opt-in immutable unpacked log streams, independent of openpilot imports."""
from concurrent.futures import ThreadPoolExecutor
import pickle

from capnp.lib.capnp import frame_offsets, project_stream, read_immutable_frame


def _module(schema_id):
    from capnp.lib.capnp import _global_schema_parser
    return _global_schema_parser.modules_by_id[schema_id]


class RawEvent:
    """Lazy immutable frame view; retaining one event retains its whole backing log.

    Use detach() for long-lived isolated events. Construction validates framing,
    not payloads. Access uses normal lazy validation and traversal limits.
    """
    __slots__ = ('_data', '_module', '_reader', '_enum', '_schema_id')

    def __init__(self, data, module):
        self._data = bytes(data)
        if frame_offsets(self._data) != [0, len(self._data)]:
            raise ValueError('expected exactly one message')
        self._module = module
        self._schema_id = module.schema.node.id
        self._reader = self._enum = None

    @classmethod
    def _trusted(cls, data, module, schema_id):
        obj = object.__new__(cls)
        obj._data, obj._module, obj._schema_id = data, module, schema_id
        obj._reader = obj._enum = None
        return obj

    def serialized_view(self):
        return memoryview(self._data)

    def to_bytes(self):
        return bytes(self._data)

    def detach(self):
        return RawEvent._trusted(self.to_bytes(), self._module, self._schema_id)

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if self._reader is None:
            self._reader = read_immutable_frame(self._data, self._module.schema)
        return getattr(self._reader, name)

    def which(self):
        if self._enum is None:
            self._enum = self.__getattr__('which')()
        return self._enum

    def __reduce__(self):
        return _restore_event, (self.to_bytes(), self._schema_id, self._enum)


def _restore_event(data, schema_id, union):
    event = RawEvent(data, _module(schema_id))
    event._enum = union
    return event


class RawLog:
    """Framing index over shared immutable bytes; iteration does not copy frames.

    Whole-log pickle transfers one backing buffer. Protocol 5 supports optional
    out-of-band buffers; receivers still validate framing and freeze input bytes.
    """
    def __init__(self, data, module):
        self.data = bytes(data)
        self.module = module
        self.schema_id = module.schema.node.id
        self.offsets = frame_offsets(self.data)

    def __len__(self):
        return len(self.offsets) - 1

    def __getitem__(self, index):
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        start, end = self.offsets[index:index+2]
        return RawEvent._trusted(memoryview(self.data)[start:end], self.module, self.schema_id)

    def __iter__(self):
        view = memoryview(self.data)
        for start, end in zip(self.offsets, self.offsets[1:]):
            yield RawEvent._trusted(view[start:end], self.module, self.schema_id)

    def __reduce_ex__(self, protocol):
        data = pickle.PickleBuffer(self.data) if protocol >= 5 else self.data
        return _restore_log, (data, self.schema_id)

    def to_bytes(self):
        return self.data

    def project(self, union_field, paths, **limits):
        return project_stream(self.data, self.module.schema, union_field, paths, **limits)


def _restore_log(data, schema_id):
    return RawLog(data, _module(schema_id))


def project_many(streams, module, union_field, paths, workers=2, **limits):
    """Project independent streams concurrently, preserving stream/row order.

    Native scanning releases the GIL. Python result creation remains serial.
    Inputs must be immutable bytes; executor lifetime is included in each call.
    """
    paths = tuple(paths)
    def scan(data):
        return project_stream(data, module.schema, union_field, paths, **limits)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(scan, streams))
