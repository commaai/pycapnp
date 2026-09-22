"""Isolate direct-wire versus typed libcapnp with shared Python conversion code."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sysconfig
import tempfile

from openpilot.tools.lib.logreader import LogReader
from run import ROOT, layout, measure_many, reference
from test_adversarial import equal


def build(directory, archive):
    (directory / "layout.h").write_text(layout())
    includes = [
        "-I" + sysconfig.get_paths()["include"],
        "-I" + str(directory),
        "-I" + str(ROOT.parents[1] / "vendor/capnproto/src"),
    ]
    obj = directory / "wire.o"
    subprocess.run(["cc", "-O3", "-fPIC", *includes, "-c", str(ROOT / "wire.c"), "-o", str(obj)], check=True)
    output = directory / ("library_control" + sysconfig.get_config_var("EXT_SUFFIX"))
    subprocess.run(
        [
            "c++",
            "-O3",
            "-std=c++17",
            "-fPIC",
            "-shared",
            *includes,
            str(ROOT / "library_control.cpp"),
            str(obj),
            str(archive),
            "-pthread",
            "-o",
            str(output),
        ],
        check=True,
    )
    spec = importlib.util.spec_from_file_location("library_control", output)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outcome(fn, data):
    try:
        return True, fn(data)
    except ValueError:
        return False, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("rlog", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--messages", type=int, default=1000)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        module = build(Path(directory), args.archive)
        wire = []
        for msg in LogReader(str(args.rlog)):
            if msg.which() == "carState":
                wire.append(msg.as_builder().to_bytes())
                if len(wire) == args.messages:
                    break
        assert wire
        rows = [reference(data) for data in wire]
        for data, row in zip(wire, rows):
            assert equal(module.read_direct(data), row)
            assert equal(module.read_library(data), row)
            # Both backends allocate identical schema-sized structs in identical order.
            assert module.write_direct(row) == module.write_library(row) == module.write_library_flat(row)
        seed = wire[0]
        for end in range(len(seed)):
            assert outcome(module.read_direct, seed[:end])[0] == outcome(module.read_library, seed[:end])[0]
        rng = random.Random(170)
        stricter_rejections = 0
        for _ in range(10000):
            data = bytearray(seed)
            for _ in range(rng.randrange(1, 5)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            direct = outcome(module.read_direct, bytes(data))
            library = outcome(module.read_library, bytes(data))
            assert not direct[0] or library[0]
            stricter_rejections += library[0] and not direct[0]
            if direct[0]:
                assert equal(direct[1], library[1])
        cases = {
            "direct read": lambda: [module.read_direct(data) for data in wire],
            "typed library read": lambda: [module.read_library(data) for data in wire],
            "direct write": lambda: [module.write_direct(row) for row in rows],
            "typed library malloc write": lambda: [module.write_library(row) for row in rows],
            "typed library flat write": lambda: [module.write_library_flat(row) for row in rows],
        }
        print(
            json.dumps(
                {
                    "stricter_malformed_rejections": stricter_rejections,
                    "count": len(wire),
                    "sha256": hashlib.sha256(b"".join(wire)).hexdigest(),
                    "us_per_event": measure_many(cases, len(wire), args.repeat),
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
