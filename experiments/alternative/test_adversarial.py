"""Targeted wire-layout compatibility checks, independent of random mutations."""

import math
import struct
import tempfile
from pathlib import Path

from openpilot.cereal import log
from run import compile_kernel, reference, reference_event
from test_wire import frame


def word(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


def target(data, offset):
    signed = struct.unpack("<i", struct.pack("<I", word(data, offset) & 0xFFFFFFFF))[0]
    return offset + 8 + (signed >> 2) * 8


def slot(data, pointer, index):
    return target(data, pointer) + ((word(data, pointer) >> 32) & 65535) * 8 + index * 8


def equal(actual, expected):
    if isinstance(expected, (tuple, list)):
        return (
            type(actual) is type(expected)
            and len(actual) == len(expected)
            and all(map(lambda p: equal(*p), zip(actual, expected)))
        )
    return actual == expected or isinstance(actual, float) and math.isnan(actual) and math.isnan(expected)


def outcome(fn, data):
    try:
        return True, fn(data)
    except Exception:
        return False, None


def replace_list(segment, pointer, kind, count, content):
    data = bytearray(segment)
    start = len(data)
    data.extend(content)
    data.extend(bytes(-len(data) % 8))
    struct.pack_into("<Q", data, pointer, ((start - pointer - 8) // 8 << 2) | 1 | (kind << 32) | (count << 35))
    return frame([data])


def fixtures():
    msg = log.Event.new_message(
        logMonoTime=123,
        valid=False,
        carState={"vEgo": 12.5, "steeringAngleDeg": -9.25, "wheelSpeeds": {"fl": 12.75}, "gearShifter": "drive"},
    )
    segment = bytearray(msg.to_bytes()[8:])
    car_index = log.Event.schema.fields["carState"].proto.slot.offset
    car_pointer = slot(segment, 0, car_index)
    wheel_index = log.Event.schema.fields["carState"].schema.fields["wheelSpeeds"].proto.slot.offset
    wheel_pointer = slot(segment, car_pointer, wheel_index)
    for name, pointer in [("car", car_pointer), ("wheel", wheel_pointer)]:
        original = word(segment, pointer)
        destination = target(segment, pointer)
        near = bytearray(segment)
        pad = len(near)
        landing = (original & 0xFFFFFFFF00000000) | (((destination - pad - 8) // 8 << 2) & 0xFFFFFFFF)
        near.extend(struct.pack("<Q", landing))
        struct.pack_into("<Q", near, pointer, (pad // 8 << 3) | 2)
        yield name + " single far/backwards", frame([near])
        double = bytearray(segment)
        struct.pack_into("<Q", double, pointer, (1 << 32) | 6)
        yield (
            name + " double far",
            frame([double, struct.pack("<QQ", (destination // 8 << 3) | 2, original & 0xFFFFFFFF00000000)]),
        )
    backward = bytearray(segment)
    root = word(segment, 0)
    event = target(segment, 0)
    new_event = len(backward)
    backward.extend(segment[event : event + (((root >> 32) & 65535) + (root >> 48)) * 8])
    new_pointer = new_event + car_pointer - event
    struct.pack_into(
        "<Q",
        backward,
        new_pointer,
        (word(segment, car_pointer) & 0xFFFFFFFF00000000)
        | (((target(segment, car_pointer) - new_pointer - 8) // 8 << 2) & 0xFFFFFFFF),
    )
    struct.pack_into("<Q", backward, 0, (root & 0xFFFFFFFF00000000) | ((new_event - 8) // 8 << 2))
    yield "backwards near", frame([backward])
    yield "far segment beyond cache", frame([struct.pack("<Q", (512 << 32) | 2)] + [b""] * 511 + [segment])

    # All primitive encodings, empty and populated, and inline-composite upgrades.
    for event_name, field in [("longitudinalPlan", "speeds"), ("modelV2", "leadsV3"), ("can", None)]:
        message = log.Event.new_message(**{event_name: [] if field is None else {}})
        data = message.to_bytes()[8:]
        pointer = slot(data, 0, log.Event.schema.fields[event_name].proto.slot.offset)
        if field is not None:
            pointer = slot(data, pointer, log.Event.schema.fields[event_name].schema.fields[field].proto.slot.offset)
        for kind, size in enumerate([0, 0, 1, 2, 4, 8, 8]):
            for count in [0, 2]:
                payload = bytes((count + 7) // 8 if kind == 1 else size * count)
                yield (
                    f"{event_name} primitive kind={kind} count={count}",
                    replace_list(data, pointer, kind, count, payload),
                )
        for count in [0, 2]:
            for data_words, pointers in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                words = count * (data_words + pointers)
                tag = (count << 2) | (data_words << 32) | (pointers << 48)
                yield (
                    f"{event_name} composite count={count} data={data_words} pointers={pointers}",
                    replace_list(data, pointer, 7, words, struct.pack("<Q", tag) + bytes(words * 8)),
                )
        # Struct tag exceeds the enclosing list's advertised word count.
        yield (
            event_name + " overrun composite",
            replace_list(data, pointer, 7, 0, struct.pack("<Q", (2 << 2) | (1 << 32))),
        )

    # Data is stricter than List(UInt8): even empty non-byte encodings are invalid.
    message = log.Event.new_message(can=[{"address": 0x123, "dat": b"x", "src": 2}])
    data = message.to_bytes()[8:]
    can_pointer = slot(data, 0, log.Event.schema.fields["can"].proto.slot.offset)
    start = target(data, can_pointer)
    tag = word(data, start)
    can_schema = log.Event.schema.fields["can"].schema.elementType
    pointer = start + 8 + ((tag >> 32) & 65535) * 8 + can_schema.fields["dat"].proto.slot.offset * 8
    for kind, size in enumerate([0, 0, 1, 2, 4, 8, 8]):
        for count in [0, 2]:
            content = bytes((count + 7) // 8 if kind == 1 else size * count)
            yield f"CAN Data kind={kind} count={count}", replace_list(data, pointer, kind, count, content)

    # A non-null Float32 list reached through a double-far landing pad.
    message = log.Event.new_message(longitudinalPlan={"speeds": [1.25, -2.5]})
    data = bytearray(message.to_bytes()[8:])
    plan_pointer = slot(data, 0, log.Event.schema.fields["longitudinalPlan"].proto.slot.offset)
    speeds = log.Event.schema.fields["longitudinalPlan"].schema.fields["speeds"].proto.slot.offset
    pointer = slot(data, plan_pointer, speeds)
    original = word(data, pointer)
    destination = target(data, pointer)
    struct.pack_into("<Q", data, pointer, (1 << 32) | 6)
    yield (
        "double-far float list",
        frame([data, struct.pack("<QQ", (destination // 8 << 3) | 2, (original & 0xFFFFFFFF00000000) | 1)]),
    )


def run():
    with tempfile.TemporaryDirectory() as directory:
        module, _, _, _ = compile_kernel(Path(directory))
        failures = []
        count = 0
        for name, data in fixtures():
            count += 1
            actual, expected = outcome(module.event, data), outcome(reference_event, data)
            if not equal(actual, expected):
                failures.append((name, actual, expected))
        for speed, angle, wheel in [(float("nan"), float("inf"), -float("inf")), (-0.0, 1.5, -1.5)]:
            row = (2**64 - 1, False, speed, angle, wheel, 65535)
            assert equal(reference(module.write_car(row)), row)
        assert not failures, failures
        print(f"{count} targeted pointer/list compatibility fixtures and special-float writer cases passed")


if __name__ == "__main__":
    run()
