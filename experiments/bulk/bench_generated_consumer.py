"""Joint generated-accessor/native-consumer projection experiment (requires generated modules)."""
import argparse
import hashlib
import json
from pathlib import Path

from openpilot.cereal import messaging
from openpilot.tools.lib.logreader import LogReader
from experiments.bulk.bench import measure_pair


def projected_python(data):
    msg = messaging.log_from_bytes(data)
    kind = msg.which()
    metadata = msg.valid, msg.logMonoTime
    if kind == 'carState':
        body = msg.carState
        values = body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, body.gearShifter.raw
    elif kind == 'carControl':
        body = msg.carControl
        actuators = body.actuators
        values = body.enabled, actuators.accel, actuators.torque
    elif kind == 'modelV2':
        body = msg.modelV2
        values = list(body.position.x), [list(lead.x) for lead in body.leadsV3], body.meta.laneChangeState.raw
    elif kind == 'longitudinalPlan':
        body = msg.longitudinalPlan
        values = list(body.speeds), list(body.accels), body.shouldStop
    else:
        values = None
    return kind, metadata, values


def main():
    import generated_cython
    import generated_native
    parser = argparse.ArgumentParser()
    parser.add_argument('rlog')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    events = list(LogReader(args.rlog))
    first = {m.which(): m for m in reversed(events)}
    n = min(1000, len(events))
    selected = [events[i * len(events) // n] for i in range(n)] + list(first.values())
    wire = [m.as_builder().to_bytes() for m in selected]
    reference = list(map(projected_python, wire))
    result = {'sha256': hashlib.sha256(b''.join(wire)).hexdigest(), 'messages': len(wire), 'cases': {}}
    for module in (generated_cython, generated_native):
        projected = list(map(module.project, wire))
        assert repr(projected) == repr(reference)
        result['cases'][module.__name__] = measure_pair(lambda: list(map(projected_python, wire)), lambda: list(map(module.project, wire)), len(wire))
        print(module.__name__, result['cases'][module.__name__], flush=True)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
