"""Differential fixtures for the deliberately narrow native CarState reader."""

from pathlib import Path
import random
import struct
import tempfile

from openpilot.cereal import log
from run import compile_kernel, reference, reference_event, reference_write


def frame(segments):
    sizes = [len(s) // 8 for s in segments]
    header = struct.pack("<" + "I" * (len(sizes) + 1), len(sizes) - 1, *sizes)
    return header + bytes((-len(header)) % 8) + b"".join(segments)


def run():
    with tempfile.TemporaryDirectory() as directory:
        module, _, _, _ = compile_kernel(Path(directory))
        msg = log.Event.new_message(logMonoTime=123, valid=False)
        car = msg.init("carState")
        car.vEgo = 12.5
        car.steeringAngleDeg = -9.25
        car.wheelSpeeds.fl = 12.75
        car.gearShifter = "drive"
        wire = msg.to_bytes()
        assert struct.unpack_from("<I", wire)[0] == 0
        segment = wire[8:]
        root = struct.unpack_from("<Q", segment)[0]
        fixtures = [
            wire,
            frame([struct.pack("<Q", (1 << 32) | 2), segment]),
            frame(
                [
                    struct.pack("<Q", (1 << 32) | 6),
                    struct.pack("<QQ", (2 << 32) | 8 | 2, root & 0xFFFFFFFF00000000),
                    segment,
                ]
            ),
        ]
        default = log.Event.new_message()
        default.init("carState")
        fixtures.append(default.to_bytes())
        # Older/smaller CarState payload: absent fields must read their defaults.
        old = [2 << 32 | 1 << 48, 99, 21, 0]
        fixtures.append(frame([struct.pack("<QQQQ", *old)]))
        # More segments than the former stack cache limit remain valid.
        fixtures.append(frame([segment] + [b""] * 512))
        for data in fixtures:
            assert module.one(data) == reference(data)
            assert module.batch([data, data]) == [reference(data)] * 2
        rows = [(123, False, 12.5, -9.25, 12.75, 65535), (0, True, 0.0, 0.0, 0.0, 0)]
        for row in rows:
            assert reference(module.write_car(row)) == row
            assert reference(module.write_car(row)) == reference(reference_write(row))
        for kind, body in [
            ("carControl", {"enabled": True, "actuators": {"accel": -1.5, "torque": 0.25}}),
            (
                "modelV2",
                {
                    "position": {"x": [1.0, 2.0, 3.0]},
                    "leadsV3": [{"x": [4.0, 5.0]}, {"x": []}],
                    "meta": {"laneChangeState": 2},
                },
            ),
            ("longitudinalPlan", {"speeds": [1.0, 2.0], "accels": [-1.0, 0.0], "shouldStop": True}),
            ("can", [{"address": 0x123, "src": 2, "dat": b"abc\x00def"}, {"address": 0, "src": 255, "dat": b""}]),
        ]:
            data = log.Event.new_message(logMonoTime=123, valid=False, **{kind: body}).to_bytes()
            assert module.event(data) == reference_event(data), kind
            default = log.Event.new_message(**{kind: [] if kind == "can" else {}}).to_bytes()
            assert module.event(default) == reference_event(default), kind
            for end in range(len(data)):
                try:
                    module.event(data[:end])
                except ValueError:
                    pass
                else:
                    raise AssertionError((kind, "accepted truncation", end))
        for data in fixtures:
            for end in range(len(data)):
                try:
                    module.one(data[:end])
                except ValueError:
                    pass
                else:
                    raise AssertionError(("accepted truncation", end))
        malformed = [frame([struct.pack("<Q", value)]) for value in [1, 3, 2, (513 << 32) | 2, (0x7FFFFFFF << 2)]]
        malformed.append(log.Event.new_message(carControl={}).to_bytes())
        for data in malformed:
            try:
                module.one(data)
            except ValueError:
                pass
            else:
                raise AssertionError("accepted malformed pointer/wrong union")
        rng = random.Random(17)
        accepted = 0
        for _ in range(10000):
            data = bytearray(wire)
            for _ in range(rng.randrange(1, 5)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            data = bytes(data)
            try:
                actual = module.one(data)
            except ValueError:
                continue
            # The selected paths must agree; unrelated malformed pointers are not traversed.
            expected = reference(data)
            for a, b in zip(actual, expected):
                assert a == b or (isinstance(a, float) and a != a and b != b)
            accepted += 1
        print(
            f"{len(fixtures)} valid fixtures; exhaustive truncations; malformed pointers; 10000 deterministic mutations ({accepted} accepted) passed"
        )


if __name__ == "__main__":
    run()
