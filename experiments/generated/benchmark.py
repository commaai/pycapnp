"""Compare generated bindings on the same sampled Event corpus and hot-field work."""

import argparse
import gc
import hashlib
import json
import math
import sys
from pathlib import Path

import generated_cython
import generated_native
from openpilot.cereal import log, messaging
from openpilot.tools.lib.logreader import LogReader

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks"))
from bench_openpilot import bench, fill


def scan(messages, generated=False):
    for msg in messages:
        kind = msg.which()
        body = getattr(msg, kind)
        _ = msg.valid, msg.logMonoTime
        if kind == "carState":
            _ = body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl
            _ = body.gearShifter if generated else body.gearShifter.raw
        elif kind == "carControl":
            _ = body.enabled, body.actuators.accel, body.actuators.torque
        elif kind == "modelV2":
            _ = list(body.position.x), [list(lead.x) for lead in body.leadsV3]
            _ = body.meta.laneChangeState if generated else body.meta.laneChangeState.raw
        elif kind == "longitudinalPlan":
            _ = list(body.speeds), list(body.accels), body.shouldStop


def equal(a, b):
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def compare(actual, expected, schema):
    for name, value in expected.items():
        got = getattr(actual, name)
        field = schema.fields[name]
        proto = field.proto
        kind = proto.slot.type.which() if proto.which() == "slot" else "struct"
        if isinstance(value, dict):
            compare(got, value, field.schema)
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                assert len(got) == len(value)
                for g, v in zip(got, value):
                    compare(g, v, field.schema.elementType)
            elif field.proto.slot.type.list.elementType.which() == "enum":
                assert got == [field.schema.elementType.enumerants[x] for x in value]
            else:
                assert equal(got, value), (name, got, value)
        elif kind == "enum":
            assert got == field.schema.enumerants[value], (name, got, value)
        else:
            assert equal(got, value), (name, got, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rlog")
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    events = list(LogReader(args.rlog))
    first = {m.which(): m for m in reversed(events)}
    n = min(1000, len(events))
    chosen = [events[i * len(events) // n] for i in range(n)] + list(first.values())
    wire = [m.as_builder().to_bytes() for m in chosen]
    records = [m.to_dict() for m in chosen]
    print(json.dumps({"rlog": args.rlog, "sha256": hashlib.sha256(b"".join(wire)).hexdigest(), "events": len(wire)}))
    for mod in (generated_cython, generated_native):
        for data, record in zip(wire, records):
            compare(mod.from_bytes(data), record, log.Event.schema)
            assert equal(messaging.log_from_bytes(mod.from_dict(record)).to_dict(), record)
            assert equal(messaging.log_from_bytes(fill(mod.new(), record).to_bytes()).to_dict(), record)
        # Child ownership outlives its root; absent struct/scalar defaults.
        child = mod.from_bytes(log.Event.new_message(carState={}).to_bytes()).carState
        gc.collect()
        assert child.vEgo == 0 and child.wheelSpeeds.fl == 0
        empty = mod.from_bytes(log.Event.new_message().to_bytes())
        assert empty.valid is True
        try:
            empty.carState
        except ValueError:
            pass
        else:
            raise AssertionError("inactive union accepted")
        for bad in (b"", b"123", b"\xff" * 8):
            try:
                mod.from_bytes(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("bad message accepted")
        print(mod.__name__, "parity PASS")
    bench("dynamic read", lambda: scan(map(messaging.log_from_bytes, wire)), len(wire), args.repeat)
    bench(
        "dynamic field write",
        lambda: [fill(log.Event.new_message(), d).to_bytes() for d in records],
        len(wire),
        args.repeat,
    )
    bench("dynamic write", lambda: [log.Event.new_message(**d).to_bytes() for d in records], len(wire), args.repeat)
    for mod in (generated_cython, generated_native):
        bench(mod.__name__ + " read", lambda: scan(map(mod.from_bytes, wire), True), len(wire), args.repeat)
        bench(mod.__name__ + " write", lambda: [mod.from_dict(d) for d in records], len(wire), args.repeat)
        bench(mod.__name__ + " field", lambda: [fill(mod.new(), d).to_bytes() for d in records], len(wire), args.repeat)
    for kind in ("carState", "carControl", "modelV2", "longitudinalPlan", "can"):
        subset = [w for w, m in zip(wire, chosen) if m.which() == kind]
        for mod in (generated_native, generated_cython, None):
            parse = mod.from_bytes if mod else messaging.log_from_bytes
            label = mod.__name__ if mod else "dynamic"
            bench(
                label + " " + ("CAN envelope" if kind == "can" else kind),
                lambda: scan(map(parse, subset), mod is not None),
                len(subset),
                args.repeat,
            )
    can_wire = [w for w, m in zip(wire, chosen) if m.which() == "can"]
    for mod in (generated_native, generated_cython, None):
        parse = mod.from_bytes if mod else messaging.log_from_bytes
        label = mod.__name__ if mod else "dynamic"
        bench(
            label + " CAN frames",
            lambda: [[(f.address, f.dat, f.src) for f in parse(w).can] for w in can_wire],
            len(can_wire),
            args.repeat,
        )
    models = [w for w, m in zip(wire, chosen) if m.which() == "modelV2"]
    for mod in (generated_native, generated_cython, None):
        parse = mod.from_bytes if mod else messaging.log_from_bytes
        label = mod.__name__ if mod else "dynamic"
        bench(
            label + " sparse model", lambda: [parse(w).modelV2.position.x[0] for w in models], len(models), args.repeat
        )
    bench(
        "dynamic full list",
        lambda: [list(messaging.log_from_bytes(w).modelV2.position.x) for w in models],
        len(models),
        args.repeat,
    )
    for mod in (generated_native, generated_cython):
        parse = mod.from_bytes
        bench(
            mod.__name__ + " view sparse",
            lambda: [parse(w).modelV2.position.view("x")[0] for w in models],
            len(models),
            args.repeat,
        )
        bench(
            mod.__name__ + " view full",
            lambda: [list(parse(w).modelV2.position.view("x")) for w in models],
            len(models),
            args.repeat,
        )
        bench(
            mod.__name__ + " eager full",
            lambda: [list(parse(w).modelV2.position.x) for w in models],
            len(models),
            args.repeat,
        )
    bench("dynamic read confirm", lambda: scan(map(messaging.log_from_bytes, wire)), len(wire), args.repeat)


if __name__ == "__main__":
    main()
