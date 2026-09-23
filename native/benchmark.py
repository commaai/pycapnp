"""Compare generated Event bindings with pycapnp on a sampled openpilot log."""

import argparse
import gc
import hashlib
import json
import statistics
import time

import generated_native
from openpilot.cereal import log
from openpilot.tools.lib.logreader import LogReader


def dynamic_from_bytes(data):
    # Match messaging.log_from_bytes without importing its msgq extension.
    with log.Event.from_bytes(data, traversal_limit_in_words=2**64 - 1) as event:
        return event


def scan(wire, generated=False):
    result = []
    for data in wire:
        event = generated_native.from_bytes(data) if generated else dynamic_from_bytes(data)
        kind = event.which()
        body = getattr(event, kind)
        value = None
        if kind == "carState":
            gear = body.gearShifter
            value = (body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, gear if generated else gear.raw)
        elif kind == "carControl":
            value = (body.enabled, body.actuators.accel, body.actuators.torque)
        elif kind == "modelV2":
            state = body.meta.laneChangeState
            value = (list(body.position.x), [list(lead.x) for lead in body.leadsV3], state if generated else state.raw)
        elif kind == "longitudinalPlan":
            value = (list(body.speeds), list(body.accels), body.shouldStop)
        result.append((kind, event.valid, event.logMonoTime, value))
    return result


def canonical(value):
    return json.dumps(value, sort_keys=True, default=lambda data: data.hex(), allow_nan=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rlog")
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be positive")
    events = list(LogReader(args.rlog))
    if not events:
        parser.error("log is empty")
    first = {event.which(): event for event in reversed(events)}
    count = min(1000, len(events))
    selected = [events[i * len(events) // count] for i in range(count)] + list(first.values())
    wire = [event.as_builder().to_bytes() for event in selected]
    records = [event.to_dict() for event in selected]
    assert canonical(scan(wire)) == canonical(scan(wire, True))
    for record in records:
        with log.Event.from_bytes(generated_native.from_dict(record)) as event:
            assert canonical(event.to_dict()) == canonical(record)
    cases = {
        "dynamic read": lambda: scan(wire),
        "native read": lambda: scan(wire, True),
        "dynamic dict write": lambda: [log.Event.new_message(**d).to_bytes() for d in records],
        "native dict write": lambda: [generated_native.from_dict(d) for d in records],
    }
    loops, samples = {}, {name: [] for name in cases}
    for name, operation in cases.items():
        start = time.perf_counter()
        operation()
        loops[name] = max(1, min(10000, int(0.12 / max(time.perf_counter() - start, 1e-9))))
    for repeat in range(args.repeat):
        order = list(cases) if repeat % 2 == 0 else list(reversed(cases))
        for name in order:
            gc.collect()
            start = time.perf_counter()
            for _ in range(loops[name]):
                cases[name]()
            samples[name].append((time.perf_counter() - start) * 1e6 / loops[name] / len(wire))
    print(
        json.dumps(
            {
                "events": len(wire),
                "corpus_sha256": hashlib.sha256(b"".join(wire)).hexdigest(),
                "microseconds_per_event": {
                    name: {"median": statistics.median(values), "samples": values} for name, values in samples.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
