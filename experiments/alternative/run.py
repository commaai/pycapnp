"""Schema-specialized native direct-wire projection and binding/JIT experiments."""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sysconfig
import tempfile
import time

import cffi
from openpilot.cereal import log, messaging
from openpilot.tools.lib.logreader import LogReader

ROOT = Path(__file__).resolve().parent


def require_field(schema, name, kind, element=None, allow_union=False):
    field = schema.fields[name].proto
    if not allow_union and field.discriminantValue != 65535:
        raise ValueError(f"unsupported union field: {name}")
    slot = field.slot
    if slot.type.which() != kind or slot.defaultValue.which() != kind:
        raise ValueError(f"unsupported type for {name}: expected {kind}")
    if kind in ("struct", "list", "data") and (slot.hadExplicitDefault or slot.defaultValue._has(kind)):
        raise ValueError(f"unsupported pointer default for {name}")
    if element is not None and slot.type.list.elementType.which() != element:
        raise ValueError(f"unsupported list element for {name}: expected {element}")


def layout(event_schema=None):
    event = log.Event.schema if event_schema is None else event_schema
    for field, kind, element in [
        ("carState", "struct", None),
        ("carControl", "struct", None),
        ("modelV2", "struct", None),
        ("longitudinalPlan", "struct", None),
        ("can", "list", "struct"),
    ]:
        require_field(event, field, kind, element, allow_union=True)
        if event.fields[field].proto.slot.offset != event.fields["carState"].proto.slot.offset:
            raise ValueError("selected Event payloads must share the same union pointer slot")
        if event.fields[field].proto.discriminantValue == 65535:
            raise ValueError("selected Event payloads must be union members")
    require_field(event, "logMonoTime", "uint64")
    require_field(event, "valid", "bool")
    car = event.fields["carState"].schema
    require_field(car, "vEgo", "float32")
    require_field(car, "steeringAngleDeg", "float32")
    require_field(car, "gearShifter", "enum")
    require_field(car, "wheelSpeeds", "struct")
    require_field(car.fields["wheelSpeeds"].schema, "fl", "float32")
    wheel = car.fields["wheelSpeeds"].schema
    values = {
        "DISCRIMINANT_OFFSET": event.node.struct.discriminantOffset * 2,
        "CAR_DISCRIMINANT": event.fields["carState"].proto.discriminantValue,
        "CAR_POINTER": event.fields["carState"].proto.slot.offset,
        "WHEEL_POINTER": car.fields["wheelSpeeds"].proto.slot.offset,
    }
    for name, schema, field, size in [
        ("TIME", event, "logMonoTime", 8),
        ("VALID", event, "valid", 1),
        ("SPEED", car, "vEgo", 4),
        ("ANGLE", car, "steeringAngleDeg", 4),
        ("WHEEL", wheel, "fl", 4),
        ("GEAR", car, "gearShifter", 2),
    ]:
        slot = schema.fields[field].proto.slot
        kind = slot.type.which()
        default = getattr(slot.defaultValue, kind)
        if kind == "float32":
            default = struct.unpack("<I", struct.pack("<f", default))[0]
        values[name + "_OFFSET"] = slot.offset * (1 if kind == "bool" else size)
        values[name + "_DEFAULT"] = int(default)
    schemas = {"EVENT": event, "CAR": car, "WHEELS": wheel}
    for prefix, field in [
        ("CONTROL", "carControl"),
        ("MODEL", "modelV2"),
        ("PLAN", "longitudinalPlan"),
        ("CAN", "can"),
    ]:
        f = event.fields[field]
        schemas[prefix] = f.schema.elementType if field == "can" else f.schema
        values[prefix + "_DISCRIMINANT"] = f.proto.discriminantValue
    schemas["ACTUATORS"] = schemas["CONTROL"].fields["actuators"].schema
    schemas["POSITION"] = schemas["MODEL"].fields["position"].schema
    schemas["LEAD"] = schemas["MODEL"].fields["leadsV3"].schema.elementType
    schemas["META"] = schemas["MODEL"].fields["meta"].schema
    expected = {
        "CONTROL": {"enabled": ("bool", None), "actuators": ("struct", None)},
        "ACTUATORS": {"accel": ("float32", None), "torque": ("float32", None)},
        "MODEL": {"position": ("struct", None), "leadsV3": ("list", "struct"), "meta": ("struct", None)},
        "POSITION": {"x": ("list", "float32")},
        "LEAD": {"x": ("list", "float32")},
        "META": {"laneChangeState": ("enum", None)},
        "PLAN": {"speeds": ("list", "float32"), "accels": ("list", "float32"), "shouldStop": ("bool", None)},
        "CAN": {"address": ("uint32", None), "src": ("uint8", None), "dat": ("data", None)},
    }
    for prefix, fields in expected.items():
        for field, (kind, element) in fields.items():
            require_field(schemas[prefix], field, kind, element)
    selected = {
        "CONTROL": ["enabled", "actuators"],
        "ACTUATORS": ["accel", "torque"],
        "MODEL": ["position", "leadsV3", "meta"],
        "POSITION": ["x"],
        "LEAD": ["x"],
        "META": ["laneChangeState"],
        "PLAN": ["speeds", "accels", "shouldStop"],
        "CAN": ["address", "src", "dat"],
    }
    for prefix, schema in schemas.items():
        values[prefix + "_DATA"] = schema.node.struct.dataWordCount
        values[prefix + "_POINTERS"] = schema.node.struct.pointerCount
        for field in selected.get(prefix, []):
            slot = schema.fields[field].proto.slot
            kind = slot.type.which()
            size = {"float32": 4, "uint32": 4, "uint16": 2, "enum": 2}.get(kind, 1)
            name = prefix + "_" + field.upper()
            values[name] = slot.offset * size
            if kind not in ("struct", "list", "data"):
                default = getattr(slot.defaultValue, kind)
                if kind == "float32":
                    default = struct.unpack("<I", struct.pack("<f", default))[0]
                values[name + "_DEFAULT"] = int(default)
    return "\n".join(f"#define {k} {v}ULL" for k, v in values.items()) + "\n"


def compile_kernel(cache):
    started = time.perf_counter()
    header = layout()
    source = b"".join((ROOT / name).read_bytes() for name in ("wire.c", "result.h", "run.py"))
    # Cache includes ABI, compiler identity and exact source/schema constants.
    compiler = subprocess.check_output(["cc", "--version"])
    key = hashlib.sha256(source + header.encode() + compiler + sysconfig.get_config_var("SOABI").encode()).hexdigest()
    target = cache / key
    target.mkdir(parents=True, exist_ok=True)
    output = target / ("wire" + sysconfig.get_config_var("EXT_SUFFIX"))
    cold = not output.exists()
    if cold:
        with tempfile.NamedTemporaryFile(mode="w", dir=target, delete=False) as stream:
            stream.write(header)
            header_temp = stream.name
        os.replace(header_temp, target / "layout.h")
        with tempfile.NamedTemporaryFile(dir=target, suffix=".so.tmp", delete=False) as stream:
            output_temp = stream.name
        subprocess.run(
            [
                "cc",
                "-O3",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-missing-field-initializers",
                "-I" + sysconfig.get_paths()["include"],
                "-I" + str(target),
                str(ROOT / "wire.c"),
                "-o",
                output_temp,
            ],
            check=True,
        )
        os.replace(output_temp, output)
    spec = importlib.util.spec_from_file_location("wire", output)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, output, time.perf_counter() - started, cold


def reference(wire):
    msg = messaging.log_from_bytes(wire)
    if msg.which() != "carState":
        raise ValueError("carState required")
    car = msg.carState
    return msg.logMonoTime, msg.valid, car.vEgo, car.steeringAngleDeg, car.wheelSpeeds.fl, car.gearShifter.raw


def reference_event(wire):
    msg = messaging.log_from_bytes(wire)
    kind = msg.which()
    body = getattr(msg, kind)
    header = (msg.logMonoTime, msg.valid)
    if kind == "carState":
        return header + (body.vEgo, body.steeringAngleDeg, body.wheelSpeeds.fl, body.gearShifter.raw)
    if kind == "carControl":
        return header + (body.enabled, body.actuators.accel, body.actuators.torque)
    if kind == "modelV2":
        return header + (list(body.position.x), [list(lead.x) for lead in body.leadsV3], body.meta.laneChangeState.raw)
    if kind == "longitudinalPlan":
        return header + (list(body.speeds), list(body.accels), body.shouldStop)
    if kind == "can":
        return header + ([(f.address, f.dat, f.src) for f in body],)
    raise ValueError(kind)


def reference_write(row):
    timestamp, valid, speed, angle, wheel, gear = row
    return log.Event.new_message(
        logMonoTime=timestamp,
        valid=valid,
        carState={"vEgo": speed, "steeringAngleDeg": angle, "wheelSpeeds": {"fl": wheel}, "gearShifter": gear},
    ).to_bytes()


def reference_write_can(row):
    timestamp, valid, frames = row
    return log.Event.new_message(
        logMonoTime=timestamp,
        valid=valid,
        can=[{"address": address, "dat": data, "src": src} for address, data, src in frames],
    ).to_bytes()


def reference_write_plan(row):
    timestamp, valid, speeds, accels, stop = row
    return log.Event.new_message(
        logMonoTime=timestamp, valid=valid, longitudinalPlan={"speeds": speeds, "accels": accels, "shouldStop": stop}
    ).to_bytes()


def bindings(path, api_module):
    class Result(ctypes.Structure):
        _fields_ = [
            ("timestamp", ctypes.c_uint64),
            ("speed", ctypes.c_double),
            ("angle", ctypes.c_double),
            ("wheel", ctypes.c_double),
            ("valid", ctypes.c_uint),
            ("gear", ctypes.c_uint),
        ]

    dll = ctypes.PyDLL(str(path))
    dll.project.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(Result)]
    dll.project.restype = ctypes.c_int
    ffi = cffi.FFI()
    ffi.cdef(
        "typedef struct { uint64_t timestamp; double speed, angle, wheel; unsigned valid, gear; } Result; int project(const unsigned char *, size_t, Result *);"
    )
    lib = ffi.dlopen(str(path))

    def ctypes_one(data):
        out = Result()
        if not dll.project(data, len(data), ctypes.byref(out)):
            raise ValueError("invalid message")
        return out.timestamp, bool(out.valid), out.speed, out.angle, out.wheel, out.gear

    def cffi_one(data):
        out = ffi.new("Result *")
        if not lib.project(data, len(data), out):
            raise ValueError("invalid message")
        return out.timestamp, bool(out.valid), out.speed, out.angle, out.wheel, out.gear

    def cffi_api_one(data):
        out = api_module.ffi.new("Result *")
        if not api_module.lib.project(data, len(data), out):
            raise ValueError("invalid message")
        return out.timestamp, bool(out.valid), out.speed, out.angle, out.wheel, out.gear

    def ctypes_batch(rows):
        out = Result()
        pointer = ctypes.byref(out)
        values = []
        for data in rows:
            if not dll.project(data, len(data), pointer):
                raise ValueError("invalid message")
            values.append((out.timestamp, bool(out.valid), out.speed, out.angle, out.wheel, out.gear))
        return values

    def cffi_batch(rows):
        out = api_module.ffi.new("Result *")
        values = []
        for data in rows:
            if not api_module.lib.project(data, len(data), out):
                raise ValueError("invalid message")
            values.append((out.timestamp, bool(out.valid), out.speed, out.angle, out.wheel, out.gear))
        return values

    return ctypes_one, cffi_one, cffi_api_one, ctypes_batch, cffi_batch


def compile_cffi(path):
    started = time.perf_counter()
    ffi = cffi.FFI()
    ffi.cdef(
        "typedef struct { uint64_t timestamp; double speed, angle, wheel; unsigned valid, gear; } Result; int project(const unsigned char *, size_t, Result *);"
    )
    ffi.set_source(
        "_wire_cffi",
        '#include "wire.c"',
        include_dirs=[str(ROOT), str(path.parent)],
        extra_compile_args=["-O3"],
        define_macros=[("_CFFI_NO_LIMITED_API", "1")],
        py_limited_api=False,
    )
    output = ffi.compile(tmpdir=str(path.parent), verbose=False)
    spec = importlib.util.spec_from_file_location("_wire_cffi", output)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, time.perf_counter() - started


def compile_pybind(path):
    import pybind11

    started = time.perf_counter()
    target = path.parent
    obj = target / "wire.o"
    subprocess.run(
        [
            "cc",
            "-O3",
            "-fPIC",
            "-fvisibility=hidden",
            "-I" + sysconfig.get_paths()["include"],
            "-I" + str(target),
            "-c",
            str(ROOT / "wire.c"),
            "-o",
            str(obj),
        ],
        check=True,
    )
    output = target / ("_wire_pybind" + sysconfig.get_config_var("EXT_SUFFIX"))
    subprocess.run(
        [
            "c++",
            "-O3",
            "-DNDEBUG",
            "-shared",
            "-fPIC",
            "-fvisibility=hidden",
            "-std=c++17",
            "-I" + sysconfig.get_paths()["include"],
            "-I" + pybind11.get_include(),
            str(ROOT / "binding.cpp"),
            str(obj),
            "-o",
            str(output),
        ],
        check=True,
    )
    spec = importlib.util.spec_from_file_location("_wire_pybind", output)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, time.perf_counter() - started


def measure_many(cases, count, repeat):
    loops = {}
    samples = {name: [] for name in cases}
    for name, fn in cases.items():
        t = time.perf_counter()
        fn()
        loops[name] = max(1, int(0.15 / (time.perf_counter() - t)))
    names = list(cases)
    for round_number in range(repeat):
        order = names[round_number % len(names) :] + names[: round_number % len(names)]
        for name in order:
            t = time.perf_counter()
            for _ in range(loops[name]):
                cases[name]()
            samples[name].append((time.perf_counter() - t) * 1e6 / loops[name] / count)
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rlog", type=Path)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--messages", type=int, default=1000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        module, path, cold, _ = compile_kernel(Path(directory))
        _, _, warm, _ = compile_kernel(Path(directory))
        api_module, cffi_compile = compile_cffi(path)
        pybind, pybind_compile = compile_pybind(path)
        ctypes_one, cffi_one, cffi_api_one, ctypes_batch, cffi_batch = bindings(path, api_module)
        groups = {kind: [] for kind in ["carState", "carControl", "modelV2", "longitudinalPlan", "can"]}
        for msg in LogReader(str(args.rlog)):
            kind = msg.which()
            if kind in groups and len(groups[kind]) < args.messages:
                groups[kind].append(msg.as_builder().to_bytes())
            if all(len(v) == args.messages for v in groups.values()):
                break
        wire = groups["carState"]
        assert wire
        expected = [reference(b) for b in wire]
        cases = {
            "pycapnp projection": lambda: [reference(b) for b in wire],
            "CPython direct wire": lambda: [module.one(b) for b in wire],
            "CPython batch wire": lambda: module.batch(wire),
            "ctypes PyDLL same kernel": lambda: [ctypes_one(b) for b in wire],
            "CFFI ABI same kernel": lambda: [cffi_one(b) for b in wire],
            "CFFI API same kernel": lambda: [cffi_api_one(b) for b in wire],
            "pybind11 same kernel": lambda: [pybind.one(b) for b in wire],
            "pybind11 batch kernel": lambda: pybind.batch(wire),
            "ctypes reuse batch": lambda: ctypes_batch(wire),
            "CFFI API reuse batch": lambda: cffi_batch(wire),
        }
        for fn in cases.values():
            assert fn() == expected
        for kind, data in groups.items():
            assert data, kind
            assert [module.event(b) for b in data] == [reference_event(b) for b in data]
        assert [reference(b) for b in map(module.write_car, expected)] == expected
        assert [reference(b) for b in map(reference_write, expected)] == expected
        for row in expected:
            assert (
                messaging.log_from_bytes(module.write_car(row)).to_dict()
                == messaging.log_from_bytes(reference_write(row)).to_dict()
            )
        read_results = {}
        for kind, data in groups.items():
            samples = measure_many(
                {
                    "baseline": lambda: [reference_event(b) for b in data],
                    "native": lambda: [module.event(b) for b in data],
                },
                len(data),
                args.repeat,
            )
            read_results[kind] = {"count": len(data), "sha256": hashlib.sha256(b"".join(data)).hexdigest(), **samples}
        writes = measure_many(
            {
                "baseline": lambda: [reference_write(row) for row in expected],
                "native": lambda: [module.write_car(row) for row in expected],
            },
            len(expected),
            args.repeat,
        )
        bulk_writes = {}
        for kind, baseline, native in [
            ("can", reference_write_can, module.write_can),
            ("longitudinalPlan", reference_write_plan, module.write_plan),
        ]:
            rows = [reference_event(data) for data in groups[kind]]
            for row in rows:
                assert (
                    messaging.log_from_bytes(native(row)).to_dict() == messaging.log_from_bytes(baseline(row)).to_dict()
                )
            bulk_writes[kind] = measure_many(
                {"baseline": lambda: [baseline(row) for row in rows], "native": lambda: [native(row) for row in rows]},
                len(rows),
                args.repeat,
            )
        print(
            json.dumps(
                {
                    "read_by_type": read_results,
                    "bulk_writes": bulk_writes,
                    "carState_write": writes,
                    "count": len(wire),
                    "corpus_sha256": hashlib.sha256(b"".join(wire)).hexdigest(),
                    "pybind_compile_seconds": pybind_compile,
                    "cffi_compile_seconds": cffi_compile,
                    "runtime_compile_seconds": cold,
                    "cached_load_seconds": warm,
                    "cpu_affinity": sorted(os.sched_getaffinity(0)),
                    "us_per_event": measure_many(cases, len(wire), args.repeat),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
