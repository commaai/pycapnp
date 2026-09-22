"""Steady-state capnp workloads from a local rlog; see README for scope and usage."""

import argparse
import gc
import hashlib
import pickle
import platform
import time
from collections import Counter
from pathlib import Path
from statistics import median

import capnp
from openpilot.cereal import log, messaging
from openpilot.selfdrive.pandad.pandad_api_impl import can_capnp_to_list, can_list_to_can_capnp
from openpilot.system.webrtc.schema import generate_struct
from openpilot.tools.lib.logreader import LogReader


def fill(builder, values):
    for key, value in values.items():
        if isinstance(value, dict):
            fill(builder.init(key), value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            for child, fields in zip(builder.init(key, len(value)), value):
                fill(child, fields)
        else:
            setattr(builder, key, value)
    return builder


def read_fields(messages):
    for msg in messages:
        kind = msg.which()
        body = getattr(msg, kind)
        _ = msg.valid, msg.logMonoTime
        if kind == "carState":
            _ = body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, body.gearShifter.raw
        elif kind == "carControl":
            _ = body.enabled, body.actuators.accel, body.actuators.torque
        elif kind == "modelV2":
            _ = list(body.position.x), [list(lead.x) for lead in body.leadsV3], body.meta.laneChangeState.raw
        elif kind == "longitudinalPlan":
            _ = list(body.speeds), list(body.accels), body.shouldStop


def bench(name, operation, count, repeats):
    start = time.perf_counter()
    operation()  # Untimed warmup/calibration; cyclic GC stays enabled.
    loops = max(1, int(0.2 / (time.perf_counter() - start)))
    samples = []
    for _ in range(repeats):
        gc.collect()
        start = time.perf_counter()
        for _ in range(loops):
            operation()
        samples.append((time.perf_counter() - start) * 1e6 / loops / count)
    print(f"{name:20} {median(samples):10.2f} us/item  [{min(samples):.2f}, {max(samples):.2f}]  n={count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rlog", type=Path)
    parser.add_argument("--messages", type=int, default=1000)
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    assert args.messages > 0 and args.repeat > 0
    events = list(LogReader(str(args.rlog.resolve())))  # I/O/decompression/setup are not timed.
    first = {m.which(): m for m in reversed(events)}
    assert {"can", "carState", "carControl", "modelV2", "longitudinalPlan", "carParams"} <= first.keys()
    n = min(args.messages, len(events))
    selected = [events[i * len(events) // n] for i in range(n)] + list(first.values())
    wire = [m.as_builder().to_bytes() for m in selected]
    blob = b"".join(wire)
    messages = [messaging.log_from_bytes(b) for b in wire]
    records = [m.to_dict() for m in messages]
    payloads = [{m.which(): getattr(m, m.which())} for m in messages]
    can_wire = [b for b, m in zip(wire, messages) if m.which() == "can"]
    frames = [batch for _, batch in can_capnp_to_list(can_wire)]
    del events, first, selected
    print(f"Python {platform.python_version()} | capnp {capnp.__version__} | {capnp.__file__}")
    print(f"sha256={hashlib.sha256(blob).hexdigest()} bytes={len(blob)}")
    print(dict(Counter(m.which() for m in messages)))
    cases = {
        "live read": (lambda: read_fields(map(messaging.log_from_bytes, wire)), len(wire)),
        "field write+encode": (lambda: [fill(log.Event.new_message(), d).to_bytes() for d in records], len(records)),
        "kwargs write+encode": (lambda: [log.Event.new_message(**d).to_bytes() for d in records], len(records)),
        "payload assignment": (lambda: [log.Event.new_message(**d).to_bytes() for d in payloads], len(payloads)),
        "CAN cached read": (lambda: can_capnp_to_list(can_wire), len(can_wire)),
        "CAN cached write": (lambda: [can_list_to_can_capnp(f) for f in frames], len(frames)),
        "LogReader parse+scan": (lambda: read_fields(LogReader.from_bytes(blob)), len(messages)),
        "dict export": (lambda: [m.to_dict(verbose=True) for m in messages], len(messages)),
        "copy+encode": (lambda: [m.as_builder().to_bytes() for m in messages], len(messages)),
        "reader pickle": (lambda: pickle.loads(pickle.dumps(messages)), len(messages)),
        "LogReader pickle": (lambda: pickle.loads(pickle.dumps(list(LogReader.from_bytes(blob)))), len(messages)),
        "schema reflection": (lambda: generate_struct(log.Event.schema.fields["carState"].schema), 1),
    }
    gc.enable()
    for name, (operation, count) in cases.items():
        bench(name, operation, count, args.repeat)
