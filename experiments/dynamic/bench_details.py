"""Focused, calibrated cases supplementing the <=100-line openpilot benchmark."""

import argparse
import gc
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

import capnp
from openpilot.cereal import log, messaging
from openpilot.tools.lib.logreader import LogReader


def measure(fn, count=1):
    start = perf_counter()
    fn()
    loops = max(1, int(0.08 / (perf_counter() - start)))
    samples = []
    for _ in range(5):
        start = perf_counter()
        for _ in range(loops):
            fn()
        samples.append((perf_counter() - start) * 1e9 / loops / count)
    return {"median_ns": median(samples), "min_ns": min(samples), "max_ns": max(samples)}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("rlog")
args = parser.parse_args()
events = list(LogReader(args.rlog))
first = {e.which(): messaging.log_from_bytes(e.as_builder().to_bytes()) for e in reversed(events)}
del events
results = {}
for name in ("carState", "carControl", "modelV2", "longitudinalPlan", "can", "carParams"):
    event = first[name]
    start = perf_counter()
    record = event.to_dict(verbose=True)
    cold = (perf_counter() - start) * 1e6
    results[name] = {
        "first_export_us": cold,
        "export": measure(lambda: event.to_dict(verbose=True)),
        "kwargs": measure(lambda: log.Event.new_message(**record)),
    }
event = first["carState"]
cs = event.carState
field = cs.schema.fields["vEgo"]
nums = first["modelV2"].modelV2.position.x
cases = {
    "attribute": lambda: cs.vEgo,
    "explicit_get": lambda: cs._get("vEgo"),
    "cached_field": lambda: cs._get_by_field(field),
    "nested_attribute": lambda: event.carState.vEgo,
    "which": lambda: event.which(),
    "which_raw": lambda: event.which.raw,
    "float_list": lambda: list(nums),
}
results["micro"] = {name: measure(fn) for name, fn in cases.items()}
# Standalone parser exercises the operation-local plan fallback.
schema = capnp.SchemaParser().load(str(Path(__file__).parents[2] / "test/addressbook.capnp"))
custom = schema.Person.new_message(name="A", phones=[{"number": "123", "type": "mobile"}])
results["custom_parser"] = measure(lambda: custom.to_dict(verbose=True))
gc.collect()
gc.disable()
before = sum(isinstance(o, capnp._MallocMessageBuilder) for o in gc.get_objects())
plans_before = sum(type(o).__name__ == "_ConversionPlan" for o in gc.get_objects())
for _ in range(10000):
    message = log.Event.new_message(carState={"vEgo": 4.0})
    message.to_dict()
    message.which()
    del message
results["retained_builders"] = sum(isinstance(o, capnp._MallocMessageBuilder) for o in gc.get_objects()) - before
results["retained_plan_growth"] = sum(type(o).__name__ == "_ConversionPlan" for o in gc.get_objects()) - plans_before
results["cached_plans"] = plans_before
gc.enable()
assert results["retained_builders"] == 0
print(
    json.dumps(
        {
            "capnp": capnp.__file__,
            "flags": {k: v for k, v in os.environ.items() if k.startswith("CAPNP_")},
            "results": results,
        },
        indent=2,
    )
)
