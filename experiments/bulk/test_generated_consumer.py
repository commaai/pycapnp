import gc
import sys

import pytest
from openpilot.cereal import log

from experiments.bulk.bench_generated_consumer import projected_python


@pytest.mark.parametrize('module_name', ['generated_cython', 'generated_native'])
@pytest.mark.parametrize('kind,body', [
    ('carState', {'vEgo': 13.5, 'steeringAngleDeg': -4.5, 'wheelSpeeds': {'fl': 7.0}, 'gearShifter': 'drive'}),
    ('carControl', {'enabled': True, 'actuators': {'accel': 1.25, 'torque': -.5}}),
    ('modelV2', {'position': {'x': [1.5, 2.5]}, 'leadsV3': [{'x': [3.5, 4.5]}, {'x': []}], 'meta': {'laneChangeState': 'off'}}),
    ('longitudinalPlan', {'speeds': [1.5, 2.5], 'accels': [-.5, .5], 'shouldStop': True}),
    ('can', [{'address': 1, 'dat': b'abc', 'src': 0}]),
    ('carState', {}), ('carControl', {}), ('modelV2', {}), ('longitudinalPlan', {}),
])
def test_projection(module_name, kind, body):
    module = pytest.importorskip(module_name)
    wire = log.Event.new_message(valid=False, logMonoTime=2**64 - 1, **{kind: body}).to_bytes()
    expected = projected_python(wire)
    output = module.project(wire)
    assert output == expected
    del wire
    gc.collect()
    assert output == expected


@pytest.mark.parametrize('module_name', ['generated_cython', 'generated_native'])
def test_projection_malformed_no_reference_leak(module_name):
    module = pytest.importorskip(module_name)
    wire = bytes(bytearray(b'\xff' * 8))
    before = sys.getrefcount(wire)
    for _ in range(100):
        with pytest.raises(ValueError):
            module.project(wire)
    assert sys.getrefcount(wire) == before
    for invalid in (None, 5, b'x'):
        with pytest.raises((ValueError, TypeError)):
            module.project(invalid)
