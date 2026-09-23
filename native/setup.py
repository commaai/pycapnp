"""Build generated bindings against this repository's vendored libcapnp."""

import os
from pathlib import Path
import subprocess

from setuptools import Extension, setup

here = Path(__file__).resolve().parent
root = here.parent
output = Path(os.environ.get("CAPNP_NATIVE_OUTPUT", here / "build")).resolve()
name = os.environ.get("CAPNP_NATIVE_MODULE", "generated_native")
build = here / "build/capnproto"
subprocess.run(
    ["cmake", "-S", str(root / "vendor/capnproto"), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"], check=True
)
subprocess.run(["cmake", "--build", str(build), "--parallel", "2"], check=True)
setup(
    name="capnp-native",
    ext_modules=[
        Extension(
            name,
            [str(output / f"{name}.cpp")],
            depends=[str(output / "runtime.h"), str(output / "accessors.h"), str(build / "libcapnp-vendored.a")],
            include_dirs=[str(root / "vendor/capnproto/src"), str(output)],
            extra_objects=[str(build / "libcapnp-vendored.a")],
            extra_compile_args=["-std=c++17", "-O3", "-g0"],
            language="c++",
        )
    ],
)
