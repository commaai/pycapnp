"""Paired optional batch API benchmarks; run with repository and openpilot on PYTHONPATH."""
import argparse
import gc
import hashlib
import json
import time
import numpy as np
from pathlib import Path
from statistics import median

from capnp.lib.capnp import _bulk_can_read, _bulk_can_write, _bulk_float_read, _bulk_float_write, _bulk_read_fields, _BulkCanFields, _bulk_float_buffer_read, _bulk_float_view
from openpilot.cereal import log, messaging
from openpilot.selfdrive.pandad.pandad_api_impl import can_capnp_to_list, can_list_to_can_capnp
from openpilot.tools.lib.logreader import LogReader
from benchmarks.bench_openpilot import read_fields


CAN_SCHEMA = log.Event.schema.fields['can'].schema.elementType
CAN_FIELDS = _BulkCanFields(CAN_SCHEMA)
CAN_SCALAR_FIELDS = tuple(CAN_SCHEMA.fields[k] for k in ('address', 'dat', 'src'))

def can_read(wire, msgtype='can', specialized=True):
    return [_bulk_can_read(messaging.log_from_bytes(b), msgtype, CAN_FIELDS, specialized) for b in wire]


def can_read_scalar(wire):
    a, d, s = CAN_SCALAR_FIELDS
    return [(m.logMonoTime, [(f._get_by_field(a), f._get_by_field(d), f._get_by_field(s)) for f in m.can])
            for m in map(messaging.log_from_bytes, wire)]


def can_write(frames, msgtype='can', valid=True, specialized=True):
    event = log.Event.new_message(valid=valid, logMonoTime=int(time.monotonic() * 1e9))
    return _bulk_can_write(event, frames, msgtype, CAN_FIELDS, specialized).to_bytes()


def measure_pair(old, new, count, repeat=7):
    samples = [[], []]
    loops = []
    for fn in (old, new):
        start = time.perf_counter()
        fn()
        loops.append(max(1, int(.12 / (time.perf_counter() - start))))
    for sample in range(repeat):
        for index in ((0, 1) if sample % 2 == 0 else (1, 0)):
            gc.collect()
            start = time.perf_counter()
            for _ in range(loops[index]):
                (old, new)[index]()
            samples[index].append((time.perf_counter() - start) * 1e6 / loops[index] / count)
    before, after = map(median, samples)
    return {'baseline_us': before, 'bulk_us': after, 'speedup': before / after,
            'samples_us': samples, 'count': count}


def read_fields_cached(messages):
    for msg in messages:
        kind = msg.which()
        body = getattr(msg, kind)
        _ = msg.valid, msg.logMonoTime
        if kind == 'carState':
            _ = body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, body.gearShifter.raw
        elif kind == 'carControl':
            actuators = body.actuators
            _ = body.enabled, actuators.accel, actuators.torque
        elif kind == 'modelV2':
            _ = list(body.position.x), [list(lead.x) for lead in body.leadsV3], body.meta.laneChangeState.raw
        elif kind == 'longitudinalPlan':
            _ = list(body.speeds), list(body.accels), body.shouldStop


def projection(messages):
    result = []
    for msg in messages:
        kind = msg.which()
        body = getattr(msg, kind)
        if kind == 'carState':
            value = body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, body.gearShifter.raw
        elif kind == 'carControl':
            value = body.enabled, body.actuators.accel, body.actuators.torque
        elif kind == 'modelV2':
            value = list(body.position.x), [list(lead.x) for lead in body.leadsV3], body.meta.laneChangeState.raw
        elif kind == 'longitudinalPlan':
            value = list(body.speeds), list(body.accels), body.shouldStop
        else:
            value = body
        result.append((kind, (msg.valid, msg.logMonoTime), value))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('rlog')
    parser.add_argument('--output')
    parser.add_argument('--case')
    args = parser.parse_args()
    events = list(LogReader(args.rlog))
    first = {m.which(): m for m in reversed(events)}
    n = min(1000, len(events))
    selected = [events[i * len(events) // n] for i in range(n)] + list(first.values())
    wire = [m.as_builder().to_bytes() for m in selected]
    messages = [messaging.log_from_bytes(b) for b in wire]
    blob = b''.join(wire)
    can_wire = [b for b, m in zip(wire, messages) if m.which() == 'can']
    frames = [f for _, f in can_capnp_to_list(can_wire)]
    assert can_read(can_wire) == can_capnp_to_list(can_wire)
    for f in frames:
        assert can_capnp_to_list([can_write(f)])[0][1] == f
    floats = [m.modelV2.position.x for m in messages if m.which() == 'modelV2']
    for f in floats:
        assert _bulk_float_read(f) == list(f)
    hot = [m for m in messages if m.which() in ('carState', 'carControl', 'modelV2', 'longitudinalPlan')]
    assert repr(_bulk_read_fields(hot, False, True)) == repr(projection(hot))
    assert repr(_bulk_read_fields(hot, True, True)) == repr(projection(hot))
    values = [list(f) for f in floats]
    arrays = [np.array(v, dtype=np.float32) for v in values]
    arrays64 = [np.array(v, dtype=np.float64) for v in values]
    for f in floats:
        np.testing.assert_array_equal(np.asarray(_bulk_float_buffer_read(f)), np.array(list(f), dtype=np.float32))
        np.testing.assert_array_equal(np.asarray(_bulk_float_view(f)), np.array(list(f), dtype=np.float32))
    builders = [log.Event.new_message().init('modelV2').init('position').init('x', len(v)) for v in values]
    def scalar_write():
        for b, v in zip(builders, values):
            for i, x in enumerate(v):
                b[i] = x
    def scalar_array_write(source=arrays):
        for b, v in zip(builders, source):
            for i, x in enumerate(v):
                b[i] = float(x)
    def bulk_write():
        for b, v in zip(builders, values):
            _bulk_float_write(b, v)
    cases = {
        'CAN read specialization': (lambda: can_read(can_wire, specialized=False), lambda: can_read(can_wire), len(can_wire)),
        'CAN write specialization': (lambda: [can_write(f, specialized=False) for f in frames], lambda: [can_write(f) for f in frames], len(frames)),
        'CAN read': (lambda: can_capnp_to_list(can_wire), lambda: can_read(can_wire), len(can_wire)),
        'CAN read same parse': (lambda: can_read_scalar(can_wire), lambda: can_read(can_wire), len(can_wire)),
        'CAN write': (lambda: [can_list_to_can_capnp(f) for f in frames], lambda: [can_write(f) for f in frames], len(frames)),
        'float read': (lambda: [list(f) for f in floats], lambda: [_bulk_float_read(f) for f in floats], len(floats)),
        'float write': (scalar_write, bulk_write, len(values)),
        'float numpy read': (lambda: [np.array(list(f), dtype=np.float32) for f in floats], lambda: [np.asarray(_bulk_float_buffer_read(f)) for f in floats], len(floats)),
        'float numpy borrowed': (lambda: [np.asarray(_bulk_float_buffer_read(f)) for f in floats], lambda: [np.asarray(_bulk_float_view(f)) for f in floats], len(floats)),
        'float crosswidth write': (lambda: scalar_array_write(arrays64), lambda: [_bulk_float_write(b, v) for b, v in zip(builders, arrays64)], len(values)),
        'float buffer write': (scalar_array_write, lambda: [_bulk_float_write(b, v) for b, v in zip(builders, arrays)], len(values)),
        'consumer same caching': (lambda: read_fields_cached(messages), lambda: _bulk_read_fields(messages), len(messages)),
        'consumer': (lambda: read_fields(messages), lambda: _bulk_read_fields(messages), len(messages)),
        'consumer+numeric': (lambda: read_fields(messages), lambda: _bulk_read_fields(messages, True), len(messages)),
        'live read': (lambda: read_fields(map(messaging.log_from_bytes, wire)), lambda: _bulk_read_fields(map(messaging.log_from_bytes, wire), True), len(wire)),
        'LogReader scan': (lambda: read_fields(LogReader.from_bytes(blob)), lambda: _bulk_read_fields((m._evt for m in LogReader.from_bytes(blob)), True), len(wire)),
    }
    results = {'sha256': hashlib.sha256(blob).hexdigest(), 'messages': len(messages), 'frame_counts': [len(f) for f in frames], 'float_lengths': [len(f) for f in floats], 'cases': {}}
    for name, (old, new, count) in cases.items():
        if args.case and name != args.case:
            continue
        if not count:
            results['cases'][name] = {'skipped': 'corpus has no matching events'}
            continue
        results['cases'][name] = measure_pair(old, new, count)
        print(name, results['cases'][name], flush=True)
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
